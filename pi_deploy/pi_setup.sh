#!/bin/bash
# Create or reuse the inference environment. Never remove an existing venv.
set -euo pipefail
cd "$(dirname "$0")"

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--offline" ]; }; then
  echo "Usage: bash pi_setup.sh [--offline]"
  exit 2
fi
if [ "${1:-}" = "--offline" ] && [ ! -d wheels_pi ]; then
  echo "Offline mode requires wheels_pi/ with compatible aarch64 Python wheels."
  exit 1
fi

car_venv="${CAR_PI_VENV:-$HOME/pi_venv}"
if [ ! -e "$car_venv" ]; then
  python3 -m venv "$car_venv"
fi
if [ ! -x "$car_venv/bin/python" ]; then
  echo "Not a usable Python venv: $car_venv"
  exit 1
fi

if [ "${1:-}" = "--offline" ]; then
  "$car_venv/bin/python" -m pip install --no-index --find-links wheels_pi -r requirements.txt
else
  "$car_venv/bin/python" -m pip install -r requirements.txt
fi
"$car_venv/bin/python" - <<'PY'
import cv2
import numpy
import onnxruntime
print("opencv:", cv2.__version__)
print("numpy:", numpy.__version__)
print("onnxruntime:", onnxruntime.__version__)
PY
echo "Environment ready: $car_venv"
echo "Run: $car_venv/bin/python pi_camera_demo.py --model best_320.onnx"
