# 金融卡服务系统 - Linux部署指南

## 系统要求

- Linux操作系统（Ubuntu 18.04+, CentOS 7+, RHEL 7+, Fedora 30+等）
- Python 3.7+
- 至少2GB RAM
- 至少1GB可用磁盘空间

## 从Windows迁移到Linux的变更说明

本项目原本在Windows服务器上运行，现已适配Linux系统。主要变更如下：

### 1. 启动脚本变更
- **Windows**: `start.bat`, `run.bat`
- **Linux**: `start.sh`, `run_linux.sh`, `install_linux.sh`

### 2. 路径分隔符
- 代码中使用`os.path.join()`确保跨平台兼容性
- 目录创建改用Linux风格的`/`分隔符

### 3. 系统依赖
- 添加了ffmpeg支持（MoviePy需要）
- 包含了各种Linux发行版的包管理器支持

## 快速部署

### 1. 自动安装（推荐）

```bash
# 1. 克隆或复制项目文件到Linux服务器
# 2. 给脚本执行权限
chmod +x install_linux.sh start.sh run_linux.sh

# 3. 运行安装脚本
./install_linux.sh
```

### 2. 手动安装

#### 2.1 安装系统依赖

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv python3-dev
sudo apt-get install -y libffi-dev libssl-dev build-essential ffmpeg
```

**CentOS/RHEL:**
```bash
sudo yum update -y
sudo yum install -y python3 python3-pip python3-devel
sudo yum install -y libffi-devel openssl-devel gcc
sudo yum install -y epel-release
sudo yum install -y ffmpeg
```

**Fedora:**
```bash
sudo dnf update -y
sudo dnf install -y python3 python3-pip python3-devel
sudo dnf install -y libffi-devel openssl-devel gcc ffmpeg
```

#### 2.2 安装Python依赖

```bash
# 升级pip
python3 -m pip install --upgrade pip

# 安装项目依赖
python3 -m pip install -r requirements.txt
```

#### 2.3 创建虚拟环境（推荐）

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 运行应用

### 开发环境

```bash
# 方式1：使用脚本
./run_linux.sh

# 方式2：直接运行
python3 run.py
```

### 生产环境

```bash
# 使用80端口需要root权限
sudo ./start.sh

# 或者修改端口（推荐使用反向代理）
export PORT=8080
./start.sh
```

## 服务配置

### 1. 使用systemd服务（推荐）

创建服务文件：
```bash
sudo nano /etc/systemd/system/financial-card-service.service
```

服务文件内容：
```ini
[Unit]
Description=Financial Card Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/your/project
Environment=PATH=/path/to/your/project/venv/bin
Environment=FLASK_ENV=production
Environment=SECRET_KEY=+Dm2%%%%3;|;9%%%%v
Environment=PORT=8080
ExecStart=/path/to/your/project/venv/bin/python run.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable financial-card-service
sudo systemctl start financial-card-service
sudo systemctl status financial-card-service
```

### 2. 使用Nginx反向代理

安装Nginx：
```bash
# Ubuntu/Debian
sudo apt-get install nginx

# CentOS/RHEL
sudo yum install nginx
```

配置文件 `/etc/nginx/sites-available/financial-card-service`：
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 增加超时时间
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }

    # 静态文件直接由Nginx提供
    location /static {
        alias /path/to/your/project/static;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/financial-card-service /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 防火墙配置

### UFW (Ubuntu)
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Firewalld (CentOS/RHEL/Fedora)
```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## 数据迁移

从Windows迁移数据：

1. **数据库文件**: 复制 `database.db`, `order_checker.db` 等SQLite文件
2. **上传文件**: 复制 `static/uploads/` 目录下的所有文件
3. **回放视频**: 复制 `static/replays/` 目录下的所有文件
4. **日志文件**: 可选择性复制 `logs/` 目录

## 监控和日志

### 查看应用日志
```bash
# 实时查看日志
tail -f logs/app.log

# 查看系统服务日志
sudo journalctl -u financial-card-service -f
```

### 监控系统资源
```bash
# 安装htop
sudo apt-get install htop  # Ubuntu/Debian
sudo yum install htop      # CentOS/RHEL

# 监控
htop
```

## 故障排除

### 1. 权限问题
```bash
# 确保目录权限正确
sudo chown -R www-data:www-data /path/to/your/project
sudo chmod -R 755 /path/to/your/project
```

### 2. 端口占用
```bash
# 查看端口占用
sudo netstat -tlnp | grep :80
sudo lsof -i :80

# 杀死占用进程
sudo kill -9 <PID>
```

### 3. Python版本问题
```bash
# 检查Python版本
python3 --version
which python3

# 安装特定版本
sudo apt-get install python3.8  # Ubuntu/Debian
```

### 4. 依赖安装失败
```bash
# 清理pip缓存
pip cache purge

# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

## 性能优化

### 1. 使用Gunicorn（替代内置服务器）
```bash
# 安装Gunicorn
pip install gunicorn

# 运行
gunicorn -w 4 -b 0.0.0.0:8080 run:app
```

### 2. 数据库优化
- 定期清理日志文件
- 优化SQLite查询
- 考虑升级到PostgreSQL或MySQL

### 3. 静态文件缓存
- 使用Nginx提供静态文件
- 启用Gzip压缩
- 设置适当的缓存头

## 安全建议

1. **防火墙**: 只开放必要端口
2. **SSL/TLS**: 使用Let's Encrypt配置HTTPS
3. **密钥管理**: 使用环境变量存储敏感信息
4. **用户权限**: 使用非root用户运行应用
5. **定期更新**: 保持系统和依赖包更新

## 备份策略

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/backup/financial-card-service"
APP_DIR="/path/to/your/project"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# 备份数据库
cp $APP_DIR/*.db $BACKUP_DIR/database_$DATE.db

# 备份上传文件
tar -czf $BACKUP_DIR/uploads_$DATE.tar.gz -C $APP_DIR static/uploads

# 备份配置文件
cp $APP_DIR/config.py $BACKUP_DIR/config_$DATE.py

# 清理7天前的备份
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
find $BACKUP_DIR -name "*.py" -mtime +7 -delete
```

## 联系支持

如果在迁移过程中遇到问题，请检查：
1. 日志文件 `logs/app.log`
2. 系统日志 `sudo journalctl -u financial-card-service`
3. Python错误信息
4. 网络连接和防火墙设置 