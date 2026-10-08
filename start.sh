#!/usr/bin/env bash
# Render / 云平台启动脚本
# Render 会注入 PORT 环境变量；本地没设置时回退到 8000。
set -euo pipefail

PORT="${PORT:-8000}"

echo "[start] working dir: $(pwd)"
echo "[start] python: $(python --version 2>&1)"
echo "[start] listening on 0.0.0.0:${PORT}"

# app-dir 指向 backend 目录，让 main.py 里的 import 正常工作
exec uvicorn main:app \
  --app-dir backend \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  --timeout-keep-alive 30 \
  --no-server-header
