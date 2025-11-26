import sqlite3
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class DatabaseUtils:
    def __init__(self, conn):
        self.conn = conn

    def safe_execute(self, sql: str, params: tuple = None) -> Optional[sqlite3.Cursor]:
        """安全执行SQL语句"""
        try:
            cursor = self.conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            return cursor
        except Exception as e:
            logger.error(f"执行SQL失败: {sql}, 参数: {params}, 错误: {str(e)}")
            raise

    def safe_executemany(self, sql: str, params_list: List[tuple]) -> Optional[sqlite3.Cursor]:
        """安全批量执行SQL语句"""
        try:
            cursor = self.conn.cursor()
            cursor.executemany(sql, params_list)
            return cursor
        except Exception as e:
            logger.error(f"批量执行SQL失败: {sql}, 参数数量: {len(params_list)}, 错误: {str(e)}")
            raise

    def fetch_one(self, sql: str, params: tuple = None) -> Optional[Dict[str, Any]]:
        """安全获取单条记录"""
        try:
            cursor = self.safe_execute(sql, params)
            result = cursor.fetchone()
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"获取单条记录失败: {sql}, 参数: {params}, 错误: {str(e)}")
            raise

    def fetch_all(self, sql: str, params: tuple = None) -> List[Dict[str, Any]]:
        """安全获取多条记录"""
        try:
            cursor = self.safe_execute(sql, params)
            results = cursor.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"获取多条记录失败: {sql}, 参数: {params}, 错误: {str(e)}")
            raise

    def exists(self, table: str, conditions: Dict[str, Any]) -> bool:
        """检查记录是否存在"""
        try:
            where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])
            sql = f"SELECT 1 FROM {table} WHERE {where_clause}"
            params = tuple(conditions.values())
            cursor = self.safe_execute(sql, params)
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查记录存在失败: 表={table}, 条件={conditions}, 错误: {str(e)}")
            raise

    def count(self, table: str, conditions: Dict[str, Any] = None) -> int:
        """计数查询"""
        try:
            sql = f"SELECT COUNT(*) as count FROM {table}"
            params = None
            if conditions:
                where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])
                sql += f" WHERE {where_clause}"
                params = tuple(conditions.values())
            cursor = self.safe_execute(sql, params)
            result = cursor.fetchone()
            return result['count'] if result else 0
        except Exception as e:
            logger.error(f"计数查询失败: 表={table}, 条件={conditions}, 错误: {str(e)}")
            raise

    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        try:
            yield self
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"事务执行失败，已回滚: {str(e)}")
            raise

    def safe_insert(self, table: str, data: Dict[str, Any]) -> int:
        """安全插入数据"""
        try:
            columns = list(data.keys())
            placeholders = ['?' for _ in columns]
            sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(placeholders)})"
            params = tuple(data.values())
            cursor = self.safe_execute(sql, params)
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"插入数据失败: 表={table}, 数据={data}, 错误: {str(e)}")
            raise

    def safe_update(self, table: str, data: Dict[str, Any], conditions: Dict[str, Any]) -> int:
        """安全更新数据"""
        try:
            set_clause = ",".join([f"{k} = ?" for k in data.keys()])
            where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])
            sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
            params = tuple(list(data.values()) + list(conditions.values()))
            cursor = self.safe_execute(sql, params)
            return cursor.rowcount
        except Exception as e:
            logger.error(f"更新数据失败: 表={table}, 数据={data}, 条件={conditions}, 错误: {str(e)}")
            raise

    def safe_delete(self, table: str, conditions: Dict[str, Any]) -> int:
        """安全删除数据"""
        try:
            where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])
            sql = f"DELETE FROM {table} WHERE {where_clause}"
            params = tuple(conditions.values())
            cursor = self.safe_execute(sql, params)
            return cursor.rowcount
        except Exception as e:
            logger.error(f"删除数据失败: 表={table}, 条件={conditions}, 错误: {str(e)}")
            raise 