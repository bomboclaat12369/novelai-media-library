"""Verify shared photographic details locally before assigning a multi-pose shoot."""
from pathlib import Path
from collections import OrderedDict
import hashlib
import json
import sqlite3

import cv2
import numpy as np
from PIL import Image, ImageOps

from engine import linked, stat_key

RECIPE = 'shoot-scene-rootsift-v4'
SIZE = 720


def tone_profile(pixels):
    """Compare lighting and color in shadows, midtones and highlights across crops."""
    rgb = cv2.resize(pixels, (32, 32), interpolation=cv2.INTER_AREA)[2:29, 2:30]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2Lab).reshape(-1, 3)
    light = lab[:, 0]
    low, high = np.quantile(light, [.25, .70])
    if high - low < 10:
        return None
    bins = np.clip((lab[:, 1:].astype(np.int32) - 64) * 24 // 128, 0, 23)
    index = bins[:, 0] * 24 + bins[:, 1]
    result = []
    for band, weight in ((light <= low, .20), ((light >= low) & (light <= high), .35), (light >= high, .45)):
        hist = np.bincount(index[band], minlength=576).reshape(24, 24).astype(np.float32)
        hist = cv2.GaussianBlur(hist, (5, 5), .9)
        result.append(np.sqrt(hist * (weight / hist.sum())).ravel())
    return np.concatenate(result)


def preview(path):
    with Image.open(path) as source:
        # The same export settings can corroborate a numbered source. They do
        # not establish that the photos were captured by the same camera.
        tables = getattr(source, 'quantization', None)
        export = (tuple(sorted(source.size)), tuple(tuple(tables[k]) for k in sorted(tables))) if tables else None
        source.draft('RGB',(SIZE,SIZE))
        image = ImageOps.exif_transpose(source)
        image.thumbnail((SIZE,SIZE),Image.Resampling.LANCZOS)
        pixels = np.asarray(image.convert('RGB'))
    return pixels, export


def photo_style(pixels, export):
    h, w = pixels.shape[:2]
    hsv = cv2.cvtColor(pixels, cv2.COLOR_RGB2HSV)[round(h*.07):round(h*.89), round(w*.06):round(w*.94)]
    chroma = (hsv[:,:,1] > 55) & (hsv[:,:,2] > 40)
    hue = hsv[:,:,0].astype(np.int32) * 18 // 180
    bins = np.bincount(hue[chroma], minlength=18).astype(np.float32)
    bins = (2*bins + np.roll(bins,1) + np.roll(bins,-1)) / 4
    palette = np.sqrt(bins/bins.sum()) if bins.sum() >= .035*h*w else None
    small = cv2.resize(pixels, (128, 128), interpolation=cv2.INTER_AREA)[5:-9,5:-5].reshape(-1,3)
    light = small @ np.array([.299,.587,.114], dtype=np.float32)
    lo, hi = np.percentile(light, [98, 99.5])
    # The color of bright surfaces distinguishes a shared lighting treatment
    # from two unrelated photographs dominated by the same midtones.
    highlight = np.median(small[(light >= lo) & (light <= hi)], axis=0)
    return palette, tone_profile(pixels), export, highlight


def describe(path):
    pixels, export = preview(path)
    h,w = pixels.shape[:2]
    if min(h,w)<70:
        return None
    gray = cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY)
    mask = np.zeros_like(gray)
    mask[round(h*.07):round(h*.89),round(w*.06):round(w*.94)] = 255
    keys,desc = cv2.SIFT_create(nfeatures=900,contrastThreshold=.026).detectAndCompute(gray,mask)
    if desc is None or len(keys)<14:
        return None
    desc = np.sqrt(desc/np.maximum(desc.sum(axis=1,keepdims=True),1e-8))
    points = np.array([k.pt for k in keys],np.float32)
    return points, desc, (w,h), *photo_style(pixels, export)


def geometric_support(left,right):
    if left is None or right is None:
        return None
    lp,ld,ls=left[:3]
    rp,rd,rs=right[:3]
    matcher=cv2.BFMatcher(cv2.NORM_L2)
    def distinctive(x,y):
        return {(a.queryIdx,a.trainIdx) for a,b in matcher.knnMatch(x,y,k=2) if a.distance<.80*b.distance}
    forward=distinctive(ld,rd)
    if len(forward)<12:
        return None
    reverse=distinctive(rd,ld)
    pairs=sorted((a,b) for a,b in forward if (b,a) in reverse)
    if len(pairs)<12:
        return None
    a=lp[[i for i,_ in pairs]];b=rp[[j for _,j in pairs]]
    model,mask=cv2.findHomography(a,b,cv2.RANSAC,4.0,maxIters=850,confidence=.99)
    if model is None or mask is None:
        return None
    good=mask[:,0].astype(bool)
    count=int(good.sum())
    if count<10 or count<.42*len(pairs):
        return None
    def spread(points,size):
        pts=points[good]/np.asarray(size,np.float32)
        area=cv2.contourArea(cv2.convexHull(pts))
        tiles=len({tuple(v) for v in np.minimum((pts*4).astype(int),3)})
        return area,tiles
    area,tiles=map(min,zip(spread(a,ls),spread(b,rs)))
    if area<.026 or tiles<3:
        return None
    return {'inliers':count,'area':round(area,3)}


class SceneEvidence:
    def __init__(self,items,recovered=None,cache_path=None,analysis_recipe=None):
        self.items=items
        self.analysis_recipe=analysis_recipe
        self.recovered=recovered
        self.features=OrderedDict()
        self.styles=OrderedDict()
        self.pairs={}
        self.cache_path=cache_path
        self.cache=None
        self.verified_stamps={}
        self.unreadable=set()

    def stamp(self,ident):
        item=self.items[ident]
        try:
            path=Path(item['path'])
            if linked(path):return None
            stamp=stat_key(path)
            if stamp==item.get('stamp') or self.recovered and self.recovered(item):
                return stamp
        except (KeyError,OSError):
            pass
        return None

    def check_group(self,ids,whole,compute):
        before={i:self.stamp(i) for i in ids}
        if not all(before.values()):return None
        identity=[(i,self.items[i]['sha'],self.items[i].get('analysis_sha'),s) for i,s in sorted(before.items())]
        recipe = (RECIPE, self.analysis_recipe) if self.analysis_recipe else RECIPE
        key=hashlib.sha256(json.dumps([recipe,whole,identity]).encode()).hexdigest()
        saved=None
        if self.cache_path:
            try:
                if self.cache is None:
                    self.cache=sqlite3.connect(self.cache_path,timeout=2,isolation_level=None)
                    self.cache.execute('CREATE TABLE IF NOT EXISTS groups(key TEXT PRIMARY KEY,proof TEXT NOT NULL)')
                saved=self.cache.execute('SELECT proof FROM groups WHERE key=?',(key,)).fetchone()
            except sqlite3.Error:
                self.cache_path=None
        if saved:
            try:proof=json.loads(saved[0])
            except (ValueError,TypeError):saved=None
        if not saved:
            proof=compute()
            if any(self.stamp(i)!=s for i,s in before.items()):return None
            if self.cache_path and self.cache is not None and not self.unreadable.intersection(ids):
                try:self.cache.execute('INSERT OR REPLACE INTO groups VALUES (?,?)',(key,json.dumps(proof)))
                except sqlite3.Error:pass
        if proof:self.verified_stamps.update(before)
        return proof

    def close(self):
        if self.cache is not None:self.cache.close()
        self.features.clear()
        self.styles.clear()
        self.pairs.clear()

    def style(self, ident):
        stamp = self.stamp(ident)
        known = self.features.get(ident)
        if known is not None and known[0] == stamp:
            return known[1][3:] if known[1] is not None else None
        cached = self.styles.get(ident)
        if cached is None or cached[0] != stamp:
            try:
                value = photo_style(*preview(self.items[ident]['path'])) if stamp else None
            except (OSError, ValueError, KeyError, cv2.error, Image.DecompressionBombError):
                self.unreadable.add(ident)
                value = None
            self.styles[ident] = (stamp, value)
        self.styles.move_to_end(ident)
        if len(self.styles) > 1024:
            self.styles.popitem(last=False)
        return self.styles[ident][1]

    def feature(self,ident):
        stamp = self.stamp(ident)
        if ident not in self.features or self.features[ident][0] != stamp:
            item=self.items[ident]
            try:
                path=Path(item['path'])
                value = describe(path) if stamp else None
            except (OSError,ValueError,KeyError,cv2.error,Image.DecompressionBombError):
                self.unreadable.add(ident)
                value = None
            self.features[ident] = (stamp, value)
        self.features.move_to_end(ident)
        if len(self.features)>160:
            self.features.popitem(last=False)
        return self.features[ident][1]

    def pair(self,a,b):
        key=tuple(sorted(((a, self.stamp(a)), (b, self.stamp(b)))))
        if key not in self.pairs:
            self.pairs[key]=geometric_support(self.feature(key[0][0]),self.feature(key[1][0]))
        return self.pairs[key]
