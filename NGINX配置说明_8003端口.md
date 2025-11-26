# 金融卡服务系统 - NGINX配置说明 (8003端口)

## 配置概述

本配置将金融卡服务系统运行在8003端口，并通过NGINX绑定域名 `hf.ztdj888.vip` 进行访问。

## 文件说明

### 1. 应用配置文件
- `run.py` - 主启动文件，已配置为8003端口
- `app.py` - 应用入口，已配置为8003端口
- `start_8003.bat` - Windows启动脚本

### 2. NGINX配置文件
- `nginx_config/financial-card-service-windows.conf` - Windows NGINX配置
- `nginx_config/financial-card-service.conf` - Linux NGINX配置

## 配置步骤

### 步骤1: 启动应用
```bash
# Windows
start_8003.bat

# 或直接运行
python run.py
```

应用将在 `http://localhost:8003` 启动

### 步骤2: 配置NGINX

#### Windows NGINX配置
1. 将 `nginx_config/financial-card-service-windows.conf` 复制到NGINX配置目录
2. 修改NGINX主配置文件 `nginx.conf`，在http块中添加：
```nginx
include conf.d/financial-card-service-windows.conf;
```

#### Linux NGINX配置
1. 将配置文件复制到 `/etc/nginx/sites-available/`
```bash
sudo cp nginx_config/financial-card-service.conf /etc/nginx/sites-available/
```

2. 创建软链接到sites-enabled
```bash
sudo ln -s /etc/nginx/sites-available/financial-card-service.conf /etc/nginx/sites-enabled/
```

3. 测试配置
```bash
sudo nginx -t
```

4. 重启NGINX
```bash
sudo systemctl restart nginx
```

### 步骤3: 域名配置

确保域名 `hf.ztdj888.vip` 的DNS记录指向您的服务器IP地址。

## 访问地址

- 直接访问: `http://localhost:8003`
- 域名访问: `http://hf.ztdj888.vip`

## 配置要点

### 1. 端口配置
- 应用端口: 8003
- NGINX监听端口: 80
- 上游服务器: 127.0.0.1:8003

### 2. 静态文件路径
- Windows: `D:/SY IT-System/User/Desktop/pypo/jinrongka2/static/`
- Linux: `/opt/financial-card-service/static/`

### 3. 安全配置
- 禁止访问敏感文件 (.py, .db, .log等)
- 设置安全头
- 限制文件上传类型

## 故障排除

### 1. 应用无法启动
- 检查端口8003是否被占用
- 检查Python依赖是否安装完整
- 查看应用日志文件

### 2. NGINX无法访问
- 检查NGINX配置语法: `nginx -t`
- 检查NGINX是否运行: `nginx -s status`
- 查看NGINX错误日志

### 3. 域名无法访问
- 检查DNS解析是否正确
- 检查防火墙设置
- 确认域名已正确配置

## 日志文件

- 应用日志: `logs/app.log`
- NGINX访问日志: `logs/financial-card-access.log`
- NGINX错误日志: `logs/financial-card-error.log`

## 性能优化

1. 启用Gzip压缩
2. 设置静态文件缓存
3. 配置连接保持
4. 设置适当的缓冲区大小

## 安全建议

1. 定期更新SSL证书（如果使用HTTPS）
2. 监控访问日志
3. 设置访问频率限制
4. 定期备份数据库
