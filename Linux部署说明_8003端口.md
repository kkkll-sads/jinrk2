# 金融卡服务系统 - Linux部署说明 (8003端口)

## 部署概述

本说明将指导您在Linux系统中部署金融卡服务系统，运行在8003端口，并通过NGINX绑定域名 `hf.ztdj888.vip`。

## 部署路径

- 应用目录: `/opt/jinrongka2`
- 运行端口: `8003`
- 域名: `hf.ztdj888.vip`

## 快速部署

### 方法1: 使用自动部署脚本（推荐）

```bash
# 1. 上传项目文件到服务器
# 2. 进入项目目录
cd /path/to/jinrongka2

# 3. 给脚本执行权限
chmod +x deploy_linux_8003.sh

# 4. 运行部署脚本（需要root权限）
sudo ./deploy_linux_8003.sh
```

### 方法2: 手动部署

#### 步骤1: 准备环境

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装必要软件
sudo apt install -y python3 python3-pip python3-venv nginx

# 创建应用目录
sudo mkdir -p /opt/jinrongka2
sudo chown -R $USER:$USER /opt/jinrongka2
```

#### 步骤2: 部署应用

```bash
# 复制项目文件
cp -r . /opt/jinrongka2/

# 进入应用目录
cd /opt/jinrongka2

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 创建必要目录
mkdir -p logs static/uploads static/replays temp

# 设置权限
chmod -R 755 .
chmod -R 777 logs static/uploads temp
```

#### 步骤3: 配置NGINX

```bash
# 复制NGINX配置
sudo cp nginx_config/financial-card-service.conf /etc/nginx/sites-available/jinrongka2-8003.conf

# 创建软链接
sudo ln -s /etc/nginx/sites-available/jinrongka2-8003.conf /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重启NGINX
sudo systemctl restart nginx
```

#### 步骤4: 创建系统服务

```bash
# 创建服务文件
sudo tee /etc/systemd/system/jinrongka2-8003.service > /dev/null << EOF
[Unit]
Description=金融卡服务系统 (端口8003)
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/jinrongka2
Environment=HOST=0.0.0.0
Environment=PORT=8003
Environment=FLASK_ENV=production
ExecStart=/opt/jinrongka2/venv/bin/python /opt/jinrongka2/run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 重新加载systemd
sudo systemctl daemon-reload

# 启用并启动服务
sudo systemctl enable jinrongka2-8003
sudo systemctl start jinrongka2-8003
```

## 服务管理

### 应用服务管理

```bash
# 启动服务
sudo systemctl start jinrongka2-8003

# 停止服务
sudo systemctl stop jinrongka2-8003

# 重启服务
sudo systemctl restart jinrongka2-8003

# 查看状态
sudo systemctl status jinrongka2-8003

# 查看日志
sudo journalctl -u jinrongka2-8003 -f
```

### NGINX管理

```bash
# 测试配置
sudo nginx -t

# 重启NGINX
sudo systemctl restart nginx

# 查看NGINX状态
sudo systemctl status nginx

# 查看NGINX日志
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

## 访问测试

### 本地测试

```bash
# 测试应用端口
curl http://localhost:8003

# 测试NGINX代理
curl http://localhost
```

### 域名测试

确保域名 `hf.ztdj888.vip` 的DNS记录指向您的服务器IP，然后访问：

- http://hf.ztdj888.vip

## 配置文件说明

### 应用配置

- **主启动文件**: `/opt/jinrongka2/run.py`
- **配置文件**: `/opt/jinrongka2/config.py`
- **端口设置**: 8003

### NGINX配置

- **配置文件**: `/etc/nginx/sites-available/jinrongka2-8003.conf`
- **上游服务器**: 127.0.0.1:8003
- **静态文件路径**: `/opt/jinrongka2/static/`

### 系统服务

- **服务名称**: `jinrongka2-8003`
- **服务文件**: `/etc/systemd/system/jinrongka2-8003.service`

## 日志文件

- **应用日志**: `/opt/jinrongka2/logs/app.log`
- **系统日志**: `journalctl -u jinrongka2-8003`
- **NGINX访问日志**: `/var/log/nginx/financial-card-access.log`
- **NGINX错误日志**: `/var/log/nginx/financial-card-error.log`

## 故障排除

### 1. 应用无法启动

```bash
# 检查端口占用
sudo netstat -tlnp | grep :8003

# 检查Python环境
/opt/jinrongka2/venv/bin/python --version

# 检查依赖
/opt/jinrongka2/venv/bin/pip list

# 查看详细日志
sudo journalctl -u jinrongka2-8003 -n 50
```

### 2. NGINX无法访问

```bash
# 检查NGINX配置
sudo nginx -t

# 检查NGINX状态
sudo systemctl status nginx

# 检查端口监听
sudo netstat -tlnp | grep :80

# 查看NGINX错误日志
sudo tail -f /var/log/nginx/error.log
```

### 3. 静态文件无法访问

```bash
# 检查文件权限
ls -la /opt/jinrongka2/static/

# 检查NGINX用户权限
sudo -u www-data ls -la /opt/jinrongka2/static/
```

## 安全建议

1. **防火墙配置**
```bash
# 只开放必要端口
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS (如果需要)
sudo ufw enable
```

2. **SSL证书配置**（可选）
```bash
# 使用Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d hf.ztdj888.vip
```

3. **定期备份**
```bash
# 备份数据库
cp /opt/jinrongka2/database.db /backup/database_$(date +%Y%m%d).db

# 备份上传文件
tar -czf /backup/uploads_$(date +%Y%m%d).tar.gz /opt/jinrongka2/static/uploads/
```

## 性能优化

1. **启用Gzip压缩**（已在NGINX配置中启用）
2. **设置静态文件缓存**（已在NGINX配置中设置）
3. **配置连接保持**（已在NGINX配置中设置）
4. **监控系统资源**

```bash
# 监控系统资源
htop
df -h
free -h
```
