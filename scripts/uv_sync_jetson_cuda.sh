#!/usr/bin/env bash
# Jetson：加载 CUDA 路径后执行 uv sync（L4T R36+ 上 sherpa-onnx 已默认编 GPU，本脚本可选）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/env/jetson-sherpa-cuda.sh"
exec uv sync "$@"
