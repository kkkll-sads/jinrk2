import requests
import schedule
import time
import signal
from datetime import datetime, timedelta
import logging
import re
from bs4 import BeautifulSoup
import json
import urllib.parse
import base64
import sqlite3
from pathlib import Path
import pickle
import sys

# 配置日志级别为DEBUG以显示更多信息
logging.basicConfig(
    level=logging.DEBUG,  # 改为DEBUG级别
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('order_check.log'),
        logging.StreamHandler()
    ]
)

class OrderChecker:
    def __init__(self):
        self.base_url = "http://aadmin.txzjs.top"
        self.last_check_time = None
        # 定义卡片等级优先级（数字越大等级越高）
        self.card_levels = {
            'platinum': 1,  # 铂金卡
            'black': 2,     # 黑金卡
            'supreme': 3    # 至尊卡
        }
        # 标准化卡片等级键（添加小写版本）
        self.card_levels.update({
            'platinum': 1,
            'black': 2,
            'supreme': 3
        })
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
        
        # 初始化状态变量
        self.running = True
        self.error_count = 0
        self.max_consecutive_errors = 5
        
        # 初始化数据库
        try:
            self.init_db()
        except Exception as e:
            logging.error(f"初始化数据库失败: {str(e)}")
            self.running = False
            
        # 设置信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def init_db(self):
        """初始化数据库"""
        try:
            db_path = Path('order_checker.db')
            # 添加超时和优化设置
            self.conn = sqlite3.connect(db_path, timeout=20)
            self.conn.execute("PRAGMA journal_mode=WAL")  # 使用WAL模式提高并发性
            self.conn.execute("PRAGMA synchronous=NORMAL")  # 降低同步级别以提高性能
            self.conn.execute("PRAGMA busy_timeout=10000")  # 10秒超时
            self.cursor = self.conn.cursor()
            
            # 创建用户账户表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_accounts (
                    phone TEXT PRIMARY KEY,
                    card_level TEXT,
                    product_name TEXT,
                    last_order_id INTEGER,
                    last_updated TIMESTAMP
                )
            ''')
            
            # 数据库迁移 - 检查并添加缺失的列
            self.migrate_db()
            
            # 创建会话信息表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_info (
                    id INTEGER PRIMARY KEY,
                    cookies BLOB,
                    csrf_token TEXT,
                    updated_at TIMESTAMP
                )
            ''')
            
            # 创建已处理订单表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_orders (
                    order_id INTEGER PRIMARY KEY,
                    phone TEXT,
                    product TEXT,
                    created_at TIMESTAMP,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建最后检查时间表
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS last_check_time (
                    id INTEGER PRIMARY KEY,
                    check_time TIMESTAMP
                )
            ''')
            
            self.conn.commit()
            logging.info("数据库初始化成功")
            
            # 尝试加载保存的会话
            self.load_session()
            
            # 获取最后检查时间
            self.cursor.execute('SELECT check_time FROM last_check_time WHERE id = 1')
            result = self.cursor.fetchone()
            if result:
                try:
                    # 尝试使用包含微秒的格式解析
                    self.last_check_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    # 如果失败，尝试不带微秒的格式
                    self.last_check_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
                logging.info(f"从数据库加载上次检查时间: {self.last_check_time}")
            
        except Exception as e:
            logging.error(f"初始化数据库失败: {str(e)}")
            raise

    def migrate_db(self):
        """检查并更新数据库表结构"""
        try:
            # 检查user_accounts表是否有product_name列
            self.cursor.execute("PRAGMA table_info(user_accounts)")
            columns = [column[1] for column in self.cursor.fetchall()]
            
            if 'product_name' not in columns:
                logging.info("数据库迁移: 添加product_name列到user_accounts表")
                self.cursor.execute("ALTER TABLE user_accounts ADD COLUMN product_name TEXT")
                self.conn.commit()
                logging.info("数据库迁移完成: product_name列已添加")
            
        except Exception as e:
            logging.error(f"数据库迁移失败: {str(e)}")
            # 继续执行，不要因为迁移失败而中断整个程序

    def is_order_processed(self, order_id):
        """检查订单是否已处理"""
        self.cursor.execute('SELECT 1 FROM processed_orders WHERE order_id = ?', (order_id,))
        return bool(self.cursor.fetchone())

    def mark_order_processed(self, order_id, phone, product, created_at):
        """标记订单为已处理"""
        try:
            sql = 'INSERT INTO processed_orders (order_id, phone, product, created_at) VALUES (?, ?, ?, ?)'
            params = (order_id, phone, product, created_at)
            
            if self.execute_with_retry(sql, params):
                self.conn.commit()
                logging.debug(f"订单 {order_id} 已记录到数据库")
                return True
            else:
                logging.error(f"记录订单到数据库失败")
                return False
        except Exception as e:
            logging.error(f"记录订单到数据库失败: {str(e)}")
            return False

    def update_last_check_time(self, check_time):
        """更新最后检查时间"""
        try:
            sql = 'INSERT OR REPLACE INTO last_check_time (id, check_time) VALUES (1, ?)'
            params = (check_time.strftime('%Y-%m-%d %H:%M:%S.%f'),)
            
            if self.execute_with_retry(sql, params):
                self.conn.commit()
                logging.debug(f"更新数据库中的检查时间: {check_time}")
                return True
            else:
                logging.error(f"更新检查时间失败")
                return False
        except Exception as e:
            logging.error(f"更新检查时间失败: {str(e)}")
            return False

    def log_request_info(self, response, action="请求"):
        logging.debug(f"\n{'='*50}")
        logging.debug(f"{action}URL: {response.url}")
        logging.debug(f"请求方法: {response.request.method}")
        logging.debug(f"请求头: {dict(response.request.headers)}")
        if response.request.body:
            try:
                if isinstance(response.request.body, bytes):
                    body_str = response.request.body.decode('utf-8')
                else:
                    body_str = str(response.request.body)
                logging.debug(f"请求体: {body_str}")
            except Exception as e:
                logging.debug(f"请求体无法解码: {e}")
        logging.debug(f"响应状态: {response.status_code}")
        logging.debug(f"响应头: {dict(response.headers)}")
        try:
            logging.debug(f"Cookie信息: {dict(self.session.cookies)}")
        except Exception as e:
            logging.debug(f"无法记录Cookie信息: {e}")
        logging.debug(f"{'='*50}\n")

    def get_token(self):
        try:
            response = self.session.get(f"{self.base_url}/AILYGfgFdj/Login")
            self.log_request_info(response, "获取登录页面")
            
            if response.status_code != 200:
                logging.error(f"获取登录页面失败，状态码: {response.status_code}")
                return None

            # 记录完整的响应内容用于调试
            logging.debug(f"登录页面内容: {response.text}")

            token_match = re.search(r'name="_token"\s+value="([^"]+)"', response.text)
            if token_match:
                token = token_match.group(1)
                logging.info(f"成功获取token: {token}")
                return token
            else:
                logging.error("未找到token，页面内容可能有变化")
                return None

        except Exception as e:
            logging.error(f"获取token过程中发生错误: {str(e)}")
            return None

    def login(self):
        try:
            token = self.get_token()
            if not token:
                logging.error("无法获取登录token")
                return False, None

            login_data = {
                'username': 'admin',
                'password': '123456',
                '_token': token
            }
            
            logging.info("尝试登录系统...")
            logging.debug(f"登录数据: username=admin, token={token[:10]}...")
            
            response = self.session.post(
                f"{self.base_url}/AILYGfgFdj/Login",
                data=login_data
            )
            
            self.log_request_info(response, "登录请求")
            
            if response.status_code == 200:
                logging.info("登录请求成功")
                # 获取登录后的token
                csrf_token = self.get_csrf_token_from_cookie()
                if not csrf_token:
                    csrf_token = token  # 如果无法从cookie获取，使用登录时的token
                    logging.warning("无法从cookie获取新token，使用原始token")
                logging.info(f"登录成功，获取到新token: {csrf_token[:10]}...")
                return True, csrf_token
            else:
                logging.error(f"登录失败，HTTP状态码: {response.status_code}")
                logging.debug(f"登录响应内容: {response.text[:500]}...")
                return False, None
                
        except Exception as e:
            logging.error(f"登录过程发生异常: {str(e)}")
            return False, None

    def get_csrf_token_from_cookie(self):
        """从Cookie中获取CSRF token"""
        try:
            for cookie in self.session.cookies:
                if cookie.name == 'XSRF-TOKEN':
                    # Laravel的XSRF-TOKEN是URL编码的，需要解码
                    decoded_token = urllib.parse.unquote(cookie.value)
                    # 解析JSON格式的token
                    token_data = json.loads(decoded_token)
                    if 'value' in token_data:
                        token = token_data['value']
                        logging.debug(f"从Cookie解析出的CSRF token: {token}")
                        return token
            logging.error("在Cookie中未找到XSRF-TOKEN")
            return None
        except Exception as e:
            logging.error(f"解析CSRF token失败: {str(e)}")
            return None

    def get_csrf_token_from_page(self, html_content):
        """从HTML页面内容中获取CSRF token"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            # 尝试从meta标签获取
            meta_token = soup.find('meta', {'name': 'csrf-token'})
            if meta_token:
                return meta_token.get('content')
            
            # 尝试从隐藏input获取
            input_token = soup.find('input', {'name': '_token'})
            if input_token:
                return input_token.get('value')
            
            logging.error("在页面中未找到CSRF token")
            return None
        except Exception as e:
            logging.error(f"解析页面获取CSRF token失败: {str(e)}")
            return None

    def save_session(self, csrf_token):
        """保存会话信息到数据库"""
        try:
            # 序列化cookies
            cookies_data = pickle.dumps(self.session.cookies)
            current_time = datetime.now()
            formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.%f')
            
            self.cursor.execute('''
                INSERT OR REPLACE INTO session_info (id, cookies, csrf_token, updated_at)
                VALUES (1, ?, ?, ?)
            ''', (cookies_data, csrf_token, formatted_time))
            
            self.conn.commit()
            logging.info("会话信息已保存到数据库")
        except Exception as e:
            logging.error(f"保存会话信息失败: {str(e)}")

    def load_session(self):
        """从数据库加载会话信息"""
        try:
            self.cursor.execute('''
                SELECT cookies, csrf_token, updated_at 
                FROM session_info 
                WHERE id = 1
            ''')
            result = self.cursor.fetchone()
            
            if result:
                cookies_data, csrf_token, updated_at = result
                try:
                    # 尝试使用包含微秒的格式解析
                    updated_at = datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    # 如果失败，尝试不带微秒的格式
                    updated_at = datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S')
                
                # 检查会话是否过期（24小时）
                if datetime.now() - updated_at < timedelta(hours=24):
                    # 恢复cookies
                    self.session.cookies = pickle.loads(cookies_data)
                    logging.info("成功加载保存的会话信息")
                    return csrf_token
                else:
                    logging.info("保存的会话已过期")
            
            return None
        except Exception as e:
            logging.error(f"加载会话信息失败: {str(e)}")
            return None

    def validate_session(self, csrf_token):
        """验证会话是否有效"""
        try:
            # 尝试访问需要登录的页面
            response = self.session.get(f"{self.base_url}/AILYGfgFdj/productbuy/lists")
            if response.status_code == 200 and "login" not in response.url.lower():
                logging.info("会话验证成功")
                return True
            logging.info("会话已失效")
            return False
        except Exception as e:
            logging.error(f"验证会话时发生错误: {str(e)}")
            return False

    def check_orders(self):
        if not self.running:
            logging.error("系统状态错误，无法执行订单检查")
            return False
            
        try:
            logging.debug("开始检查订单流程...")
            
            # 第一次运行时进行登录，之后只在会话无效时才登录
            if not hasattr(self, 'login_done') or not self.login_done:
                logging.debug("检查登录状态：需要进行登录")
                # 尝试使用保存的会话
                csrf_token = self.load_session()
                
                # 如果没有保存的会话或会话无效，则重新登录
                if not csrf_token or not self.validate_session(csrf_token):
                    logging.info("首次运行或会话无效，开始登录流程")
                    login_success, csrf_token = self.login()
                    if not login_success or not csrf_token:
                        self.error_count += 1
                        logging.error(f"登录失败，当前错误计数：{self.error_count}/{self.max_consecutive_errors}")
                        if self.error_count >= self.max_consecutive_errors:
                            logging.critical(f"连续登录失败{self.error_count}次，系统可能需要人工干预")
                        return False
                    logging.info("登录成功，准备保存会话信息")
                    # 保存新的会话信息
                    self.save_session(csrf_token)
                    
                # 登录成功，设置标志和重置错误计数
                self.login_done = True
                self.csrf_token = csrf_token
                self.error_count = 0
                logging.info(f"登录状态已确认，token: {csrf_token[:10]}...")
            else:
                # 使用已保存的token
                csrf_token = self.csrf_token
                logging.debug(f"使用现有会话，token: {csrf_token[:10]}...")

            # 记录当前检查时间点
            current_check_time = datetime.now()
            logging.debug(f"本次检查开始时间：{current_check_time}")
            
            # 如果是首次运行，设置上次检查时间为当前时间
            if self.last_check_time is None:
                self.last_check_time = current_check_time
                self.update_last_check_time(self.last_check_time)
                logging.info(f"首次运行，初始化检查时间点: {self.last_check_time}")
            
            # POST请求参数
            post_data = {
                'page': '1',
                's_key': '',
                'top_uid': '',
                's_categoryid': '95',
                's_order': '',
                's_status': '1',
                's_pay_type': '',
                'date_s': '',
                'date_e': '',
                '_token': csrf_token
            }
            logging.debug(f"准备发送请求，参数：{post_data}")
            
            # 更新请求头
            headers = {
                'Host': 'aadmin.txzjs.top',
                'Referer': f"{self.base_url}/AILYGfgFdj/productbuy/lists?s_key=&top_uid=&s_categoryid=95&s_order=&s_status=1&s_pay_type=&date_s=&date_e=",
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'X-CSRF-TOKEN': csrf_token,
                'Origin': self.base_url
            }
            logging.debug("已更新请求头")
            self.session.headers.update(headers)

            # 先访问列表页面
            logging.debug("开始访问订单列表页面...")
            list_response = self.session.get(f"{self.base_url}/AILYGfgFdj/productbuy/lists")
            self.log_request_info(list_response, "获取订单列表页面")
            
            if list_response.status_code != 200:
                logging.error(f"访问列表页面失败，状态码：{list_response.status_code}")
                logging.debug(f"响应内容：{list_response.text[:500]}...")
                return False
            
            logging.debug("开始获取订单数据...")
            # 发送POST请求获取订单数据
            response = self.session.post(
                f"{self.base_url}/AILYGfgFdj/productbuy/lists",
                data=post_data
            )
            
            self.log_request_info(response, "获取订单数据")
            
            if response.status_code == 200:
                try:
                    json_data = response.json()
                    logging.info("成功获取订单数据")
                    logging.debug(f"订单数据响应：{json_data}")
                    
                    if json_data.get('status') == 0 and 'list' in json_data:
                        order_list = json_data['list']
                        total_orders = order_list.get('total', 0)
                        current_page = order_list.get('current_page', 1)
                        per_page = order_list.get('per_page', 10)
                        
                        logging.info(f"订单统计信息：总数={total_orders}, 当前页={current_page}, 每页显示={per_page}")
                        
                        # 处理订单数据
                        orders = order_list.get('data', [])
                        logging.info(f"本次获取到 {len(orders)} 个订单")
                        
                        for order in orders:
                            # 只处理已支付的订单
                            if order.get('status') == 1:
                                order_id = order.get('id')
                                created_at = datetime.strptime(order.get('created_at'), '%Y-%m-%d %H:%M:%S')
                                
                                logging.debug(f"处理订单 {order_id}，创建时间：{created_at}")
                                
                                # 检查是否是新订单
                                if not self.is_order_processed(order_id) and created_at > self.last_check_time:
                                    phone = order.get('username')
                                    product = order.get('product')
                                    logging.info(f"发现新订单 {order_id} - 手机: {phone}, 产品: {product}, 创建时间: {created_at}")
                                    
                                    # 添加重试机制
                                    max_retries = 3
                                    retry_count = 0
                                    success = False
                                    
                                    while retry_count < max_retries and not success:
                                        if retry_count > 0:
                                            logging.info(f"第{retry_count}次重试处理订单 {order_id} - 手机: {phone}")
                                            
                                        try:
                                            logging.info(f"开始处理订单 {order_id} - 查询账户状态并进行更新/添加")
                                            success = self.add_account_to_local(phone, product)
                                            if success:
                                                logging.info(f"成功处理订单 {order_id} - 账户已更新或添加")
                                                break
                                            else:
                                                logging.error(f"处理订单 {order_id} 失败 - 账户更新或添加出错")
                                        except Exception as e:
                                            logging.error(f"处理订单 {order_id} 时发生异常: {str(e)}")
                                            
                                        retry_count += 1
                                        if retry_count < max_retries:
                                            wait_time = 2 * retry_count
                                            logging.debug(f"等待 {wait_time} 秒后进行第 {retry_count + 1} 次重试")
                                            time.sleep(wait_time)
                                    
                                    if not success:
                                        logging.warning(f"订单 {order_id} 处理失败，已达到最大重试次数")
                                        
                                    # 记录到数据库
                                    if self.mark_order_processed(order_id, phone, product, created_at):
                                        logging.info(f"订单 {order_id} 已标记为已处理")
                                    else:
                                        logging.error(f"订单 {order_id} 标记处理状态失败")
                                else:
                                    logging.debug(f"订单 {order_id} 已处理或不是新订单")
                        
                        # 更新最后检查时间
                        self.last_check_time = current_check_time
                        self.update_last_check_time(self.last_check_time)
                        logging.info(f"完成本次检查，更新时间点: {self.last_check_time}")
                        
                    else:
                        logging.warning(f"获取订单列表失败，响应数据: {json_data}")
                        
                except json.JSONDecodeError as e:
                    logging.error(f"解析JSON响应失败: {str(e)}")
                    logging.debug(f"响应内容: {response.text[:1000]}...")  # 只记录前1000个字符
                
            else:
                logging.error(f"获取订单失败，状态码: {response.status_code}")
                if response.status_code == 419:
                    logging.error("CSRF token验证失败")
                    logging.debug(f"使用的CSRF token: {csrf_token}")
                    logging.debug(f"响应内容: {response.text[:500]}...")
                    # 会话可能失效，清除登录状态以便下次重新登录
                    self.login_done = False
                    self.csrf_token = None
                    logging.info("已清除登录状态，下次将重新登录")
                
        except Exception as e:
            logging.error(f"检查订单过程中发生错误: {str(e)}")
            import traceback
            logging.error(f"详细错误信息: {traceback.format_exc()}")
            # 如果出现异常，重置登录状态，下次重新登录
            if hasattr(self, 'login_done'):
                self.login_done = False
                self.csrf_token = None
                logging.info("由于异常发生，已清除登录状态，下次将重新登录")
            return False

    def format_order_status(self, status):
        """格式化订单状态"""
        status_map = {
            0: "待支付",
            1: "已支付",
            2: "已取消",
            # 根据实际情况添加更多状态
        }
        return status_map.get(status, f"未知状态({status})")

    def map_card_level(self, product_name):
        """将产品名称映射为卡片等级"""
        if not product_name:
            return None
            
        if "黑金卡" in product_name:
            return "black"
        elif "铂金卡" in product_name or "platinum" in product_name.lower():
            return "platinum"
        elif "至尊卡" in product_name or "supreme" in product_name.lower():
            return "supreme"
        # 添加更多卡类型映射
        return None

    def compare_card_levels(self, current_level, new_level):
        """比较卡片等级
        返回: True 如果新等级更高，False 如果当前等级更高或相等
        """
        if not current_level or not new_level:
            # 如果任一等级不存在，允许更新
            logging.debug(f"卡片等级比较: 当前={current_level}, 新={new_level}, 结果=允许更新(缺少等级信息)")
            return True
        
        # 标准化等级名称（小写并去除空格）
        current_level = current_level.lower().strip() if isinstance(current_level, str) else current_level
        new_level = new_level.lower().strip() if isinstance(new_level, str) else new_level
        
        # 获取各等级的优先级
        current_priority = self.card_levels.get(current_level, 0)
        new_priority = self.card_levels.get(new_level, 0)
        
        result = new_priority > current_priority
        logging.debug(f"卡片等级比较: 当前={current_level}({current_priority}), 新={new_level}({new_priority}), 结果={result}")
        return result

    def get_user_account(self, phone):
        """获取用户账户信息"""
        try:
            self.cursor.execute('''
                SELECT card_level, product_name, last_order_id 
                FROM user_accounts 
                WHERE phone = ?
            ''', (phone,))
            result = self.cursor.fetchone()
            if result:
                logging.debug(f"获取到用户账户信息 - 手机: {phone}, 当前等级: {result[0]}")
            return result
        except Exception as e:
            logging.error(f"获取用户账户信息失败: {str(e)}")
            return None

    def search_account(self, phone):
        """使用新API查询账户信息"""
        try:
            url = f"http://127.0.0.1:80/api/admin/accounts/search_new?phone={phone}&level=all&status=all"
            logging.info(f"查询账户信息 - 手机: {phone}, API: {url}")
            
            response = requests.get(
                url,
                timeout=10
            )
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    if response_data.get('success') and 'accounts' in response_data:
                        accounts = response_data['accounts']
                        logging.info(f"成功查询到账户信息 - 手机: {phone}, 账户数量: {len(accounts)}")
                        return accounts
                    else:
                        logging.warning(f"查询账户返回成功但数据不完整 - 手机: {phone}, 响应: {response_data}")
                        return []
                except json.JSONDecodeError as e:
                    logging.error(f"解析查询账户响应JSON失败: {str(e)}")
                    return []
            else:
                logging.error(f"查询账户失败 - 状态码: {response.status_code}, 响应: {response.text}")
                return []
        except Exception as e:
            logging.error(f"查询账户过程中发生错误: {str(e)}")
            return []

    def update_account_to_local(self, phone, card_level, product_name=None):
        """更新本地服务器中的账户信息"""
        try:
            data = {
                "phone": phone,
                "card_level": card_level
            }
            
            logging.info(f"开始更新账户 - 手机: {phone}")
            logging.debug(f"更新数据: 等级={card_level}, 产品={product_name}")
            
            response = requests.post(
                "http://127.0.0.1:80/admin_update_account",
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            logging.debug(f"更新响应 - 状态码: {response.status_code}")
            logging.debug(f"响应内容: {response.text[:500]}...")
            
            success = response.status_code == 200
            if success:
                logging.info(f"账户更新成功 - 手机: {phone}, 新等级: {card_level}")
            else:
                logging.error(f"账户更新失败 - 手机: {phone}, 状态码: {response.status_code}")
            
            return success
        except Exception as e:
            logging.error(f"更新账户时发生异常: {str(e)}")
            return False

    def add_account_to_local(self, phone, product_name):
        """向本地服务器添加账户"""
        try:
            card_level = self.map_card_level(product_name)
            if not card_level:
                logging.error(f"未知的卡片类型: {product_name}")
                return False
                
            logging.info(f"开始处理账户 - 手机: {phone}, 产品: {product_name}, 映射等级: {card_level}")
            
            # 使用新API查询账户信息
            accounts = self.search_account(phone)
            
            if accounts:
                # 账户已存在，比较卡片等级
                existing_account = accounts[0]  # 使用第一个账户
                existing_card_level = existing_account.get('card_level')
                
                logging.info(f"发现已存在账户 - 手机: {phone}")
                logging.debug(f"当前账户信息: {existing_account}")
                logging.info(f"等级对比 - 当前: {existing_card_level}, 新: {card_level}")
                
                # 比较卡片等级
                if not self.compare_card_levels(existing_card_level, card_level):
                    logging.info(f"保留更高等级 - 手机: {phone}, 当前等级({existing_card_level})比新等级({card_level})高或相等")
                    return True
                
                # 如果新等级更高，则更新
                logging.info(f"需要升级 - 手机: {phone}, 从 {existing_card_level} 升级到 {card_level}")
                success = self.update_account_to_local(phone, card_level, product_name)
                if success:
                    logging.info(f"账户升级成功 - 手机: {phone}, 新等级: {card_level}")
                else:
                    logging.error(f"账户升级失败 - 手机: {phone}")
                return success
            else:
                # 如果是新账户，则添加
                logging.info(f"添加新账户 - 手机: {phone}, 卡片等级: {card_level}, 产品: {product_name}")
                data = {
                    "phone": phone,
                    "card_level": card_level
                }
                
                try:
                    logging.debug(f"发送添加账户请求 - 数据: {data}")
                    response = requests.post(
                        "http://127.0.0.1:80/admin_add_account",
                        json=data,
                        headers={'Content-Type': 'application/json'},
                        timeout=10
                    )
                    
                    logging.debug(f"添加账户响应 - 状态码: {response.status_code}")
                    logging.debug(f"响应内容: {response.text[:500]}...")
                    
                    remote_success = response.status_code == 200
                    if remote_success:
                        logging.info(f"成功添加新账户 - 手机: {phone}")
                    else:
                        logging.warning(f"添加账户失败 - 状态码: {response.status_code}")
                        # 处理可能的错误情况...

                except Exception as e:
                    logging.error(f"连接远程服务器失败: {str(e)}")
                    # 连接远程服务器失败，尝试只更新本地数据库
                    try:
                        try:
                            self.cursor.execute('''
                                INSERT OR REPLACE INTO user_accounts (phone, card_level, product_name, last_updated)
                                VALUES (?, ?, ?, ?)
                            ''', (phone, card_level, product_name, datetime.now()))
                        except sqlite3.OperationalError as sql_err:
                            # 如果product_name列不存在，尝试不使用此列
                            if "no such column: product_name" in str(sql_err):
                                logging.warning(f"product_name列不存在，尝试不使用此列添加")
                                self.cursor.execute('''
                                    INSERT OR REPLACE INTO user_accounts (phone, card_level, last_updated)
                                    VALUES (?, ?, ?)
                                ''', (phone, card_level, datetime.now()))
                            else:
                                # 其他SQL错误，重新抛出
                                raise
                        self.conn.commit()
                        logging.debug(f"远程服务器失败，但本地数据库更新成功 - 手机: {phone}, 卡片等级: {card_level}")
                        return True  # 本地成功也算部分成功
                    except Exception as db_e:
                        logging.error(f"本地数据库更新也失败: {str(db_e)}")
                        return False
                
        except Exception as e:
            logging.error(f"添加账户时发生错误: {str(e)}")
            return False

    def save_program_state(self):
        """保存程序状态到文件"""
        try:
            state = {
                'last_check_time': self.last_check_time,
                'error_count': self.error_count,
                'running': self.running,
                'login_done': hasattr(self, 'login_done') and self.login_done,
                'csrf_token': getattr(self, 'csrf_token', None)
            }
            with open('order_checker_state.pkl', 'wb') as f:
                pickle.dump(state, f)
            logging.debug("程序状态已保存")
            return True
        except Exception as e:
            logging.error(f"保存程序状态失败: {str(e)}")
            return False
            
    def load_program_state(self):
        """从文件加载程序状态"""
        try:
            state_file = Path('order_checker_state.pkl')
            if state_file.exists():
                with open(state_file, 'rb') as f:
                    state = pickle.load(f)
                
                if 'last_check_time' in state and state['last_check_time']:
                    self.last_check_time = state['last_check_time']
                if 'error_count' in state:
                    self.error_count = state['error_count']
                if 'running' in state:
                    self.running = state['running']
                if 'login_done' in state:
                    self.login_done = state['login_done']
                if 'csrf_token' in state and state['csrf_token']:
                    self.csrf_token = state['csrf_token']
                    
                logging.info(f"程序状态已加载，上次检查时间: {self.last_check_time}")
                if getattr(self, 'login_done', False):
                    logging.info("已加载登录状态，将使用保存的会话")
                return True
            return False
        except Exception as e:
            logging.error(f"加载程序状态失败: {str(e)}")
            return False

    def signal_handler(self, sig, frame):
        """处理中断信号，安全关闭程序"""
        logging.info("接收到终止信号，正在安全关闭...")
        self.running = False
        self.save_program_state()
        self.__del__()
        sys.exit(0)

    def __del__(self):
        """析构函数，确保数据库连接正确关闭"""
        try:
            self.save_program_state()
            if hasattr(self, 'conn') and self.conn:
                logging.info("关闭数据库连接...")
                self.conn.commit()
                self.conn.close()
                logging.info("数据库连接已安全关闭")
        except Exception as e:
            logging.error(f"关闭数据库连接时发生错误: {str(e)}")

    def execute_with_retry(self, sql, params=(), max_retries=3, retry_delay=1):
        """执行SQL语句，支持重试"""
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                self.cursor.execute(sql, params)
                return True
            except sqlite3.OperationalError as e:
                last_error = e
                retries += 1
                if "database is locked" in str(e) and retries < max_retries:
                    logging.warning(f"数据库锁定，等待重试 ({retries}/{max_retries})...")
                    time.sleep(retry_delay * retries)  # 递增等待时间
                else:
                    break
        
        if last_error:
            logging.error(f"SQL执行失败 (重试{retries}次后): {str(last_error)}\nSQL: {sql}")
        return False

    def execute_transaction(self, operations):
        """作为一个事务执行多个SQL操作"""
        try:
            for sql, params in operations:
                if not self.execute_with_retry(sql, params):
                    self.conn.rollback()
                    return False
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            logging.error(f"事务执行失败: {str(e)}")
            return False

def job():
    """定时任务"""
    try:
        logging.info("开始执行订单检查任务")
        checker = OrderChecker()
        
        # 尝试加载之前的程序状态
        checker.load_program_state()
        
        if checker.running:
            checker.check_orders()
            
        # 保存程序状态
        checker.save_program_state()
        del checker  # 显式释放资源
    except KeyboardInterrupt:
        logging.info("任务被用户中断")
    except Exception as e:
        logging.error(f"执行任务时发生错误: {str(e)}")

def main():
    try:
        # 首次运行立即执行一次
        job()
        
        # 然后设置每3分钟执行一次
        schedule.every(3).minutes.do(job)
        
        logging.info("系统启动成功，将每3分钟检查一次订单")
        
        # 主循环
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("程序被用户中断，正在安全退出...")
    except Exception as e:
        logging.error(f"程序运行时发生错误: {str(e)}")
    finally:
        logging.info("程序已安全退出")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("程序被用户中断，正在安全退出...")
    except Exception as e:
        logging.error(f"程序入口点发生错误: {str(e)}")
        raise 