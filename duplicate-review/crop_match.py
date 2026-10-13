"""Local, cached feature retrieval followed by geometric AND pixel verification.
No feature match is proof of identity: results are manual-review suggestions only.
"""
import io
import cv2
import numpy as np
from PIL import Image, ImageOps

cv2.setNumThreads(1)
FEATURE_VERSION = 1


def describe(image):
    image = image.copy()
    image.thumbnail((800, 800), Image.Resampling.LANCZOS)
    rgb = np.asarray(image.convert('RGB'))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    detector = cv2.SIFT_create(nfeatures=450, contrastThreshold=.025)
    variants = []
    for reflected in (False, True):
        pixels = np.ascontiguousarray(gray[:, ::-1] if reflected else gray)
        keys, descriptors = detector.detectAndCompute(pixels, None)
        points = np.array([k.pt for k in keys], dtype=np.float32).reshape(-1, 2)
        points /= np.array([gray.shape[1], gray.shape[0]], dtype=np.float32)
        variants.append((points, descriptors.astype(np.uint8) if descriptors is not None else np.empty((0,128),np.uint8)))
    small = cv2.resize(rgb, (256, 256), interpolation=cv2.INTER_AREA)
    buf = io.BytesIO()
    np.savez_compressed(buf, points=variants[0][0], desc=variants[0][1],
                        mirror_points=variants[1][0], mirror_desc=variants[1][1], image=small)
    return buf.getvalue()


def unpack(data):
    with np.load(io.BytesIO(data), allow_pickle=False) as z:
        result = {k:z[k] for k in z.files}
    # Convert once per cached image, not for every candidate pair.
    result['desc'] = result['desc'].astype(np.float32, copy=False)
    result['mirror_desc'] = result['mirror_desc'].astype(np.float32, copy=False)
    return result


def verify(a, b, mode, mirrored=False):
    prefix = 'mirror_' if mirrored else ''
    da, db = a[prefix+'desc'].astype(np.float32, copy=False), b['desc'].astype(np.float32, copy=False)
    if min(len(da),len(db)) < 8:
        return None
    nearest = cv2.BFMatcher().knnMatch(da, db, k=2)
    good = [m for m,n in nearest if m.distance < .78*n.distance and m.distance < 260]
    # Each destination feature gets at most one vote.
    good = list({m.trainIdx:m for m in sorted(good,key=lambda m:-m.distance)}.values())
    if len(good) < 8:
        return None
    p = np.float32([a[prefix+'points'][m.queryIdx]*256 for m in good])
    q = np.float32([b['points'][m.trainIdx]*256 for m in good])
    # Affine fit permits aspect-changing crops; constrain its geometry below.
    transform, inliers = cv2.estimateAffine2D(p,q,method=cv2.RANSAC,ransacReprojThreshold=2.5,maxIters=2000,confidence=.995)
    if transform is None or inliers is None:
        return None
    selected = inliers.ravel().astype(bool)
    if selected.sum() < 8 or selected.mean() < .45:
        return None
    # Correspondences must span the image, not just a logo or watermark.
    spread = [cv2.contourArea(cv2.convexHull(points[selected]))/(256*256) for points in (p,q)]
    if max(spread) < .12 or min(spread) < .025:
        return None
    determinant = np.linalg.det(transform[:,:2])
    if determinant <= 0 or not .04 < determinant < 25:
        return None
    src = a['image'][:,::-1] if mirrored else a['image']
    warped = cv2.warpAffine(src,transform,(256,256),flags=cv2.INTER_LINEAR)
    mask = cv2.warpAffine(np.ones((256,256),np.uint8),transform,(256,256),flags=cv2.INTER_NEAREST)
    mask = cv2.erode(mask,np.ones((5,5),np.uint8)).astype(bool)
    overlap = mask.mean()
    # Most of at least one image must be explained by the alignment.
    if max(overlap,min(1,overlap/determinant)) < .55 or overlap < .12:
        return None
    x,y = warped[mask].astype(float),b['image'][mask].astype(float)
    # Mild exposure / white balance differences should not defeat matching.
    x -= x.mean(axis=0); y -= y.mean(axis=0)
    norm = np.sqrt(np.sum(x*x)*np.sum(y*y))
    if not norm: return None
    corr = float((x*y).sum()/norm)
    error = float(np.abs(x-y).mean())
    threshold = {'strict':.98,'balanced':.96,'broad':.935}[mode]
    if corr < threshold or error > {'strict':15,'balanced':23,'broad':30}[mode]:
        return None
    return round(corr*100,1), 'Aligned visual match' + (' · mirrored' if mirrored else ' · crop / rotation')


def candidates(query, index, owners):
    """No top-N image cutoff. Every image with enough feature votes is verified."""
    if not len(query): return []
    indices, distances = index.knnSearch(query.astype(np.float32, copy=False), min(12,len(owners)), params={'checks':96})
    valid = (indices >= 0) & (distances < 260**2)
    rows = np.broadcast_to(np.arange(len(indices))[:,None],indices.shape)[valid]
    matched = owners[indices[valid]]
    if not len(matched): return []
    # Unique (query point, image) pairs preserve the old one-vote rule.
    width = int(owners.max()) + 1
    encoded = rows.astype(np.int64)*width + matched
    votes = np.bincount(np.unique(encoded)%width, minlength=width)
    return np.flatnonzero(votes >= 6).tolist()
