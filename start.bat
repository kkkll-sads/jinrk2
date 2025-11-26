@echo off

rem 修改编码设置方式
chcp 65001
echo 设置UTF-8编码

rem 设置标题
title 金融卡服务系统-生产环境

rem 设置环境变量
set FLASK_ENV=production
set FLASK_DEBUG=0
set "SECRET_KEY=+Dm2%%%%3;|;9%%%%v"
set PYTHONOPTIMIZE=2
set "LOG_LEVEL=INFO"
set "HOST=0.0.0.0"
set "PORT=80"
set "PUBLIC_URL=http://103.164.81.222"
set "WAITRESS_THREADS=32"
set "WAITRESS_CHANNEL_TIMEOUT=300"
set "WAITRESS_CONNECTION_LIMIT=2000"
set "WAITRESS_CLEANUP_INTERVAL=30"
set "WAITRESS_MAX_REQUEST_BODY_SIZE=1073741824"
set "WAITRESS_SOCKET_OPTIONS=SO_REUSEADDR"
set "WAITRESS_OUTBUF_OVERFLOW=104857600"
set "WAITRESS_INBUF_OVERFLOW=52428800"
set "WAITRESS_SEND_BYTES=65536"
set "WAITRESS_RECV_BYTES=65536"
set "WAITRESS_BACKLOG=2048"

rem 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 请以管理员权限运行此脚本（使用80端口需要管理员权限）
    pause
    exit /b 1
)

rem 检查Python是否已安装
where python > nul 2>&1
if %errorlevel% neq 0 (
    echo Python未安装或未添加到PATH环境变量中
    echo 请安装Python并确保将其添加到系统环境变量
    pause
    exit /b 1
)

rem 检查pip是否可用
python -m pip --version > nul 2>&1
if %errorlevel% neq 0 (
    echo pip未安装或不可用
    echo 请确保pip已正确安装
    pause
    exit /b 1
)

rem 创建目录
if not exist "temp" mkdir "temp"
if not exist "logs" mkdir "logs"
if not exist "static\uploads" mkdir "static\uploads"
if not exist "static\replays" mkdir "static\replays"
if not exist "static\replays\thumbnails" mkdir "static\replays\thumbnails"

rem 简化的版本检查，不使用复杂命令
echo 检查Python版本...
python --version
echo Python版本检查完成

rem 清理并重新安装依赖
echo 正在安装核心依赖...
python -m pip install --no-cache-dir numpy==1.23.5
python -m pip install --no-cache-dir pandas==1.5.3
python -m pip install --no-cache-dir moviepy==1.0.3
python -m pip install --no-cache-dir Flask==2.0.1
python -m pip install --no-cache-dir Werkzeug==2.0.1
python -m pip install --no-cache-dir openpyxl==3.0.9
python -m pip install --no-cache-dir backoff==2.1.2
python -m pip install --no-cache-dir APScheduler==3.9.1
python -m pip install --no-cache-dir waitress==2.1.2
python -m pip install --no-cache-dir requests==2.31.0
python -m pip install --no-cache-dir -r requirements.txt

rem 简单创建默认缩略图
if not exist "static\video-placeholder.jpg" (
    echo 创建默认视频缩略图...
    copy "static\uploads\*.jpg" "static\video-placeholder.jpg" > nul 2>&1
    if not exist "static\video-placeholder.jpg" (
        echo 警告：未找到缩略图，创建空白图片...
        echo > "static\video-placeholder.jpg"
    )
)

rem 检查视频文件
echo 检查视频文件...
dir "static\replays\*.mp4" "static\replays\*.webm" > nul 2>&1
if %errorlevel% neq 0 (
    echo 警告：未找到视频文件
    echo 请将视频文件放入 static\replays 目录
)

rem 备份和初始化日志文件
if not exist "logs" mkdir "logs"
if exist "logs\app.log" (
    echo 备份日志文件...
    copy "logs\app.log" "logs\app_backup_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%.log" > nul
    del "logs\app.log"
)
type nul > "logs\app.log"
echo %date% %time% [INFO] 金融卡服务系统启动 > "logs\app.log"

echo 正在启动金融卡服务系统（生产环境）...
echo 应用将在 http://%HOST%:%PORT% 运行
echo 按 Ctrl+C 可以停止服务器

python run.py

if %errorlevel% neq 0 (
    echo 应用启动失败，请检查日志文件
    if exist "logs\app.log" type "logs\app.log"
    pause
    exit /b 1
)

pause