"""Conservative same-photo verification for reversible, opt-in quarantine.

Unlike broad review suggestions, every discarded image must be contained in its
actual keeper and pass both global and local pixel/structure checks. Scores here
are engineering thresholds, not probabilities. Ambiguity returns False.
"""
import cv2
import numpy as np
from PIL import Image, ImageOps

VERSION = "same-photo-1"


def prepare(path):
    with Image.open(path) as original:
        if getattr(original, 'n_frames', 1) != 1:
            raise ValueError('Animated or multi-page image')
        profile = (original.info.get('icc_profile', b''),
                   repr([original.info.get(k) for k in ('gamma', 'srgb', 'chromaticity')]))
        image = ImageOps.exif_transpose(original)
        if image.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
            return None
        if image.convert('RGBA').getchannel('A').getextrema() != (255, 255):
            return None
        image = image.convert('RGB')
        image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        rgb = np.array(image)
    if min(rgb.shape[:2]) < 128:
        return None
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if gray.std() < 8:
        return None
    keys, desc = cv2.SIFT_create(nfeatures=1200, contrastThreshold=.025).detectAndCompute(gray, None)
    points = np.float32([k.pt for k in keys]).reshape(-1, 2)
    return {'rgb': rgb, 'profile': profile, 'points': points, 'desc': desc}


def _pixels_agree(a, b):
    # Small blur tolerates resampling/JPEG noise; no region or corner is ignored.
    x = cv2.GaussianBlur(a.astype(np.float32), (3, 3), .6)
    y = cv2.GaussianBlur(b.astype(np.float32), (3, 3), .6)
    delta = np.max(np.abs(x-y), axis=2)
    if delta.mean() > 4 or (delta > 20).mean() > .015:
        return False
    # Inspect overlapping local windows: an unchanged background must not hide
    # a changed hand, face, or other small part of the photograph.
    local_bad = cv2.boxFilter((delta > 20).astype(np.float32), -1, (24, 24))
    local_error = cv2.boxFilter(delta, -1, (24, 24))
    if local_bad.max() > .25 or local_error.max() > 15:
        return False
    gx = cv2.cvtColor(x, cv2.COLOR_RGB2GRAY)
    gy = cv2.cvtColor(y, cv2.COLOR_RGB2GRAY)
    blur = lambda v: cv2.GaussianBlur(v, (11, 11), 1.5)
    ux, uy = blur(gx), blur(gy)
    vx, vy = np.maximum(0, blur(gx*gx)-ux*ux), np.maximum(0, blur(gy*gy)-uy*uy)
    cov = blur(gx*gy)-ux*uy
    structure = (2*cov+58.5225)/(vx+vy+58.5225)
    if structure.mean() < .99:
        return False
    # Local structural loss catches subtle changes even without large RGB error.
    if (cv2.boxFilter(1-structure, -1, (24, 24)).max() > .05
            or cv2.boxFilter(1-structure, -1, (12, 12)).max() > .09):
        return False
    return True


def _check_transform(target, keeper, matrix):
    a, b = target['rgb'], keeper['rgb']
    h, w = a.shape[:2]; kh, kw = b.shape[:2]
    scale = float(np.linalg.norm(matrix[:, 0]))
    if not .08 <= scale <= 12:
        return False
    # Every corner of the target must be covered by the keeper, not merely a
    # shared region. Rotated copies can qualify; complementary crops cannot.
    corners = np.float32([[0, 0], [w-1, 0], [0, h-1], [w-1, h-1]])
    mapped = corners @ matrix[:, :2].T + matrix[:, 2]
    if (mapped.min(axis=0) < -1).any() or (mapped.max(axis=0) > [kw, kh]).any():
        return False
    factor = min(1., scale, 1024/max(w, h))
    ow, oh = max(1, round(w*factor)), max(1, round(h*factor))
    if min(ow, oh) < 128:
        return False
    # Map comparison pixel centers back to target, then into the keeper.
    resize = np.array([[w/ow, 0, (w/ow-1)/2], [0, h/oh, (h/oh-1)/2], [0, 0, 1.]])
    mapping = matrix @ resize
    # Filter before downsampling the keeper. Point sampling would create aliasing
    # and falsely reject ordinary resized versions of the same photograph.
    reduction = min(1., 1/float(np.linalg.norm(mapping[:, 0])))
    if reduction < .999:
        bw, bh = max(1, round(kw*reduction)), max(1, round(kh*reduction))
        b = np.array(Image.fromarray(b).resize((bw, bh), Image.Resampling.LANCZOS))
        adjust = np.array([[bw/kw, 0, (bw/kw-1)/2], [0, bh/kh, (bh/kh-1)/2]])
        mapping = adjust @ np.vstack([mapping, [0, 0, 1]])
    warped = cv2.warpAffine(b, mapping, (ow, oh), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
    reduced = np.array(Image.fromarray(a).resize((ow, oh), Image.Resampling.LANCZOS))
    return _pixels_agree(reduced, warped)


def verify(target, keeper):
    """True only when target is explained by keeper. No quality/MP ranking here."""
    if target is None or keeper is None or target['profile'] != keeper['profile']:
        return False
    h, w = target['rgb'].shape[:2]; kh, kw = keeper['rgb'].shape[:2]
    if abs((w/h)/(kw/kh)-1) < .002:
        # Exact resize mapping avoids feature-fit noise for ordinary copies.
        sx, sy = kw/w, kh/h
        matrix = np.array([[sx, 0, (sx-1)/2], [0, sy, (sy-1)/2]])
        if _check_transform(target, keeper, matrix):
            return True
    da, db = target['desc'], keeper['desc']
    if da is None or db is None or min(len(da), len(db)) < 16:
        return False
    matches = cv2.BFMatcher().knnMatch(da, db, k=2)
    good = [pair[0] for pair in matches if len(pair)==2 and pair[0].distance < .65*pair[1].distance]
    good = list({m.trainIdx: m for m in sorted(good, key=lambda m:-m.distance)}.values())
    if len(good) < 16:
        return False
    p = np.float32([target['points'][m.queryIdx] for m in good])
    q = np.float32([keeper['points'][m.trainIdx] for m in good])
    # A single rigid resize/rotation/translation, never a flexible warp that can
    # deform one pose into another. Mirrored variants stay in manual review.
    matrix, inliers = cv2.estimateAffinePartial2D(p, q, method=cv2.RANSAC, ransacReprojThreshold=1.2, maxIters=3000, confidence=.999)
    if matrix is None or inliers is None:
        return False
    mask = inliers.ravel().astype(bool)
    if mask.sum() < 16 or mask.mean() < .85:
        return False
    if cv2.contourArea(cv2.convexHull(p[mask]))/(w*h) < .25:
        return False
    errors = np.linalg.norm(p[mask] @ matrix[:, :2].T + matrix[:, 2] - q[mask], axis=1)
    if np.median(errors) > .35:
        return False
    return _check_transform(target, keeper, matrix)
