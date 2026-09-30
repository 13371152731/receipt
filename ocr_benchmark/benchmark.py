"""Local PaddleOCR benchmark: original inputs, serial requests, synchronized GPU.

Run with the existing Paddle environment, not the document runtime.
All model paths are explicit local files. No image is uploaded.
"""
import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import statistics
import sys
import time
import traceback
import winreg

START = time.perf_counter()
ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--profile', choices=['gpu_full', 'gpu_standard', 'cpu_standard', 'gpu_960'], required=True)
parser.add_argument('--rounds', type=int, default=3)
parser.add_argument('--samples-dir', type=Path, default=ROOT/'samples')
parser.add_argument('--model-root', type=Path, default=ROOT.parent/'models'/'official_models')
args = parser.parse_args()
OUT = ROOT / args.profile
OUT.mkdir(parents=True, exist_ok=True)
os.environ['PADDLE_PDX_CACHE_HOME'] = str(ROOT / 'runtime_cache')
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['USE_TORCH'] = '0'
# Optional ModelScope logging would otherwise load the unrelated Torch CUDA
# runtime, which conflicts with installed Paddle DLLs on this computer.
# Only disable Torch in this child process; Paddle inference is unmodified.
sys.modules['torch'] = None

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def log(event, **data):
    row = {'event': event, **data}
    with (OUT / 'events.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps(row, ensure_ascii=False), flush=True)

def native(value):
    if hasattr(value, 'tolist'):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [native(v) for v in value]
    return value

try:
    t = time.perf_counter()
    from paddleocr import PaddleOCR
    import paddle
    import cv2
    import numpy as np
    import_s = time.perf_counter() - t
    model_root = args.model_root.resolve()
    gpu = args.profile.startswith('gpu')
    cfg = {
        'device': 'gpu:0' if gpu else 'cpu',
        'text_detection_model_name': 'PP-OCRv5_server_det',
        'text_detection_model_dir': str(model_root / 'PP-OCRv5_server_det'),
        'text_recognition_model_name': 'PP-OCRv5_server_rec',
        'text_recognition_model_dir': str(model_root / 'PP-OCRv5_server_rec'),
        'doc_orientation_classify_model_name': 'PP-LCNet_x1_0_doc_ori',
        'doc_orientation_classify_model_dir': str(model_root / 'PP-LCNet_x1_0_doc_ori'),
        'textline_orientation_model_name': 'PP-LCNet_x1_0_textline_ori',
        'textline_orientation_model_dir': str(model_root / 'PP-LCNet_x1_0_textline_ori'),
        'use_doc_orientation_classify': True,
        'use_textline_orientation': True,
        'use_doc_unwarping': args.profile == 'gpu_full',
        'text_recognition_batch_size': 6,
        'textline_orientation_batch_size': 6,
        'text_det_limit_side_len': 64,
        'text_det_limit_type': 'min',
        'text_rec_score_thresh': 0.0,
        'use_tensorrt': False,
        'enable_hpi': False,
        'enable_mkldnn': True,
        'cpu_threads': 8,
    }
    if cfg['use_doc_unwarping']:
        cfg['doc_unwarping_model_name'] = 'UVDoc'
        cfg['doc_unwarping_model_dir'] = str(model_root / 'UVDoc')
    if args.profile == 'gpu_960':
        cfg['text_det_limit_side_len'] = 960
        cfg['text_det_limit_type'] = 'max'
    names = ['104113','104116','104119','104125','104136','104147','104154','104159','104205']
    descriptions = ['旧版证书近景','旧版证书留白','旧版证书斜拍','近重复近景','倒置且证书占比小','新版证书与页面标题','英文HCIP证书带弹窗','整页小字证书带弹窗','新版证书近景']
    paths = [args.samples_dir.resolve() / f'屏幕截图 2026-09-07 {n}.png' for n in names]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError('Benchmark samples are missing:\n'+'\n'.join(missing))
    images, samples = [], []
    for i, path in enumerate(paths):
        read_times = []
        for _ in range(3):
            t = time.perf_counter()
            raw = path.read_bytes()
            im = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
            read_times.append(time.perf_counter()-t)
        assert im is not None
        images.append(im)
        samples.append({'id': f'T{i+1:02}', 'filename': path.name, 'source_path': str(path), 'description': descriptions[i], 'width': im.shape[1], 'height': im.shape[0], 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'read_decode_median_s': statistics.median(read_times)})
    k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0')
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(x, ctypes.c_ulonglong) for x in ['total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended']]
    mem = MemoryStatus()
    mem.length = ctypes.sizeof(mem)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
    metadata = {'profile': args.profile, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S %z'), 'python': sys.version, 'executable': sys.executable, 'os': platform.platform(), 'cpu': winreg.QueryValueEx(k, 'ProcessorNameString')[0], 'logical_cpus': os.cpu_count(), 'ram_gib': mem.total_phys/1024**3, 'paddle': paddle.__version__, 'paddleocr': importlib.metadata.version('paddleocr'), 'paddlex': importlib.metadata.version('paddlex'), 'cuda_compiled': paddle.is_compiled_with_cuda(), 'gpu_name': paddle.device.cuda.get_device_name(0) if gpu else None, 'import_s': import_s, 'config': cfg, 'samples': samples, 'rounds': args.rounds, 'concurrency': 1, 'optional_torch_disabled_in_process': True}
    dump(OUT / 'metadata.json', metadata)
    log('imports_complete', seconds=import_s, profile=args.profile)
    t = time.perf_counter()
    ocr = PaddleOCR(**cfg)
    if gpu:
        paddle.device.cuda.synchronize()
    metadata['model_initialization_s'] = time.perf_counter()-t
    log('models_loaded', seconds=metadata['model_initialization_s'])
    ocr.export_paddlex_config_to_yaml(str(OUT / 'pipeline.yaml'))
    def infer(im):
        if gpu:
            paddle.device.cuda.synchronize()
        t = time.perf_counter()
        result = list(ocr.predict(im))
        if gpu:
            paddle.device.cuda.synchronize()
        return time.perf_counter()-t, result
    cold_s, cold = infer(images[0])
    metadata['first_inference_s'] = cold_s
    metadata['process_entry_to_first_result_s'] = time.perf_counter()-START
    dump(OUT / 'metadata.json', metadata)
    log('first_inference', id='T01', seconds=cold_s, entry_to_result_s=metadata['process_entry_to_first_result_s'])
    for sample, im in zip(samples, images):
        elapsed, result = infer(im)
        log('warmup', id=sample['id'], seconds=elapsed)
    rows = []
    raw_results = {}
    for rnd in range(1, args.rounds+1):
        indices = list(range(len(samples)))
        random.Random(20260907+rnd).shuffle(indices)
        for idx in indices:
            sample = samples[idx]
            elapsed, result = infer(images[idx])
            row = {'round':rnd,'id':sample['id'],'ocr_s':elapsed,'lines':sum(len(r.get('rec_texts',[])) for r in result)}
            rows.append(row)
            log('measurement', **row)
            if rnd == 1:
                raw_results[sample['id']] = [{key: native(r[key]) for key in ['rec_texts','rec_scores','rec_polys','rec_boxes','textline_orientation_angles'] if key in r} | {'doc_orientation_angle':native(r.get('doc_preprocessor_res',{}).get('angle'))} for r in result]
                dump(OUT / 'ocr_results.json', raw_results)
    vals = [r['ocr_s'] for r in rows]
    total = sum(vals)
    summary = {'profile':args.profile, 'count':len(vals), 'mean_s':statistics.mean(vals), 'median_s':statistics.median(vals), 'p95_s':float(np.percentile(vals,95)), 'min_s':min(vals), 'max_s':max(vals), 'serial_images_per_second':len(vals)/total, 'serial_images_per_minute':60*len(vals)/total, 'mean_nine_image_pass_s':total/args.rounds, 'by_image':{s['id']:{'mean_s':statistics.mean(r['ocr_s'] for r in rows if r['id']==s['id']), 'values_s':[r['ocr_s'] for r in rows if r['id']==s['id']]} for s in samples}}
    dump(OUT / 'measurements.json', rows)
    dump(OUT / 'summary.json', summary)
    log('complete', **{k:v for k,v in summary.items() if k != 'by_image'})
    ocr.close()
except BaseException as exc:
    dump(OUT / 'failure.json', {'error':str(exc),'traceback':traceback.format_exc(),'elapsed_s':time.perf_counter()-START})
    traceback.print_exc()
    raise
