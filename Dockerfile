# 班级课表统计工具 —— Render 部署镜像
# 单镜像同时提供 FastAPI 接口与静态前端页面，适合 Render 免费实例（0.1 CPU / 512MB）。
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/backend:/usr/local/lib/python3.*/site-packages

WORKDIR /app

# pdfplumber 依赖的轮子均为纯 wheel，无需编译工具链，因此不安装 build-essential，
# 以保持镜像体积小、构建快。
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

# Render 会注入 PORT；这里给出默认值，方便本地 docker run 测试
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz').read()"

# 显式用 sh 调用，避免镜像内缺少可执行位时启动失败
CMD ["sh", "/app/start.sh"]
