from functools import wraps
from models.database import DatabasePool
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def with_db_connection(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 获取数据库连接池单例实例
        pool = DatabasePool()
        conn = None
        try:
            # 获取连接
            conn = pool.get_connection()
            if not conn:
                logger.error("无法获取数据库连接")
                raise Exception("数据库连接失败")
            
            # 开始事务
            conn.execute("BEGIN")
            
            # 将连接传递给目标函数
            result = f(*args, conn=conn, **kwargs)
            
            # 如果没有异常，提交事务
            conn.commit()
            logger.info("数据库事务提交成功")
            
            return result
        except Exception as e:
            # 如果发生异常，回滚事务
            logger.error(f"数据库操作失败: {str(e)}")
            if conn:
                try:
                    conn.rollback()
                    logger.info("数据库事务已回滚")
                except Exception as rollback_error:
                    logger.error(f"事务回滚失败: {str(rollback_error)}")
            raise
        finally:
            # 确保连接被归还到连接池
            if conn:
                try:
                    pool.return_connection(conn)
                    logger.info("数据库连接已归还到连接池")
                except Exception as return_error:
                    logger.error(f"归还连接到连接池失败: {str(return_error)}")
    
    return decorated_function 