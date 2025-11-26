from flask import Flask
from routes.main import main
from models.database import init_db
from utils.scheduler import init_scheduler
import logging
import os
from logging.handlers import RotatingFileHandler

def create_app():
    app = Flask(__name__)
    
    # 设置密钥
    app.secret_key = os.environ.get('SECRET_KEY', '+Dm2%3;|;9%v')
    
    # 注册蓝图（避免重复注册）
    if 'main' not in app.blueprints:
        app.register_blueprint(main)
    
    # 确保日志目录存在
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 配置日志
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 文件处理器 - 使用 RotatingFileHandler
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 配置 Flask 应用的日志记录器
    app.logger.setLevel(logging.INFO)
    if not app.logger.handlers:
        app.logger.addHandler(file_handler)
        app.logger.addHandler(console_handler)
    
    app.logger.info('金融卡服务系统启动')
    
    # 初始化数据库
    init_db()
    
    # 初始化调度器
    init_scheduler()
    
    return app

if __name__ == '__main__':
    app = create_app()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 8003))
    app.run(host=host, port=port) 