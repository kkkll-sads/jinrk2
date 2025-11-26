from functools import wraps
from flask import request, jsonify
import time
from collections import defaultdict
import threading
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, max_requests=60, time_window=60):
        self.max_requests = max_requests  # 最大请求次数
        self.time_window = time_window    # 时间窗口（秒）
        self.requests = defaultdict(list)  # 记录请求时间
        self.lock = threading.Lock()      # 线程锁
        
    def is_allowed(self, key):
        """检查是否允许请求"""
        with self.lock:
            now = time.time()
            
            # 清理过期的请求记录
            self.requests[key] = [req_time for req_time in self.requests[key]
                                if now - req_time < self.time_window]
            
            # 检查是否超过限制
            if len(self.requests[key]) >= self.max_requests:
                return False
            
            # 记录新的请求
            self.requests[key].append(now)
            return True
            
    def get_remaining(self, key):
        """获取剩余可用请求次数"""
        with self.lock:
            now = time.time()
            valid_requests = [req_time for req_time in self.requests[key]
                            if now - req_time < self.time_window]
            return max(0, self.max_requests - len(valid_requests))
            
    def get_reset_time(self, key):
        """获取限制重置时间"""
        with self.lock:
            if not self.requests[key]:
                return 0
            oldest_request = min(self.requests[key])
            return max(0, self.time_window - (time.time() - oldest_request))

# 全局限流器实例
default_limiter = RateLimiter()

def rate_limit(max_requests=60, time_window=60, key_func=None):
    """
    请求频率限制装饰器
    :param max_requests: 时间窗口内最大请求次数
    :param time_window: 时间窗口（秒）
    :param key_func: 自定义键生成函数，默认使用IP地址
    """
    limiter = RateLimiter(max_requests, time_window)
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 获取限流键
            if key_func:
                key = key_func()
            else:
                key = request.remote_addr
                
            # 检查是否允许请求
            if not limiter.is_allowed(key):
                remaining = limiter.get_remaining(key)
                reset_time = limiter.get_reset_time(key)
                
                logger.warning(f"请求频率超限: IP={key}, 剩余={remaining}, 重置时间={reset_time}秒")
                
                response = jsonify({
                    'error': '请求过于频繁，请稍后再试',
                    'remaining': remaining,
                    'reset_time': reset_time
                })
                response.headers['X-RateLimit-Remaining'] = str(remaining)
                response.headers['X-RateLimit-Reset'] = str(int(time.time() + reset_time))
                return response, 429
            
            # 添加限流信息到响应头
            response = f(*args, **kwargs)
            if isinstance(response, tuple):
                response, status_code = response
            else:
                status_code = 200
                
            if hasattr(response, 'headers'):
                remaining = limiter.get_remaining(key)
                reset_time = limiter.get_reset_time(key)
                response.headers['X-RateLimit-Remaining'] = str(remaining)
                response.headers['X-RateLimit-Reset'] = str(int(time.time() + reset_time))
            
            return response if isinstance(response, tuple) else (response, status_code)
            
        return decorated_function
    return decorator

# 针对特定API的限流装饰器
def api_rate_limit(max_requests=10, time_window=60):
    """API特定的频率限制装饰器"""
    return rate_limit(max_requests, time_window)

# 针对文件上传的限流装饰器
def upload_rate_limit(max_requests=5, time_window=60):
    """文件上传的频率限制装饰器"""
    return rate_limit(max_requests, time_window) 