#!/bin/bash

# 金融卡服务系统 Linux 部署脚本 - 端口8003
# 部署到 /opt/jinrongka2

echo "=========================================="
echo "金融卡服务系统 Linux 部署脚本"
echo "部署路径: /opt/jinrongka2"
echo "运行端口: 8003"
echo "域名: hf.ztdj888.vip"
echo "=========================================="

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    echo "请使用root权限运行此脚本: sudo $0"
    exit 1
fi

# 设置变量
APP_DIR="/opt/jinrongka2"
NGINX_CONF="/etc/nginx/sites-available/jinrongka2-8003.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/jinrongka2-8003.conf"
SERVICE_NAME="jinrongka2-8003"

# 创建应用目录
echo "创建应用目录..."
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/logs"
mkdir -p "$APP_DIR/static/uploads"
mkdir -p "$APP_DIR/static/replays"
mkdir -p "$APP_DIR/temp"

# 复制项目文件
echo "复制项目文件..."
cp -r . "$APP_DIR/"

# 设置目录权限
echo "设置目录权限..."
chown -R www-data:www-data "$APP_DIR"
chmod -R 755 "$APP_DIR"
chmod -R 777 "$APP_DIR/logs"
chmod -R 777 "$APP_DIR/static/uploads"
chmod -R 777 "$APP_DIR/temp"

# 安装Python依赖
echo "安装Python依赖..."
cd "$APP_DIR"

# 检查Python3
if ! command -v python3 &> /dev/null; then
    echo "安装Python3..."
    apt update
    apt install -y python3 python3-pip python3-venv
fi

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "创建Python虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境并安装依赖
echo "安装Python包..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 安装NGINX
echo "安装NGINX..."
apt update
apt install -y nginx

# 配置NGINX
echo "配置NGINX..."
cp nginx_config/financial-card-service.conf "$NGINX_CONF"

# 创建软链接
if [ -L "$NGINX_ENABLED" ]; then
    rm "$NGINX_ENABLED"
fi
ln -s "$NGINX_CONF" "$NGINX_ENABLED"

# 测试NGINX配置
echo "测试NGINX配置..."
nginx -t
if [ $? -ne 0 ]; then
    echo "NGINX配置测试失败，请检查配置文件"
    exit 1
fi

# 创建systemd服务文件
echo "创建systemd服务..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=金融卡服务系统 (端口8003)
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
Environment=HOST=0.0.0.0
Environment=PORT=8003
Environment=FLASK_ENV=production
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 重新加载systemd
systemctl daemon-reload

# 启动服务
echo "启动服务..."
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

# 重启NGINX
echo "重启NGINX..."
systemctl restart nginx

# 检查服务状态
echo "检查服务状态..."
systemctl status "$SERVICE_NAME" --no-pager -l

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo "应用目录: $APP_DIR"
echo "服务名称: $SERVICE_NAME"
echo "运行端口: 8003"
echo "访问地址: http://localhost:8003"
echo "域名访问: http://hf.ztdj888.vip"
echo ""
echo "服务管理命令:"
echo "  启动服务: systemctl start $SERVICE_NAME"
echo "  停止服务: systemctl stop $SERVICE_NAME"
echo "  重启服务: systemctl restart $SERVICE_NAME"
echo "  查看状态: systemctl status $SERVICE_NAME"
echo "  查看日志: journalctl -u $SERVICE_NAME -f"
echo ""
echo "NGINX管理命令:"
echo "  测试配置: nginx -t"
echo "  重启NGINX: systemctl restart nginx"
echo "  查看NGINX状态: systemctl status nginx"
echo "=========================================="
