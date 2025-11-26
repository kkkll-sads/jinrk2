import sqlite3
import time
from threading import Lock
import backoff
import logging
from config import Config
import os

# 创建logger
logger = logging.getLogger(__name__)

class DatabasePool:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, max_connections=5):
        if not hasattr(self, 'initialized'):
            self.max_connections = max_connections
            self.connections = []
            self.lock = Lock()
            self.timeout = Config.DB_TIMEOUT
            self.initialized = True
            self._initialize_pool()

    @backoff.on_exception(backoff.expo, 
                         (sqlite3.OperationalError, sqlite3.DatabaseError),
                         max_tries=5)
    def _initialize_pool(self):
        """初始化连接池"""
        try:
            with self.lock:
                for _ in range(self.max_connections):
                    conn = self._create_connection()
                    if conn:
                        self.connections.append(conn)
                logger.info(f"连接池初始化成功，创建了 {len(self.connections)} 个连接")
        except Exception as e:
            logger.error(f"初始化连接池失败: {str(e)}")
            raise

    def _create_connection(self):
        """创建单个数据库连接"""
        try:
            conn = sqlite3.connect(Config.DATABASE_PATH,
                                 check_same_thread=False,
                                 timeout=self.timeout)
            
            # 设置row_factory为sqlite3.Row
            def dict_factory(cursor, row):
                d = {}
                for idx, col in enumerate(cursor.description):
                    d[col[0]] = row[idx]
                return d
            conn.row_factory = dict_factory
            
            # 设置数据库参数
            conn.execute('PRAGMA busy_timeout=60000')
            conn.execute('PRAGMA temp_store=MEMORY')
            conn.execute('PRAGMA cache_size=10000')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA foreign_keys=ON')
            
            # 测试连接
            conn.execute("SELECT 1").fetchone()
            logger.info("创建新的数据库连接成功")
            return conn
        except Exception as e:
            logger.error(f"创建数据库连接失败: {str(e)}")
            if conn:
                try:
                    conn.close()
                except:
                    pass
            return None

    def get_connection(self):
        """获取数据库连接"""
        start_time = time.time()
        attempts = 0
        max_attempts = 3
        
        while attempts < max_attempts:
            try:
                with self.lock:
                    if self.connections:
                        conn = self.connections.pop()
                        try:
                            # 测试连接是否有效
                            conn.execute("SELECT 1").fetchone()
                            logger.info("从连接池获取到有效连接")
                            return conn
                        except sqlite3.Error as e:
                            logger.warning(f"连接池中的连接已失效: {str(e)}")
                            try:
                                conn.close()
                            except:
                                pass
                            
                    # 如果没有可用连接，创建新连接
                    conn = self._create_connection()
                    if conn:
                        return conn
                    
                attempts += 1
                if attempts < max_attempts:
                    time.sleep(0.5)  # 短暂等待后重试
                
            except Exception as e:
                logger.error(f"获取数据库连接时发生错误: {str(e)}")
                attempts += 1
                if attempts < max_attempts:
                    time.sleep(0.5)
        
        logger.error("达到最大重试次数，无法获取数据库连接")
        raise Exception("无法获取数据库连接，请稍后重试")

    def return_connection(self, conn):
        """归还数据库连接到连接池"""
        if not conn:
            return
            
        try:
            if len(self.connections) < self.max_connections:
                with self.lock:
                    if len(self.connections) < self.max_connections:
                        try:
                            # 测试连接是否仍然有效
                            conn.execute("SELECT 1").fetchone()
                            self.connections.append(conn)
                            logger.info("成功归还连接到连接池")
                            return
                        except sqlite3.Error as e:
                            logger.warning(f"归还的连接已失效: {str(e)}")
            
            # 如果连接池已满或连接无效，关闭连接
            try:
                conn.close()
                logger.info("关闭多余的数据库连接")
            except:
                pass
        except Exception as e:
            logger.error(f"归还连接时发生错误: {str(e)}")
            try:
                conn.close()
            except:
                pass

    def close_all(self):
        """关闭所有数据库连接"""
        with self.lock:
            for conn in self.connections:
                try:
                    conn.close()
                except:
                    pass
            self.connections.clear()

@backoff.on_exception(backoff.expo, 
                     (sqlite3.OperationalError, sqlite3.DatabaseError),
                     max_tries=5,
                     max_time=30)
def init_db():
    """初始化数据库"""
    conn = None
    try:
        need_create_tables = not os.path.exists(Config.DATABASE_PATH)
        
        # 连接数据库
        conn = sqlite3.connect(Config.DATABASE_PATH, timeout=60)
        c = conn.cursor()
        
        # 设置数据库参数
        c.execute('PRAGMA busy_timeout=60000')
        c.execute('PRAGMA temp_store=MEMORY')
        c.execute('PRAGMA cache_size=10000')
        c.execute('PRAGMA synchronous=NORMAL')
        c.execute('PRAGMA foreign_keys=ON')
        
        if need_create_tables:
            logger.info("创建新数据库...")
            
            # 创建账户表
            c.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    create_time DATETIME NOT NULL,
                    card_level TEXT NOT NULL DEFAULT 'platinum',
                    UNIQUE(phone)
                )
            ''')
            
            # 创建金融卡表
            c.execute('''
                CREATE TABLE IF NOT EXISTS financial_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_number TEXT NOT NULL,
                    create_time DATETIME NOT NULL,
                    status TEXT DEFAULT 'available',
                    card_level TEXT NOT NULL DEFAULT 'platinum',
                    UNIQUE(card_number)
                )
            ''')
            
            # 创建激活登记表
            c.execute('''
                CREATE TABLE IF NOT EXISTS card_activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    name TEXT NOT NULL,
                    id_number TEXT NOT NULL,
                    card_number TEXT NOT NULL,
                    card_type TEXT NOT NULL,
                    id_front_photo TEXT NOT NULL,
                    id_back_photo TEXT NOT NULL,
                    submit_time DATETIME NOT NULL,
                    UNIQUE(phone),
                    UNIQUE(card_number),
                    FOREIGN KEY(phone) REFERENCES accounts(phone),
                    FOREIGN KEY(card_number) REFERENCES financial_cards(card_number)
                )
            ''')
            
            # 创建索引
            c.execute('CREATE INDEX IF NOT EXISTS idx_phone_activation ON card_activations(phone)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_idnum_activation ON card_activations(id_number)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_cardnum_activation ON card_activations(card_number)')
            
            # 创建地址登记表
            c.execute('''
                CREATE TABLE IF NOT EXISTS address_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    name TEXT NOT NULL,
                    id_number TEXT NOT NULL,
                    delivery_phone TEXT NOT NULL,
                    delivery_address TEXT NOT NULL,
                    card_type TEXT NOT NULL,
                    id_front_photo TEXT NOT NULL,
                    id_back_photo TEXT NOT NULL,
                    submit_time DATETIME NOT NULL,
                    shipping_status TEXT DEFAULT 'pending',
                    shipping_time DATETIME,
                    tracking_number TEXT,
                    UNIQUE(phone),
                    FOREIGN KEY(phone) REFERENCES accounts(phone)
                )
            ''')
            
            conn.commit()
            logger.info("数据库创建成功")
        else:
            logger.info("数据库已存在，检查并更新表结构...")
            
            # 检查并创建accounts表
            try:
                c.execute("SELECT 1 FROM accounts LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("创建accounts表...")
                c.execute('''
                    CREATE TABLE IF NOT EXISTS accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone TEXT NOT NULL,
                        create_time DATETIME NOT NULL,
                        card_level TEXT NOT NULL DEFAULT 'platinum',
                        UNIQUE(phone)
                    )
                ''')
                conn.commit()
            
            # 检查并创建financial_cards表
            try:
                c.execute("SELECT 1 FROM financial_cards LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("创建financial_cards表...")
                c.execute('''
                    CREATE TABLE IF NOT EXISTS financial_cards (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        card_number TEXT NOT NULL,
                        create_time DATETIME NOT NULL,
                        status TEXT DEFAULT 'available',
                        card_level TEXT NOT NULL DEFAULT 'platinum',
                        UNIQUE(card_number)
                    )
                ''')
                conn.commit()
            
            # 检查并添加shipping_status列
            try:
                c.execute("SELECT shipping_status FROM address_records LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("添加shipping_status列...")
                c.execute("ALTER TABLE address_records ADD COLUMN shipping_status TEXT DEFAULT 'pending'")
                conn.commit()
            
            # 检查并添加shipping_time列
            try:
                c.execute("SELECT shipping_time FROM address_records LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("添加shipping_time列...")
                c.execute("ALTER TABLE address_records ADD COLUMN shipping_time DATETIME")
                conn.commit()
            
            # 检查并添加tracking_number列
            try:
                c.execute("SELECT tracking_number FROM address_records LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("添加tracking_number列...")
                c.execute("ALTER TABLE address_records ADD COLUMN tracking_number TEXT")
                conn.commit()
        
    except Exception as e:
        logger.error(f"初始化数据库失败: {str(e)}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass 