#!/bin/bash

# 金融卡服务系统启动脚本 - 端口8003
# 适用于Linux系统

echo "=========================================="
echo "启动金融卡服务系统 - 端口8003"
echo "=========================================="

# 设置环境变量
export HOST=0.0.0.0
export PORT=8003
export FLASK_ENV=production

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3环境，请先安装Python3"
    exit 1
fi

# 检查依赖文件
if [ ! -f "requirements.txt" ]; then
    echo "错误: 未找到requirements.txt文件"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "创建Python虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 安装/更新依赖
echo "检查并安装依赖..."
pip install -r requirements.txt

# 创建必要的目录
mkdir -p logs
mkdir -p static/uploads
mkdir -p static/replays
mkdir -p temp

# 设置权限
chmod 755 logs
chmod 755 static
chmod 755 static/uploads
chmod 755 static/replays
chmod 755 temp

# 启动应用
echo "启动应用在端口8003..."
echo "访问地址: http://localhost:8003"
echo "域名访问: http://hf.ztdj888.vip (需要配置NGINX)"
echo ""
echo "按 Ctrl+C 停止服务"
echo "=========================================="

# 启动应用
python3 run.py
