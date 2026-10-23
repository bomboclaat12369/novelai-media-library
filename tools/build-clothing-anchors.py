"""Build fixed text features for the bulk pilot; never run on the user's photos.

Developer-only dependencies: numpy, tokenizers, onnxruntime. Supply a directory
containing the pinned text_model.onnx and tokenizer.json. The app needs neither
the text model nor these additional dependencies: it uses the generated features
with its existing FashionSigLIP image vectors.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

MODEL = 'Marqo/marqo-fashionSigLIP'
REVISION = 'c56244cc94f92419e8369fa71efdaf403b124ce8'
TEXT_SHA = 'c1d501b23bddf27ba828c037b0780e44fdf47ca4c0b925ef190ab5bcf7aaf6e6'
TOKEN_SHA = '5bc9b16db0e7adf5c9a2bd57f8f9c8e6ebdaabe75679cc956d007f78036d5b4a'
IMAGE_SHA = 'a7e773846b27a699c45ba7e3978514b7fca420662d7e69e3b9226982f09f4a13'
PROMPTS = {
    'clothing': [
        'a photograph of a woman wearing a dress',
        'a photograph of a woman wearing a shirt and pants',
        'a photograph of a woman wearing a blouse and skirt',
        'a photograph of a woman wearing a sweater',
        'a photograph of a woman wearing a jacket',
        'a photograph of a woman wearing a bikini',
        'a photograph of a woman wearing a swimsuit',
        'a photograph of a woman wearing a bra and underwear',
        'a photograph of a woman wearing lingerie',
    ],
    'limited': [
        'a photograph of a nude woman',
        'a photograph of a naked woman with no clothing',
        'a photograph of a woman without clothes',
    ],
    'partial': [
        'a photograph of a woman taking off her clothes',
        'a photograph of a topless woman wearing pants',
        'a photograph of a woman with clothing partly removed',
    ],
}


def build(root, output):
    for name, digest in [('text_model.onnx', TEXT_SHA), ('tokenizer.json', TOKEN_SHA)]:
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Checksum mismatch: '+name)
    tokenizer = Tokenizer.from_file(str(root/'tokenizer.json'))
    tokenizer.enable_truncation(max_length=64)
    tokenizer.enable_padding(length=64, pad_id=tokenizer.token_to_id('</s>'), pad_token='</s>')
    options = ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
    session = ort.InferenceSession(str(root/'text_model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
    rows = []
    for kind, prompts in PROMPTS.items():
        for prompt in prompts:
            ids = np.array([tokenizer.encode(prompt).ids], dtype=np.int64)
            vector = session.run(None, {'input_ids':ids})[0].reshape(-1)
            vector = vector / np.linalg.norm(vector)
            if vector.size != 768 or not np.isfinite(vector).all():raise ValueError('Invalid text vector')
            rows.append({'kind':kind, 'text':prompt, 'vector':[round(float(value),8) for value in vector]})
    data = {'recipe':'garment-cues-1','model':MODEL,'revision':REVISION,
            'image_model_sha':IMAGE_SHA,'text_model_sha':TEXT_SHA,'tokenizer_sha':TOKEN_SHA,
            'license':'Apache-2.0','sequence_length':64,'rows':rows}
    output.write_text(json.dumps(data,separators=(',',':'))+'\n',encoding='utf-8')
    print('Wrote',len(rows),'fixed text features to',output)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('model_dir',type=Path)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'duplicate-review/bulk/clothing-anchors.json')
    args=parser.parse_args();build(args.model_dir,args.output)
