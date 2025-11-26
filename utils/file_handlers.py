import os
import time
import json
import logging
import mimetypes
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class FileHandler:
    # 允许的文件类型
    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif'}
    # 目录大小限制（字节）
    MAX_TEMP_DIR_SIZE = 100 * 1024 * 1024  # 100MB
    MAX_UPLOAD_DIR_SIZE = 1024 * 1024 * 1024  # 1GB
    
    _instance = None
    
    def __new__(cls, base_dir=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, base_dir=None):
        if not hasattr(self, 'initialized'):
            self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.upload_dir = os.path.join(self.base_dir, 'static', 'uploads')
            self.temp_dir = os.path.join(self.base_dir, 'temp')
            self.log_dir = os.path.join(self.base_dir, 'logs')
            self._ensure_directories()
            self.initialized = True

    def _ensure_directories(self):
        """确保必要的目录存在"""
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

    def _get_directory_size(self, directory):
        """获取目录总大小"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                total_size += os.path.getsize(filepath)
        return total_size

    def _check_directory_size(self, directory, max_size):
        """检查目录大小是否超过限制"""
        current_size = self._get_directory_size(directory)
        return current_size <= max_size

    def _is_safe_file_type(self, file, allowed_types=None):
        """检查文件类型是否安全"""
        if not file or not file.filename:
            return False
            
        # 获取文件的MIME类型
        mime_type = mimetypes.guess_type(file.filename)[0]
        if not mime_type:
            return False
            
        # 如果没有指定允许的类型，使用默认的图片类型
        allowed_types = allowed_types or self.ALLOWED_IMAGE_TYPES
        return mime_type.lower() in allowed_types

    def save_failed_records(self, import_type, failed_records):
        """保存失败记录到临时文件"""
        try:
            # 检查临时目录大小
            if not self._check_directory_size(self.temp_dir, self.MAX_TEMP_DIR_SIZE):
                logger.warning("临时目录空间不足，清理旧文件")
                self.cleanup_old_temp_files(hours=1)
                
            # 如果清理后仍然超过限制，返回错误
            if not self._check_directory_size(self.temp_dir, self.MAX_TEMP_DIR_SIZE):
                logger.error("临时目录空间不足，无法保存失败记录")
                return None
            
            # 生成安全的文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = secure_filename(f"{import_type}_{timestamp}.json")
            filepath = os.path.join(self.temp_dir, filename)
            
            # 保存失败记录
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(failed_records, f, ensure_ascii=False, indent=2)
            
            logger.info(f"保存失败记录成功: {filename}")
            return filename
        except Exception as e:
            logger.error(f"保存失败记录失败: {str(e)}")
            return None

    def get_failed_records(self, import_type):
        """从临时目录获取最新的失败记录"""
        try:
            # 获取指定类型的所有失败记录文件
            files = [f for f in os.listdir(self.temp_dir) 
                    if f.startswith(f"{import_type}_") and f.endswith('.json')]
            
            if not files:
                return None
                
            # 按文件名排序（因为包含时间戳，所以最新的文件会排在最后）
            files.sort()
            latest_file = files[-1]
            
            # 读取最新的失败记录文件
            filepath = os.path.join(self.temp_dir, latest_file)
            if not os.path.exists(filepath):
                return None
                
            # 检查文件是否过期（1小时）
            file_modified_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            if datetime.now() - file_modified_time > timedelta(hours=1):
                # 删除过期文件
                os.remove(filepath)
                logger.info(f"删除过期失败记录: {latest_file}")
                return None
                
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"获取失败记录失败: {str(e)}")
            return None

    def save_upload_file(self, file, prefix, file_type='jpg', max_size_mb=5):
        """保存上传的文件"""
        if not file:
            return None
            
        try:
            # 检查文件类型
            if not self._is_safe_file_type(file):
                logger.warning(f"不安全的文件类型: {file.filename}")
                raise ValueError("不支持的文件类型")
            
            # 检查文件大小
            file_size = len(file.read())
            file.seek(0)  # 重置文件指针
            if file_size > max_size_mb * 1024 * 1024:
                raise ValueError(f"文件大小超过限制 ({max_size_mb}MB)")
            
            # 检查上传目录大小
            if not self._check_directory_size(self.upload_dir, self.MAX_UPLOAD_DIR_SIZE):
                logger.warning("上传目录空间不足，清理旧文件")
                self.cleanup_old_uploads(days=30)
                
            if not self._check_directory_size(self.upload_dir, self.MAX_UPLOAD_DIR_SIZE):
                logger.error("上传目录空间不足，无法保存文件")
                raise ValueError("服务器存储空间不足")
                
            # 生成安全的文件名
            original_filename = secure_filename(file.filename)
            filename = f"{prefix}_{int(time.time())}_{original_filename}"
            filepath = os.path.join(self.upload_dir, filename)
            
            file.save(filepath)
            logger.info(f"保存上传文件成功: {filename}")
            return os.path.join('uploads', filename)
        except Exception as e:
            logger.error(f"保存文件失败: {str(e)}")
            return None

    def delete_file(self, relative_path):
        """删除文件"""
        if not relative_path:
            return
            
        try:
            # 确保文件路径安全
            filename = os.path.basename(relative_path)
            safe_filename = secure_filename(filename)
            if filename != safe_filename:
                logger.warning(f"不安全的文件名: {filename}")
                return
                
            full_path = os.path.join(self.base_dir, 'static', relative_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                logger.info(f"删除文件成功: {full_path}")
        except Exception as e:
            logger.error(f"删除文件失败: {str(e)}")

    def save_temp_file(self, content, prefix, suffix='.json'):
        """保存临时文件"""
        try:
            # 检查临时目录大小
            if not self._check_directory_size(self.temp_dir, self.MAX_TEMP_DIR_SIZE):
                logger.warning("临时目录空间不足，清理旧文件")
                self.cleanup_old_temp_files(hours=1)
                
            if not self._check_directory_size(self.temp_dir, self.MAX_TEMP_DIR_SIZE):
                logger.error("临时目录空间不足，无法保存文件")
                return None
                
            # 生成安全的文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = secure_filename(f"{prefix}_{timestamp}{suffix}")
            filepath = os.path.join(self.temp_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.info(f"保存临时文件成功: {filename}")
            return filename
        except Exception as e:
            logger.error(f"保存临时文件失败: {str(e)}")
            return None

    def read_temp_file(self, filename):
        """读取临时文件"""
        try:
            # 确保文件名安全
            safe_filename = secure_filename(filename)
            if filename != safe_filename:
                logger.warning(f"不安全的文件名: {filename}")
                return None
                
            filepath = os.path.join(self.temp_dir, filename)
            if not os.path.exists(filepath):
                return None
                
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取临时文件失败: {str(e)}")
            return None

    def delete_temp_file(self, filename):
        """删除临时文件"""
        try:
            # 确保文件名安全
            safe_filename = secure_filename(filename)
            if filename != safe_filename:
                logger.warning(f"不安全的文件名: {filename}")
                return
                
            filepath = os.path.join(self.temp_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"删除临时文件成功: {filepath}")
        except Exception as e:
            logger.error(f"删除临时文件失败: {str(e)}")

    def cleanup_old_temp_files(self, hours=1):
        """清理过期的临时文件"""
        try:
            current_time = datetime.now()
            for filename in os.listdir(self.temp_dir):
                filepath = os.path.join(self.temp_dir, filename)
                file_modified_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if current_time - file_modified_time > timedelta(hours=hours):
                    os.remove(filepath)
                    logger.info(f"清理过期文件: {filepath}")
        except Exception as e:
            logger.error(f"清理临时文件失败: {str(e)}")

    def cleanup_old_uploads(self, days=30):
        """清理过期的上传文件"""
        try:
            current_time = datetime.now()
            for filename in os.listdir(self.upload_dir):
                filepath = os.path.join(self.upload_dir, filename)
                file_modified_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if current_time - file_modified_time > timedelta(days=days):
                    os.remove(filepath)
                    logger.info(f"清理过期上传文件: {filepath}")
        except Exception as e:
            logger.error(f"清理上传文件失败: {str(e)}")

    def get_file_path(self, relative_path):
        """获取文件的完整路径"""
        filename = os.path.basename(relative_path)
        safe_filename = secure_filename(filename)
        if filename != safe_filename:
            logger.warning(f"不安全的文件名: {filename}")
            return None
        return os.path.join(self.base_dir, 'static', relative_path) 