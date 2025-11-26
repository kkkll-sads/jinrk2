# Nginx端口转发配置说明

## 📋 概述

本文档详细说明如何为金融卡服务系统配置Nginx反向代理，实现从80端口到应用8080端口的转发。

## 🎯 配置目标

- **外部访问**: 通过80端口（HTTP）和443端口（HTTPS）
- **内部应用**: 运行在8080端口（仅本地访问）
- **静态文件**: 由Nginx直接提供，提高性能
- **安全性**: 添加安全头和访问控制

## 🚀 快速配置

### 方式一：自动配置（推荐）

```bash
# 1. 给脚本执行权限
chmod +x setup_nginx.sh start_with_nginx.sh

# 2. 运行自动配置脚本
sudo ./setup_nginx.sh

# 3. 启动应用
./start_with_nginx.sh
```

### 方式二：手动配置

#### 1. 安装Nginx

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y nginx
```

**CentOS/RHEL:**
```bash
sudo yum install -y nginx
```

**Fedora:**
```bash
sudo dnf install -y nginx
```

#### 2. 创建配置文件

```bash
sudo nano /etc/nginx/sites-available/financial-card-service
```

将`nginx_config/financial-card-service.conf`的内容复制到配置文件中。

#### 3. 启用配置

```bash
# 删除默认配置
sudo rm /etc/nginx/sites-enabled/default

# 启用新配置
sudo ln -s /etc/nginx/sites-available/financial-card-service /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重启Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

## 📁 配置文件说明

### 核心配置结构

```nginx
# 上游服务器（后端应用）
upstream financial_card_backend {
    server 127.0.0.1:8080;  # 应用运行在8080端口
    keepalive 32;           # 保持连接池
}

server {
    listen 80;              # 监听80端口
    server_name your-domain.com;
    
    # 代理到后端应用
    location / {
        proxy_pass http://financial_card_backend;
        # 设置代理头...
    }
    
    # 静态文件直接提供
    location /static/ {
        alias /path/to/project/static/;
        # 缓存设置...
    }
}
```

### 关键配置说明

#### 1. 端口转发
```nginx
# 外部80端口 → 内部8080端口
listen 80;
proxy_pass http://financial_card_backend;
```

#### 2. 静态文件优化
```nginx
location /static/ {
    alias /opt/financial-card-service/static/;
    expires 1d;                              # 1天缓存
    add_header Cache-Control "public, immutable";
    gzip_static on;                          # 静态压缩
}
```

#### 3. 安全头设置
```nginx
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
add_header Referrer-Policy "strict-origin-when-cross-origin";
```

#### 4. 上传文件处理
```nginx
location /static/uploads/ {
    alias /opt/financial-card-service/static/uploads/;
    
    # 只允许特定文件类型
    location ~* \.(jpg|jpeg|png|gif|pdf|doc|docx|xls|xlsx)$ {
        add_header X-Content-Type-Options nosniff;
    }
    
    # 禁止脚本执行
    location ~* \.(php|asp|aspx|jsp|py|pl|sh)$ {
        deny all;
    }
}
```

#### 5. 视频文件处理
```nginx
location /static/replays/ {
    alias /opt/financial-card-service/static/replays/;
    
    location ~* \.(mp4|webm|ogg|avi|mov|wmv|flv)$ {
        add_header Accept-Ranges bytes;  # 支持断点续传
    }
}
```

## 🔧 应用配置调整

### 修改启动参数

使用`start_with_nginx.sh`脚本，它会设置：

```bash
export HOST=127.0.0.1  # 只监听本地
export PORT=8080       # 使用8080端口
```

这样配置的好处：
- **安全性**: 应用只能本地访问
- **权限**: 不需要root权限运行应用
- **性能**: Nginx处理静态文件和连接管理

## 🛡️ 安全配置

### 1. 文件访问控制

```nginx
# 禁止访问敏感文件
location ~* \.(py|pyc|pyo|db|sqlite|log|conf|ini|bak|backup)$ {
    deny all;
}

# 禁止访问隐藏文件
location ~* /\. {
    deny all;
}

# 禁止访问临时目录
location /temp/ {
    deny all;
}
```

### 2. 请求大小限制

```nginx
client_max_body_size 100M;  # 最大上传100MB
```

### 3. 超时设置

```nginx
proxy_connect_timeout 300;
proxy_send_timeout 300;
proxy_read_timeout 300;
send_timeout 300;
```

## 📊 性能优化

### 1. Gzip压缩

```nginx
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_types
    text/plain
    text/css
    text/xml
    text/javascript
    application/javascript
    application/json;
```

### 2. 缓存设置

```nginx
# 静态资源长期缓存
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}

# 上传文件短期缓存
location /static/uploads/ {
    expires 7d;
    add_header Cache-Control "public";
}
```

### 3. 连接优化

```nginx
upstream financial_card_backend {
    server 127.0.0.1:8080;
    keepalive 32;          # 保持连接池
}

proxy_http_version 1.1;
proxy_set_header Connection "";
```

## 🔍 监控和日志

### 1. 日志配置

```nginx
access_log /var/log/nginx/financial-card-access.log;
error_log /var/log/nginx/financial-card-error.log;
```

### 2. 实时监控

```bash
# 查看访问日志
sudo tail -f /var/log/nginx/financial-card-access.log

# 查看错误日志
sudo tail -f /var/log/nginx/financial-card-error.log

# 查看应用日志
tail -f logs/app.log

# 检查Nginx状态
sudo systemctl status nginx

# 检查端口占用
sudo netstat -tlnp | grep :80
sudo netstat -tlnp | grep :8080
```

## 🔒 SSL/HTTPS配置

### 1. 安装Certbot

**Ubuntu/Debian:**
```bash
sudo apt-get install certbot python3-certbot-nginx
```

**CentOS/RHEL:**
```bash
sudo yum install certbot python3-certbot-nginx
```

### 2. 获取SSL证书

```bash
sudo certbot --nginx -d your-domain.com
```

### 3. 自动续期

```bash
# 添加到crontab
sudo crontab -e

# 添加这行（每天检查续期）
0 12 * * * /usr/bin/certbot renew --quiet
```

## 🆘 故障排除

### 1. 端口冲突

```bash
# 检查端口占用
sudo netstat -tlnp | grep :80
sudo netstat -tlnp | grep :8080

# 杀死占用进程
sudo kill -9 <PID>
```

### 2. 权限问题

```bash
# 设置正确的文件权限
sudo chown -R www-data:www-data /opt/financial-card-service
sudo chmod -R 755 /opt/financial-card-service
```

### 3. 配置测试

```bash
# 测试Nginx配置
sudo nginx -t

# 重新加载配置
sudo nginx -s reload

# 重启Nginx
sudo systemctl restart nginx
```

### 4. 防火墙问题

```bash
# Ubuntu
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# CentOS/RHEL/Fedora
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## 📈 性能测试

### 1. 基准测试

```bash
# 安装测试工具
sudo apt-get install apache2-utils

# 并发测试
ab -n 1000 -c 10 http://your-server-ip/

# 压力测试
ab -n 10000 -c 100 http://your-server-ip/
```

### 2. 监控指标

- **响应时间**: 应该在100ms以内
- **并发连接**: 根据服务器配置调整
- **内存使用**: 监控Nginx和应用内存占用
- **CPU使用**: 高并发时的CPU负载

## 📝 维护建议

### 1. 定期检查

- 每周检查日志文件大小
- 每月检查SSL证书有效期
- 定期更新Nginx版本

### 2. 备份配置

```bash
# 备份Nginx配置
sudo cp /etc/nginx/sites-available/financial-card-service /backup/

# 备份SSL证书
sudo cp -r /etc/letsencrypt /backup/
```

### 3. 性能调优

根据访问量调整：
- `worker_processes` 数量
- `worker_connections` 数量
- 缓存大小和时间
- 超时设置

通过以上配置，你的金融卡服务系统将获得更好的性能、安全性和可维护性。 