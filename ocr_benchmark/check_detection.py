import argparse
import os
import sys
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--samples-dir', type=Path, default=ROOT/'samples')
parser.add_argument('--model-root', type=Path, default=ROOT.parent/'models'/'official_models')
args = parser.parse_args()
os.environ['PADDLE_PDX_CACHE_HOME'] = str(ROOT / 'runtime_cache')
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['USE_TORCH'] = '0'
sys.modules['torch'] = None
from paddleocr import PaddleOCR
import numpy as np
import cv2

cfg = json.loads((ROOT/'gpu_standard'/'metadata.json').read_text(encoding='utf-8'))['config']
for key,value in list(cfg.items()):
    if key.endswith('_model_dir'):
        cfg[key] = str(args.model_root.resolve()/Path(value).name)
ocr = PaddleOCR(**cfg)
output = []
for filename in ['104113','104119','104125']:
    p = args.samples_dir.resolve() / f'屏幕截图 2026-09-07 {filename}.png'
    if not p.is_file():raise FileNotFoundError(f'找不到检测样本: {p}')
    im = cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    for settings in [dict(text_det_thresh=0.2,text_det_box_thresh=0.35),dict(text_det_thresh=0.1,text_det_box_thresh=0.25)]:
        t = time.perf_counter()
        result = list(ocr.predict(im,**settings))
        row = {'file':filename,'settings':settings,'elapsed_s':time.perf_counter()-t,'texts':result[0]['rec_texts']}
        output.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
(ROOT/'detection_trials.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
ocr.close()
