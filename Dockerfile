# ============================================================
# 多阶段构建 Dockerfile - THE FINALS QQ Bot
# ============================================================

# ============================================================
# 阶段 1: 基础镜像 - 安装系统依赖
# ============================================================
FROM python:3.11-slim-bookworm AS base

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    curl \
    wget \
    ca-certificates \
    # 图像处理依赖
    libjpeg62-turbo \
    libpng16-16 \
    libfreetype6 \
    # Playwright 浏览器依赖
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    # 字体支持
    fonts-liberation \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# 阶段 2: 构建阶段 - 安装 Python 依赖
# ============================================================
FROM base AS builder

# 安装构建工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖到虚拟环境
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install -r requirements.txt

# 安装 Playwright 浏览器
RUN /opt/venv/bin/playwright install chromium

# ============================================================
# 阶段 3: 运行阶段 - 最小化镜像
# ============================================================
FROM base AS runtime

# 创建非 root 用户
RUN groupadd -r botuser && \
    useradd -r -g botuser -u 1000 -m -s /bin/bash botuser

# 从构建阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv

# 从构建阶段复制 Playwright 浏览器
COPY --from=builder /root/.cache/ms-playwright /home/botuser/.cache/ms-playwright

# 设置工作目录
WORKDIR /app

# 复制应用代码
COPY --chown=botuser:botuser . .

# 创建必要的目录
RUN mkdir -p \
    /app/data \
    /app/data/cache \
    /app/data/persistence \
    /app/data/backups \
    /app/logs \
    /app/static/temp_images \
    /app/config && \
    chown -R botuser:botuser /app

# 设置环境变量
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH"

# 切换到非 root 用户
USER botuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 暴露端口
EXPOSE 8080

# 启动脚本
COPY --chown=botuser:botuser docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "bot.py"]

