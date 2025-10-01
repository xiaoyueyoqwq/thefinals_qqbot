#!/bin/bash
# ============================================================
# Docker 入口脚本 - THE FINALS QQ Bot
# ============================================================

set -e

echo "=========================================="
echo "THE FINALS QQ Bot - Starting..."
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================
# 1. 环境检查
# ============================================================
log_info "检查运行环境..."

# 检查 Python 版本
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
log_info "Python 版本: $PYTHON_VERSION"

# 检查必要的目录
REQUIRED_DIRS=(
    "/app/data"
    "/app/data/cache"
    "/app/data/persistence"
    "/app/logs"
    "/app/static/temp_images"
    "/app/config"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        log_warn "目录不存在，正在创建: $dir"
        mkdir -p "$dir"
    fi
done

# ============================================================
# 2. 配置文件检查
# ============================================================
log_info "检查配置文件..."

CONFIG_FILE="/app/config/config.yaml"
CONFIG_EXAMPLE="/app/config/config.yaml.example"

if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "$CONFIG_EXAMPLE" ]; then
        log_warn "配置文件不存在，从示例文件创建..."
        cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
        log_error "请编辑 config/config.yaml 文件并填写正确的配置！"
        exit 1
    else
        log_error "配置文件和示例文件都不存在！"
        exit 1
    fi
else
    log_info "配置文件已找到: $CONFIG_FILE"
fi

# ============================================================
# 3. 数据库初始化检查
# ============================================================
log_info "检查数据库文件..."

DB_FILES=(
    "/app/data/deep_search.db"
    "/app/data/df_history.db"
    "/app/data/flappy_bird.db"
)

for db in "${DB_FILES[@]}"; do
    if [ ! -f "$db" ]; then
        log_info "数据库文件将在首次运行时自动创建: $db"
    fi
done

# ============================================================
# 4. Redis 连接检查
# ============================================================
log_info "检查 Redis 连接..."

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if timeout 2 bash -c "cat < /dev/null > /dev/tcp/$REDIS_HOST/$REDIS_PORT" 2>/dev/null; then
        log_info "Redis 连接成功: $REDIS_HOST:$REDIS_PORT"
        break
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
            log_error "无法连接到 Redis: $REDIS_HOST:$REDIS_PORT"
            log_warn "机器人将继续启动，但缓存功能可能不可用"
            break
        fi
        log_warn "等待 Redis 启动... ($RETRY_COUNT/$MAX_RETRIES)"
        sleep 2
    fi
done

# ============================================================
# 5. Playwright 浏览器检查
# ============================================================
log_info "检查 Playwright 浏览器..."

if [ -d "/home/botuser/.cache/ms-playwright" ]; then
    log_info "Playwright 浏览器已安装"
else
    log_warn "Playwright 浏览器可能未正确安装，图片生成功能可能受影响"
fi

# ============================================================
# 6. 权限检查
# ============================================================
log_info "检查文件权限..."

# 确保数据目录可写
if [ -w "/app/data" ]; then
    log_info "数据目录权限正常"
else
    log_error "数据目录不可写！"
    exit 1
fi

# ============================================================
# 7. 清理旧的临时文件
# ============================================================
log_info "清理旧的临时文件..."

TEMP_IMAGE_DIR="/app/static/temp_images"
if [ -d "$TEMP_IMAGE_DIR" ]; then
    # 统计并删除超过 24 小时的图片
    CLEANED_COUNT=$(find "$TEMP_IMAGE_DIR" -type f -mtime +1 2>/dev/null | wc -l)
    find "$TEMP_IMAGE_DIR" -type f -mtime +1 -delete 2>/dev/null || true
    if [ "$CLEANED_COUNT" -gt 0 ]; then
        log_info "已清理 $CLEANED_COUNT 个过期临时文件"
    fi
fi

# ============================================================
# 8. 显示系统信息
# ============================================================
log_info "系统信息:"
echo "  - 主机名: $(hostname)"
echo "  - 用户: $(whoami)"
echo "  - 工作目录: $(pwd)"
echo "  - 时区: ${TZ:-未设置}"
echo "  - Python 路径: $(which python)"

# ============================================================
# 9. 启动应用
# ============================================================
echo "=========================================="
log_info "启动 THE FINALS QQ Bot..."
echo "=========================================="

# 执行传入的命令
exec "$@"

