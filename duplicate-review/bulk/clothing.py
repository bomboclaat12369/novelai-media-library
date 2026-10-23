"""Cheap, fallible clothing-cue gate, using existing image features.

These are prompt similarities, not calibrated probabilities or a nudity detector.
Only clear positive clothing evidence unlocks an outfit-only link. Everything
else needs context/source corroboration. No new per-image neural inference.
"""
import json
from functools import lru_cache
from pathlib import Path
import numpy as np

RECIPE = 'garment-cues-1'


@lru_cache(maxsize=1)
def anchors():
    data=json.loads(Path(__file__).with_name('clothing-anchors.json').read_text(encoding='utf-8'))
    if data['recipe'] != RECIPE:raise ValueError('Clothing feature recipe mismatch')
    matrix=np.array([r['vector'] for r in data['rows']],np.float32)
    if matrix.shape != (15,768) or not np.isfinite(matrix).all():raise ValueError('Invalid clothing features')
    return matrix,[r['kind'] for r in data['rows']],data['image_model_sha']


def classify(vectors,model_sha=None):
    matrix,kinds,image_sha=anchors()
    if model_sha is not None and model_sha!=image_sha:raise ValueError('Clothing cues require a matching image-model version.')
    scores=vectors @ matrix.T
    result=[]
    for row in scores:
        best={k:float(max(row[j] for j,kind in enumerate(kinds) if kind==k)) for k in ('clothing','limited','partial')}
        margin=best['clothing']-max(best['limited'],best['partial'])
        state='present' if margin>=.025 else ('limited' if best['limited']-best['clothing']>=.015 else 'uncertain')
        result.append({'state':state,'margin':round(margin,4),'recipe':RECIPE,
                       'scores':{k:round(v,4) for k,v in best.items()}})
    return result
