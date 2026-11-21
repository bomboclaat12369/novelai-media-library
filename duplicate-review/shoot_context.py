"""Complete a compact shoot when some views show too little background for geometry."""
import re
from pathlib import PurePath

import numpy as np

from bulk.sources import original_name
from shoot_scene import RECIPE

# Camera-style counters can survive an attachment service's extra filename suffix.
# Generic slide numbers are assigned to compilations just as often as to shoots.
SERIAL = re.compile(r'^(_?(?:img|dscf?|dscn|pict|dji)[_-]?)(\d{3,8})(?:[_-][a-z0-9]+)?$', re.I)
MIN_PHOTOS = 5
MAX_PHOTOS = 24


def numbered_series(items, ids, post):
    if not MIN_PHOTOS <= len(ids) <= MAX_PHOTOS:
        return False
    matches = [SERIAL.fullmatch(PurePath(original_name(items[i], post)).stem) for i in ids]
    if not all(matches) or len({(m[1].casefold(), len(m[2])) for m in matches}) != 1:
        return False
    numbers = [int(m[2]) for m in matches]
    return all(right == left + 1 for left, right in zip(numbers, numbers[1:]))


def shared_highlights(styles, core, crops):
    highlights = np.stack([style[3] for style in styles])
    reference = highlights[sorted(core)]
    bright = (np.median(reference, axis=0) >= 248) & (reference.min(axis=0) >= 240)
    gaps = highlights[:,:,None] - highlights[:,None,:]
    lower = np.percentile(gaps[sorted(core)], 15, axis=0)
    distinctive = lower >= 32
    if not bright.any() or not distinctive.any():
        return False
    for j in crops:
        if np.any(highlights[j,bright] < np.maximum(244, reference[:,bright].min(axis=0) - 4)):
            return False
        if np.any(gaps[j][distinctive] < lower[distinctive] - 14):
            return False
    return True


def complete_shoot(ids, agreement, scene, numbered, repeated):
    """Every crop must have direct witnesses in one independently verified scene."""
    n = len(ids)
    if not 4 <= n <= MAX_PHOTOS:
        return None
    outfit = agreement[:, :, 0]
    weakest_median = np.nanmedian(outfit, axis=1).min()
    if weakest_median < .68:
        return None
    styles = [scene.style(i) for i in ids]
    if any(s is None or s[0] is None or s[1] is None for s in styles):
        return None
    hues = np.stack([s[0] for s in styles])
    tones = np.stack([s[1] for s in styles])
    colors = hues @ hues.T
    lighting = tones @ tones.T
    export = styles[0][2]
    same_export = export is not None and all(s[2] == export for s in styles)
    crop_context = (n >= MIN_PHOTOS and (numbered or repeated) and same_export and
                    np.nanmin(outfit) >= .63 and weakest_median >= .72 and
                    colors.min() >= .93 and lighting.min() >= .66)
    comparable = (outfit >= .70) & (colors >= .82) & (lighting >= .65)
    required = max(2, (n + 2) // 3)
    if not crop_context and min(comparable.sum(axis=1)) < required:
        return None
    if any(scene.feature(i) is None for i in ids):
        return None

    # Check all plausible room correspondences, including pairs separated by
    # several close-ups. Two independent scene groups are a reason to abstain.
    peers = [set() for _ in ids]
    direct = [set() for _ in ids]
    broad = set()
    links = []
    linked_pairs = []
    for j in range(n):
        for k in range(j):
            if not crop_context and not comparable[j, k]:
                continue
            link = scene.pair(ids[j], ids[k])
            if link is None:
                continue
            count, area = link['inliers'], link['area']
            links.append([ids[j], ids[k], count, area])
            linked_pairs.append((j, k))
            if count >= 28 and area >= .055 and comparable[j, k]:
                direct[j].add(k)
                direct[k].add(j)
            if count >= 20 and area >= .030:
                peers[j].add(k)
                peers[k].add(j)
                if count >= 32 and area >= .055:
                    broad.update((j, k))
    summary = {'recipe': RECIPE, 'camera_groups': 1, 'numbered_series': numbered,
               'repeated_block': repeated, 'common_export': same_export,
               'geometric_pairs': len(links), 'links': links}
    if links:
        summary['minimum_inliers'] = min(link[2] for link in links)
    # Even without a filename sequence, multiple well-spread scene details can
    # directly verify every frame. Reject two clusters joined by a single view.
    if min(map(len, direct)) >= required and all(
            k in direct[j] or len(direct[j] & direct[k]) >= 2 for j in range(n) for k in range(j)):
        return dict(summary, method='multiple-direct-scene-witnesses', scene_core=list(ids),
                    minimum_witnesses=min(map(len, direct)), crop_witnesses={})
    if not crop_context:
        return None
    core = {j for j in broad if len(peers[j]) >= 2}
    if len(core) < 3 or 2 * len(core) <= n:
        return None
    for j in core:
        neighbors = peers[j] & core
        if len(neighbors) < max(2, len(core) // 3):
            return None
        if any(len(neighbors & peers[k]) < 2 for k in core - neighbors - {j}):
            return None
    fringe = set(range(n)) - core
    # A few similar compositions leave too little evidence for a crop that
    # shares no verifiable detail with them, even in a numbered sequence.
    if fringe and (len(core) < 5 or not shared_highlights(styles, core, fringe)):
        return None
    if any(j in fringe and k in fringe for j, k in linked_pairs):
        return None
    witnesses = {}
    for j in range(n):
        support = [k for k in sorted(core - {j}) if outfit[j,k] >= .72 and lighting[j,k] >= .77
                   and colors[j,k] >= .95 and .6 * lighting[j,k] + .4 * outfit[j,k] >= .80]
        if len(support) < 2:
            return None
        if j in fringe:
            witnesses[ids[j]] = [ids[k] for k in support]
    if fringe:
        summary['highlight_rgb'] = {i: styles[j][3].round(1).tolist() for j, i in enumerate(ids)}
    return dict(summary, method='scene-core-and-crop-witnesses',
                scene_core=[ids[j] for j in sorted(core)], crop_witnesses=witnesses)
