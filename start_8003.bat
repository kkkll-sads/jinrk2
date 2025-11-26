@echo off
echo 启动金融卡服务系统 - 端口8003
echo ================================

REM 设置环境变量
set HOST=0.0.0.0
set PORT=8003
set FLASK_ENV=production

REM 切换到项目目录
cd /d "%~dp0"

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python环境，请先安装Python
    pause
    exit /b 1
)

REM 检查依赖
if not exist "requirements.txt" (
    echo 错误: 未找到requirements.txt文件
    pause
    exit /b 1
)

REM 安装依赖（如果需要）
echo 检查并安装依赖...
pip install -r requirements.txt

REM 启动应用
echo 启动应用在端口8003...
echo 访问地址: http://localhost:8003
echo 域名访问: http://hf.ztdj888.vip (需要配置NGINX)
echo.
echo 按 Ctrl+C 停止服务
echo ================================

python run.py
