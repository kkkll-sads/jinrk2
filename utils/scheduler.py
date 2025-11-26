from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import logging
from datetime import datetime
from utils.file_handlers import FileHandler
from config import Config

logger = logging.getLogger(__name__)

class TaskScheduler:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.scheduler = BackgroundScheduler()
            self.file_handler = FileHandler()
            self.initialized = True
            self._setup_jobs()
    
    def _setup_jobs(self):
        """设置定时任务"""
        try:
            # 每小时清理临时文件
            self.scheduler.add_job(
                self._cleanup_temp_files,
                CronTrigger(minute=0),  # 每小时执行一次
                id='cleanup_temp_files',
                replace_existing=True,
                misfire_grace_time=3600  # 允许1小时的任务延迟
            )
            
            # 每天凌晨3点清理过期的上传文件
            self.scheduler.add_job(
                self._cleanup_old_uploads,
                CronTrigger(hour=3),  # 每天凌晨3点执行
                id='cleanup_uploads',
                replace_existing=True,
                misfire_grace_time=3600  # 允许1小时的任务延迟
            )
            
            # 每5分钟检查一次目录大小
            self.scheduler.add_job(
                self._check_directory_sizes,
                IntervalTrigger(minutes=5),
                id='check_directory_sizes',
                replace_existing=True
            )
            
            logger.info("定时任务已设置")
            
        except Exception as e:
            logger.error(f"设置定时任务失败: {str(e)}")
            raise
    
    def _cleanup_temp_files(self):
        """清理临时文件"""
        try:
            logger.info("开始清理临时文件...")
            self.file_handler.cleanup_old_temp_files(
                hours=Config.TEMP_FILE_LIFETIME.total_seconds() / 3600
            )
            logger.info("临时文件清理完成")
        except Exception as e:
            logger.error(f"清理临时文件失败: {str(e)}")
    
    def _cleanup_old_uploads(self):
        """清理过期的上传文件"""
        try:
            logger.info("开始清理过期上传文件...")
            self.file_handler.cleanup_old_uploads(
                days=Config.UPLOAD_FILE_LIFETIME.days
            )
            logger.info("过期上传文件清理完成")
        except Exception as e:
            logger.error(f"清理上传文件失败: {str(e)}")
    
    def _check_directory_sizes(self):
        """检查目录大小"""
        try:
            # 检查临时目录
            temp_size = self.file_handler._get_directory_size(self.file_handler.temp_dir)
            if temp_size > Config.MAX_TEMP_DIR_SIZE * 0.9:  # 90%警告阈值
                logger.warning(f"临时目录使用率超过90%: {temp_size / (1024*1024):.2f}MB")
                self._cleanup_temp_files()
            
            # 检查上传目录
            upload_size = self.file_handler._get_directory_size(self.file_handler.upload_dir)
            if upload_size > Config.MAX_UPLOAD_DIR_SIZE * 0.9:  # 90%警告阈值
                logger.warning(f"上传目录使用率超过90%: {upload_size / (1024*1024):.2f}MB")
                self._cleanup_old_uploads()
                
        except Exception as e:
            logger.error(f"检查目录大小失败: {str(e)}")
    
    def start(self):
        """启动调度器"""
        try:
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("调度器已启动")
            else:
                logger.info("调度器已经在运行中")
        except Exception as e:
            logger.error(f"启动调度器失败: {str(e)}")
            raise
    
    def shutdown(self):
        """关闭调度器"""
        try:
            self.scheduler.shutdown()
            logger.info("调度器已关闭")
        except Exception as e:
            logger.error(f"关闭调度器失败: {str(e)}")
            raise
    
    def add_job(self, func, trigger, **kwargs):
        """添加自定义任务"""
        try:
            self.scheduler.add_job(func, trigger, **kwargs)
            logger.info(f"添加任务成功: {func.__name__}")
        except Exception as e:
            logger.error(f"添加任务失败: {str(e)}")
            raise
    
    def remove_job(self, job_id):
        """移除任务"""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"移除任务成功: {job_id}")
        except Exception as e:
            logger.error(f"移除任务失败: {str(e)}")
            raise

def init_scheduler():
    """初始化并启动调度器"""
    scheduler = TaskScheduler()
    scheduler.start()
    return scheduler 