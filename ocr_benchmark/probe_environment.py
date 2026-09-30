import os
from pathlib import Path
import time
import json
import sys

root = Path(__file__).resolve().parent
os.environ['PADDLE_PDX_CACHE_HOME'] = str(root / 'runtime_cache')
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['USE_TORCH'] = '0'
# This benchmark uses Paddle only. Keep unrelated optional Torch CUDA DLLs
# out of the process; do not modify either installed package.
sys.modules['torch'] = None
t = time.perf_counter()
from paddleocr import PaddleOCR
print('paddleocr_import_s', time.perf_counter()-t, flush=True)
import paddle
print(json.dumps({'version': paddle.__version__, 'compiled_cuda': paddle.is_compiled_with_cuda(), 'device': paddle.get_device(), 'gpu_count': paddle.device.cuda.device_count() if paddle.is_compiled_with_cuda() else 0}, ensure_ascii=False), flush=True)
