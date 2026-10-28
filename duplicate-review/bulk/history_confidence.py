"""Opt-in provenance recovery policy. Never used for file quarantine."""
import io
import math
import cv2
import numpy as np
from PIL import Image, ImageCms
import same_photo

VERSION = 'history-high-confidence-1'
MIN_SCORE = 99.0
MIN_MARGIN = 1.0


def candidates(saved, catalog, digest, separated):
    """A strong, unique winner by image contents; nearby alternatives stay manual."""
    by_sha = {}
    for match in saved:
        item = catalog.get(match.get('id'))
        if not item or item.get('quarantine_only'):
            continue
        if tuple(sorted((digest, item['sha']))) in separated:
            continue
        try:
            score = float(match['score'])
        except (KeyError, ValueError, TypeError):
            continue
        if not math.isfinite(score) or not 0 <= score <= 100:
            continue
        if score > float(by_sha.get(item['sha'], {}).get('score', -1)):
            by_sha[item['sha']] = match
    ranked = sorted(by_sha.values(), key=lambda m: -float(m['score']))
    if not ranked or float(ranked[0]['score']) < MIN_SCORE:
        return []
    if len(ranked) > 1 and float(ranked[0]['score']) - float(ranked[1]['score']) <= MIN_MARGIN:
        return []
    return ranked[:1]


def prepare(path):
    result = same_photo.prepare(path)
    if result is None:
        return None
    # Convert embedded profiles to sRGB instead of demanding identical metadata.
    # Untagged ordinary images are treated as sRGB; nonstandard untagged gamma
    # metadata remains manual rather than silently discarding its meaning.
    icc, metadata = result['profile']
    if icc:
        source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        rgb = ImageCms.profileToProfile(Image.fromarray(result['rgb']), source,
                                       ImageCms.createProfile('sRGB'), outputMode='RGB')
        result['rgb'] = np.array(rgb)
    elif metadata != '[None, None, None]':
        raise ValueError('Untagged color metadata needs manual review.')
    result['profile'] = ('normalized-sRGB', '')
    gray = cv2.cvtColor(result['rgb'], cv2.COLOR_RGB2GRAY)
    keys, result['desc'] = cv2.SIFT_create(nfeatures=1200, contrastThreshold=.025).detectAndCompute(gray, None)
    result['points'] = np.float32([k.pt for k in keys]).reshape(-1, 2)
    return result


def pixels_agree(a, b):
    # More tolerance for global JPEG/resizing noise, while retaining the strict
    # local checks so a matching background cannot conceal a changed pose.
    x = cv2.GaussianBlur(a.astype(np.float32), (3, 3), .6)
    y = cv2.GaussianBlur(b.astype(np.float32), (3, 3), .6)
    delta = np.max(np.abs(x-y), axis=2)
    if delta.mean() > 6 or (delta > 20).mean() > .02:
        return False
    if (cv2.boxFilter((delta > 20).astype(np.float32), -1, (24, 24)).max() > .25
            or cv2.boxFilter(delta, -1, (24, 24)).max() > 15):
        return False
    gx = cv2.cvtColor(x, cv2.COLOR_RGB2GRAY)
    gy = cv2.cvtColor(y, cv2.COLOR_RGB2GRAY)
    blur = lambda v: cv2.GaussianBlur(v, (11, 11), 1.5)
    ux, uy = blur(gx), blur(gy)
    vx, vy = np.maximum(0, blur(gx*gx)-ux*ux), np.maximum(0, blur(gy*gy)-uy*uy)
    cov = blur(gx*gy)-ux*uy
    structure = (2*cov+58.5225)/(vx+vy+58.5225)
    return bool(structure.mean() >= .98
                and cv2.boxFilter(1-structure, -1, (24, 24)).max() <= .05
                and cv2.boxFilter(1-structure, -1, (12, 12)).max() <= .09)


def verify(target, keeper):
    return same_photo.verify(target, keeper, pixel_check=pixels_agree)
