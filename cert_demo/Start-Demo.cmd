@echo off
chcp 65001 >nul
set "PROJECT_ROOT=%~dp0.."
if not defined CERT_DEMO_PYTHON set "CERT_DEMO_PYTHON=D:\Apps\miniconda3\envs\fapiao\python.exe"
if not defined CERT_OCR_MODEL_ROOT set "CERT_OCR_MODEL_ROOT=%PROJECT_ROOT%\models\official_models"
if not defined CERT_OCR_DEVICE set "CERT_OCR_DEVICE=cpu"
if not defined CERT_OCR_CPU_THREADS set "CERT_OCR_CPU_THREADS=8"
"%CERT_DEMO_PYTHON%" -X utf8 -B "%~dp0launch.py"
if errorlevel 1 (
  pause
  exit /b 1
)
