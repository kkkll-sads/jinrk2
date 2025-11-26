from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from logging.handlers import RotatingFileHandler
import os

from config import Config
from models.database import init_db, DatabasePool
from routes.main import main
from routes.api import api

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 确保必要目录存在
    os.makedirs('logs', exist_ok=True)
    os.makedirs(app.config['UPLOAD_DIR'], exist_ok=True)
    
    # 配置限流器
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=app.config['RATELIMIT_DEFAULT'],
        storage_uri=app.config['RATELIMIT_STORAGE_URL']
    )
    
    # 配置日志
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240000, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    
    # 注册蓝图
    app.register_blueprint(main)
    app.register_blueprint(api, url_prefix='/api')
    
    with app.app_context():
        app.logger.info('金融卡服务系统启动')
        # 初始化数据库
        init_db()
    
    return app

# 全局变量
db_pool = None

def init_pool():
    """初始化数据库连接池"""
    global db_pool
    if db_pool is None:
        db_pool = DatabasePool(max_connections=Config.DB_MAX_CONNECTIONS)

if __name__ == '__main__':
    app = create_app()
    init_pool()
    app.run(host='0.0.0.0', port=8003, debug=True, use_reloader=False) 