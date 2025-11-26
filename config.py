import os
import logging.config
from datetime import timedelta

class Config:
    # 基础配置
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SECRET_KEY = os.getenv('SECRET_KEY', '+Dm2%3;|;9%v')
    
    # 目录配置
    UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
    TEMP_DIR = os.path.join(BASE_DIR, 'temp')
    LOG_DIR = os.path.join(BASE_DIR, 'logs')
    
    # 数据库配置
    DATABASE_PATH = os.path.join(BASE_DIR, 'database.db')
    DB_TIMEOUT = 60
    DB_MAX_CONNECTIONS = 5
    
    # 限流器配置
    RATELIMIT_DEFAULT = ["200 per day", "50 per hour"]
    RATELIMIT_STORAGE_URL = "memory://"
    
    # 文件大小限制
    MAX_TEMP_DIR_SIZE = 100 * 1024 * 1024  # 100MB
    MAX_UPLOAD_DIR_SIZE = 1024 * 1024 * 1024  # 1GB
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    
    # 文件类型
    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif'}
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}
    
    # 清理配置
    TEMP_FILE_LIFETIME = timedelta(hours=1)
    UPLOAD_FILE_LIFETIME = timedelta(days=30)
    
    # 日志配置
    LOGGING_CONFIG = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
            'detailed': {
                'format': '%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d]: %(message)s'
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                'formatter': 'standard',
                'stream': 'ext://sys.stdout'
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'INFO',
                'formatter': 'detailed',
                'filename': os.path.join(LOG_DIR, 'app.log'),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5,
                'encoding': 'utf8'
            },
            'error_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'ERROR',
                'formatter': 'detailed',
                'filename': os.path.join(LOG_DIR, 'error.log'),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5,
                'encoding': 'utf8'
            },
        },
        'loggers': {
            '': {  # root logger
                'handlers': ['console', 'file', 'error_file'],
                'level': 'INFO',
                'propagate': True
            },
            'werkzeug': {  # Flask's logger
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': False
            },
        }
    }
    
    @classmethod
    def init_app(cls, app):
        """初始化应用配置"""
        # 确保必要的目录存在
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        os.makedirs(cls.TEMP_DIR, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)
        
        # 配置日志
        logging.config.dictConfig(cls.LOGGING_CONFIG)
        
        # 配置 Flask
        app.config.from_object(cls)
        
        # 初始化其他配置
        return app

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    # 使用内存数据库进行测试
    DATABASE_PATH = ':memory:'

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    # 生产环境应该使用环境变量设置密钥
    SECRET_KEY = os.getenv('SECRET_KEY')

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 