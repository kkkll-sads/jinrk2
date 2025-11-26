#!/bin/bash

# 设置标题
echo "金融卡服务系统-生产环境"

# 设置环境变量
export FLASK_ENV=production
export FLASK_DEBUG=0
export SECRET_KEY="+Dm2%%%%3;|;9%%%%v"
export PYTHONOPTIMIZE=2
export LOG_LEVEL=INFO
export HOST=0.0.0.0
export PORT=80
export PUBLIC_URL=http://103.164.81.222
export WAITRESS_THREADS=32
export WAITRESS_CHANNEL_TIMEOUT=300
export WAITRESS_CONNECTION_LIMIT=2000
export WAITRESS_CLEANUP_INTERVAL=30
export WAITRESS_MAX_REQUEST_BODY_SIZE=1073741824
export WAITRESS_SOCKET_OPTIONS=SO_REUSEADDR
export WAITRESS_OUTBUF_OVERFLOW=104857600
export WAITRESS_INBUF_OVERFLOW=52428800
export WAITRESS_SEND_BYTES=65536
export WAITRESS_RECV_BYTES=65536
export WAITRESS_BACKLOG=2048

# 检查是否以root权限运行（使用80端口需要）
if [ "$EUID" -ne 0 ] && [ "$PORT" -eq 80 ]; then
    echo "使用80端口需要root权限，请使用sudo运行此脚本"
    echo "或者修改PORT环境变量使用其他端口"
    exit 1
fi

# 检查Python是否已安装
if ! command -v python3 &> /dev/null; then
    echo "Python3未安装，请先安装Python3"
    exit 1
fi

# 使用python3作为默认Python命令
PYTHON_CMD=python3
if command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version 2>&1)
    if [[ $PYTHON_VERSION == *"Python 3"* ]]; then
        PYTHON_CMD=python
    fi
fi

# 检查pip是否可用
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo "pip未安装或不可用，请确保pip已正确安装"
    exit 1
fi

# 创建目录（Linux使用/作为路径分隔符）
mkdir -p temp
mkdir -p logs
mkdir -p static/uploads
mkdir -p static/replays
mkdir -p static/replays/thumbnails

# 检查Python版本
echo "检查Python版本..."
$PYTHON_CMD --version
echo "Python版本检查完成"

# 清理并重新安装依赖
echo "正在安装核心依赖..."
$PYTHON_CMD -m pip install --no-cache-dir numpy==1.23.5
$PYTHON_CMD -m pip install --no-cache-dir pandas==1.5.3
$PYTHON_CMD -m pip install --no-cache-dir moviepy==1.0.3
$PYTHON_CMD -m pip install --no-cache-dir Flask==2.0.1
$PYTHON_CMD -m pip install --no-cache-dir Werkzeug==2.0.1
$PYTHON_CMD -m pip install --no-cache-dir openpyxl==3.0.9
$PYTHON_CMD -m pip install --no-cache-dir backoff==2.1.2
$PYTHON_CMD -m pip install --no-cache-dir APScheduler==3.9.1
$PYTHON_CMD -m pip install --no-cache-dir waitress==2.1.2
$PYTHON_CMD -m pip install --no-cache-dir requests==2.31.0
$PYTHON_CMD -m pip install --no-cache-dir -r requirements.txt

# 创建默认缩略图
if [ ! -f "static/video-placeholder.jpg" ]; then
    echo "创建默认视频缩略图..."
    if ls static/uploads/*.jpg 1> /dev/null 2>&1; then
        cp static/uploads/*.jpg static/video-placeholder.jpg 2> /dev/null || true
    fi
    if [ ! -f "static/video-placeholder.jpg" ]; then
        echo "警告：未找到缩略图，创建空白图片..."
        touch static/video-placeholder.jpg
    fi
fi

# 检查视频文件
echo "检查视频文件..."
if ! ls static/replays/*.mp4 static/replays/*.webm 1> /dev/null 2>&1; then
    echo "警告：未找到视频文件"
    echo "请将视频文件放入 static/replays 目录"
fi

# 备份和初始化日志文件
mkdir -p logs
if [ -f "logs/app.log" ]; then
    echo "备份日志文件..."
    BACKUP_TIME=$(date +"%Y%m%d_%H%M%S")
    cp "logs/app.log" "logs/app_backup_${BACKUP_TIME}.log"
    rm "logs/app.log"
fi
touch "logs/app.log"
echo "$(date) [INFO] 金融卡服务系统启动" > "logs/app.log"

echo "正在启动金融卡服务系统（生产环境）..."
echo "应用将在 http://$HOST:$PORT 运行"
echo "按 Ctrl+C 可以停止服务器"

# 启动应用
$PYTHON_CMD run.py

if [ $? -ne 0 ]; then
    echo "应用启动失败，请检查日志文件"
    if [ -f "logs/app.log" ]; then
        cat "logs/app.log"
    fi
    exit 1
fi 