from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, make_response, session, send_file, Response
from datetime import datetime, timedelta
import os
from models.database import DatabasePool
from utils.decorators import with_db_connection
import time
import sqlite3
import re
import pandas as pd
import json
import tempfile
import csv
from io import StringIO
from werkzeug.utils import secure_filename
from urllib.parse import quote
from utils.validators import validate_json_input
from utils.file_handlers import FileHandler
from utils.db_utils import DatabaseUtils
import logging
from pathlib import Path
import requests

# 可选导入 moviepy
try:
    from moviepy.editor import VideoFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    VideoFileClip = None

# 创建蓝图
main = Blueprint('main', __name__)

def save_failed_records(import_type, failed_records):
    """保存失败记录到临时文件"""
    # 创建临时文件
    temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    # 生成唯一的文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{import_type}_{timestamp}.json"
    filepath = os.path.join(temp_dir, filename)
    
    # 保存失败记录
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(failed_records, f, ensure_ascii=False)
    
    # 在session中只存储文件名
    session[f'failed_{import_type}_records_file'] = filename
    
    # 设置过期时间（1小时后）
    session[f'failed_{import_type}_records_expires'] = (datetime.now() + timedelta(hours=1)).timestamp()

def get_failed_records(import_type):
    """从临时文件获取失败记录"""
    filename = session.get(f'failed_{import_type}_records_file')
    if not filename:
        return []
        
    # 检查是否过期
    expires = session.get(f'failed_{import_type}_records_expires')
    if expires and datetime.now().timestamp() > expires:
        # 删除过期文件和session记录
        cleanup_failed_records(import_type)
        return []
    
    filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp', filename)
    if not os.path.exists(filepath):
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def cleanup_failed_records(import_type):
    """清理失败记录相关的文件和session"""
    filename = session.get(f'failed_{import_type}_records_file')
    if filename:
        filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp', filename)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"清理失败记录文件出错: {str(e)}")
        
        session.pop(f'failed_{import_type}_records_file', None)
        session.pop(f'failed_{import_type}_records_expires', None)

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/card_activation')
def card_activation():
    return render_template('card_activation.html')

@main.route('/address_registration')
def address_registration():
    return render_template('address_registration.html')

@main.route('/search_records')
def search_records():
    return render_template('search_records.html')

@main.route('/submit_activation', methods=['POST'])
@with_db_connection
def submit_activation(conn=None):
    try:
        # 获取表单数据，去除两边空格
        phone = request.form.get('phone', '').strip()
        card_number = request.form.get('card_number', '').strip()
        
        # 验证账户是否存在并获取账户等级
        cursor = conn.cursor()
        cursor.execute("SELECT card_level FROM accounts WHERE phone = ?", (phone,))
        account = cursor.fetchone()
        if not account:
            return jsonify({"成功": False, "消息": "该手机号未注册，请先联系管理员添加账户"}), 400
            
        # 验证金融卡是否存在且可用
        cursor.execute("""
            SELECT status, card_level
            FROM financial_cards 
            WHERE card_number = ?
        """, (card_number,))
        card = cursor.fetchone()
        
        if not card:
            return jsonify({"成功": False, "消息": "该金融卡不存在，请确认卡号是否正确"}), 400
            
        if card['status'] != 'available':
            return jsonify({"成功": False, "消息": "该金融卡已被使用或状态异常"}), 400
            
        # 验证用户是否有权限激活该等级的卡片
        card_levels = {
            'platinum': 1,
            'black': 2,
            'supreme': 3
        }
        
        user_level = card_levels.get(account['card_level'], 0)
        card_level = card_levels.get(card['card_level'], 0)
        
        if user_level < card_level:
            return jsonify({
                "成功": False, 
                "消息": f"您的账户等级（{account['card_level']}）不足以激活该卡片（{card['card_level']}）"
            }), 400
            
        name = request.form.get('name', '').strip()
        id_number = request.form.get('id_number', '').strip()
        card_type = request.form.get('card_type', '').strip()
        
        print(f"接收到的表单数据: phone={phone}, name={name}, id_number={id_number}, card_type={card_type}")
        
        # 获取身份证照片文件
        id_front_photo = request.files.get('id_front_photo')
        id_back_photo = request.files.get('id_back_photo')
        
        # 验证所有必填字段
        if not all([phone, name, id_number, card_number, card_type, id_front_photo, id_back_photo]):
            print("缺少必填字段")
            return jsonify({"成功": False, "消息": "请填写所有必要信息并上传身份证照片"}), 400
            
        # 检查唯一性
        cursor.execute("""
            SELECT phone, card_number 
            FROM card_activations 
            WHERE phone = ? OR card_number = ?
        """, (phone, card_number))
        
        existing = cursor.fetchone()
        if existing:
            if existing['phone'] == phone:
                return jsonify({"成功": False, "消息": "该手机号已经登记过"}), 400
            elif existing['card_number'] == card_number:
                return jsonify({"成功": False, "消息": "该卡号已经登记过"}), 400
        
        try:
            # 确保上传目录存在
            upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            print(f"上传目录: {upload_dir}")
            
            # 保存身份证照片
            front_photo_filename = None
            back_photo_filename = None
            
            if id_front_photo:
                front_photo_filename = f"{id_number}_front_{int(time.time())}.jpg"
                front_photo_path = os.path.join(upload_dir, front_photo_filename)
                id_front_photo.save(front_photo_path)
                front_photo_filename = os.path.join('uploads', front_photo_filename)
                print(f"保存正面照片: {front_photo_path}")
                
            if id_back_photo:
                back_photo_filename = f"{id_number}_back_{int(time.time())}.jpg"
                back_photo_path = os.path.join(upload_dir, back_photo_filename)
                id_back_photo.save(back_photo_path)
                back_photo_filename = os.path.join('uploads', back_photo_filename)
                print(f"保存背面照片: {back_photo_path}")
                
            cursor = conn.cursor()
            sql = """INSERT INTO card_activations
                     (phone, name, id_number, card_number, card_type, id_front_photo, id_back_photo, submit_time)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
            submit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 打印SQL语句和参数
            print(f"SQL: {sql}")
            print(f"参数: {(phone, name, id_number, card_number, card_type, front_photo_filename, back_photo_filename, submit_time)}")
            
            cursor.execute(sql, (
                phone, name, id_number, card_number, card_type,
                front_photo_filename, back_photo_filename, submit_time
            ))
            conn.commit()
            print("数据库提交成功")
            
            # 验证插入是否成功
            cursor.execute("""
                SELECT * FROM card_activations 
                WHERE phone=? AND id_number=? 
                ORDER BY submit_time DESC LIMIT 1
            """, (phone, id_number))
            result = cursor.fetchone()
            if result:
                print(f"验证插入成功: {dict(result)}")
            else:
                print("警告：数据似乎没有成功插入")
                
            # 更新金融卡状态
            cursor.execute("""
                UPDATE financial_cards 
                SET status = 'activated' 
                WHERE card_number = ?
            """, (card_number,))
            
            return jsonify({"成功": True, "消息": "激活登记成功"})
        except sqlite3.IntegrityError as e:
            print(f"数据库唯一性约束错误: {str(e)}")
            # 如果保存失败，删除已上传的文件
            if front_photo_filename:
                front_photo_path = os.path.join(upload_dir, os.path.basename(front_photo_filename))
                if os.path.exists(front_photo_path):
                    os.remove(front_photo_path)
                    print(f"删除正面照片: {front_photo_path}")
            if back_photo_filename:
                back_photo_path = os.path.join(upload_dir, os.path.basename(back_photo_filename))
                if os.path.exists(back_photo_path):
                    os.remove(back_photo_path)
                    print(f"删除背面照片: {back_photo_path}")
            
            error_message = str(e)
            if "phone" in error_message:
                return jsonify({"成功": False, "消息": "该手机号已经登记过"}), 400
            elif "card_number" in error_message:
                return jsonify({"成功": False, "消息": "该卡号已经登记过"}), 400
            else:
                return jsonify({"成功": False, "消息": "该信息已经登记过"}), 400
        except Exception as e:
            print(f"发生错误: {str(e)}")
            # 如果保存失败，删除已上传的文件
            if front_photo_filename:
                front_photo_path = os.path.join(upload_dir, os.path.basename(front_photo_filename))
                if os.path.exists(front_photo_path):
                    os.remove(front_photo_path)
                    print(f"删除正面照片: {front_photo_path}")
            if back_photo_filename:
                back_photo_path = os.path.join(upload_dir, os.path.basename(back_photo_filename))
                if os.path.exists(back_photo_path):
                    os.remove(back_photo_path)
                    print(f"删除背面照片: {back_photo_path}")
            raise  # 重新抛出异常
    except Exception as e:
        print(f"外层错误: {str(e)}")
        return jsonify({"成功": False, "消息": f"登记失败：{str(e)}"}), 500

@main.route('/submit_address', methods=['POST'])
@with_db_connection
def submit_address(conn=None):
    try:
        # 获取表单数据，去除两边空格
        phone = request.form.get('phone', '').strip()
        
        # 打印完整请求信息，用于调试
        print("=== 提交地址表单数据 ===")
        for key in request.form.keys():
            value = request.form.get(key, '')
            print(f"{key}: {value}")
        
        print("=== 提交地址文件数据 ===")
        for key in request.files.keys():
            file = request.files.get(key)
            if file:
                print(f"{key}: {file.filename}")
            else:
                print(f"{key}: None")
        
        # 验证账户是否存在并获取账户等级
        cursor = conn.cursor()
        cursor.execute("SELECT card_level FROM accounts WHERE phone = ?", (phone,))
        account = cursor.fetchone()
        if not account:
            print(f"手机号 {phone} 未注册")
            return jsonify({"成功": False, "消息": "该手机号未注册，请先联系管理员添加账户"}), 400
            
        name = request.form.get('name', '').strip()
        id_number = request.form.get('id_number', '').strip()
        delivery_phone = request.form.get('delivery_phone', '').strip()
        delivery_address = request.form.get('delivery_address', '').strip()
        card_type = request.form.get('card_type', '').strip()
        id_front = request.files.get('id_front_photo')
        id_back = request.files.get('id_back_photo')
        
        # 根据账户获取卡类型
        if not card_type:
            card_type = account['card_level']
            print(f"使用账户默认卡类型: {card_type}")

        # 检查必要数据是否完整，详细记录哪个字段缺失
        missing_fields = []
        if not phone: missing_fields.append("手机号码")
        if not name: missing_fields.append("姓名")
        if not id_number: missing_fields.append("身份证号码")
        if not delivery_phone: missing_fields.append("收件人手机号码")
        if not delivery_address: missing_fields.append("收件地址")
        if not card_type: missing_fields.append("金融卡类型")
        
        if id_front is None:
            missing_fields.append("身份证正面照片")
        elif not id_front.filename:
            missing_fields.append("身份证正面照片文件名为空")
            
        if id_back is None:
            missing_fields.append("身份证背面照片")
        elif not id_back.filename:
            missing_fields.append("身份证背面照片文件名为空")
        
        if missing_fields:
            missing_str = "、".join(missing_fields)
            print(f"缺少字段: {missing_str}")
            return jsonify({"成功": False, "消息": f"请填写以下必要信息: {missing_str}"}), 400

        # 验证手机号格式
        if not re.match(r'^1[3-9]\d{9}$', phone):
            print(f"无效的手机号码: {phone}")
            return jsonify({"成功": False, "消息": "请输入有效的手机号码"}), 400
            
        if not re.match(r'^1[3-9]\d{9}$', delivery_phone):
            print(f"无效的收货手机号码: {delivery_phone}")
            return jsonify({"成功": False, "消息": "请输入有效的收货手机号码"}), 400

        # 验证身份证号格式
        if not re.match(r'^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dX]$', id_number):
            print(f"无效的身份证号码: {id_number}")
            return jsonify({"成功": False, "消息": "请输入有效的身份证号码"}), 400

        # 验证金融卡等级
        account_level = account['card_level']
        
        # 定义等级的中文名称
        level_names = {
            'platinum': '铂金卡',
            'black': '黑金卡',
            'supreme': '至尊卡'
        }
        
        if card_type != account_level:
            print(f"卡类型不匹配: 提交的为 {card_type}，账户为 {account_level}")
            return jsonify({
                "成功": False, 
                "消息": f"金融卡登记不符，该账户金融卡等级为{level_names.get(account_level, account_level)}"
            }), 400

        # 验证是否已经提交过地址登记
        cursor.execute("SELECT 1 FROM address_records WHERE phone = ?", (phone,))
        if cursor.fetchone():
            print(f"手机号 {phone} 已提交过地址登记")
            return jsonify({"成功": False, "消息": "该手机号已提交过地址登记"}), 400

        # 保存图片并插入记录
        front_photo_filename = None
        back_photo_filename = None

        try:
            # 确保上传目录存在
            upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            print(f"上传目录: {upload_dir}")
            
            # 保存身份证照片
            try:
                # 保存正面照片
                front_photo_filename = f"{id_number}_front_{int(time.time())}.jpg"
                front_photo_path = os.path.join(upload_dir, front_photo_filename)
                id_front.save(front_photo_path)
                front_photo_filename = os.path.join('uploads', front_photo_filename)
                print(f"保存正面照片成功: {front_photo_path}")
                
                # 保存背面照片
                back_photo_filename = f"{id_number}_back_{int(time.time())}.jpg"
                back_photo_path = os.path.join(upload_dir, back_photo_filename)
                id_back.save(back_photo_path)
                back_photo_filename = os.path.join('uploads', back_photo_filename)
                print(f"保存背面照片成功: {back_photo_path}")
            except Exception as e:
                print(f"保存照片失败: {str(e)}")
                return jsonify({"成功": False, "消息": f"保存照片失败: {str(e)}"}), 500
                
            # 插入数据库记录
            cursor = conn.cursor()
            sql = """INSERT INTO address_records
                     (phone, name, id_number, delivery_phone, delivery_address, card_type, 
                      id_front_photo, id_back_photo, submit_time)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            submit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 打印SQL语句和参数
            print(f"SQL: {sql}")
            print(f"参数: {(phone, name, id_number, delivery_phone, delivery_address, card_type, front_photo_filename, back_photo_filename, submit_time)}")
            
            cursor.execute(sql, (
                phone, name, id_number, delivery_phone, delivery_address, card_type,
                front_photo_filename, back_photo_filename, submit_time
            ))
            
            conn.commit()
            print("数据库提交成功")
            
            # 验证插入是否成功
            cursor.execute("""
                SELECT * FROM address_records 
                WHERE phone=? AND id_number=? 
                ORDER BY submit_time DESC LIMIT 1
            """, (phone, id_number))
            result = cursor.fetchone()
            if result:
                print(f"验证插入成功: {dict(result)}")
            else:
                print("警告：数据似乎没有成功插入")
            
            return jsonify({"成功": True, "消息": "地址登记成功"})

        except sqlite3.IntegrityError as e:
            print(f"数据库唯一性约束错误: {str(e)}")
            # 如果保存失败，删除已上传的文件
            try:
                if front_photo_filename:
                    front_photo_path = os.path.join(upload_dir, os.path.basename(front_photo_filename))
                    if os.path.exists(front_photo_path):
                        os.remove(front_photo_path)
                        print(f"删除正面照片: {front_photo_path}")
                if back_photo_filename:
                    back_photo_path = os.path.join(upload_dir, os.path.basename(back_photo_filename))
                    if os.path.exists(back_photo_path):
                        os.remove(back_photo_path)
                        print(f"删除背面照片: {back_photo_path}")
            except Exception as clean_e:
                print(f"清理照片失败: {str(clean_e)}")
            
            if "UNIQUE constraint failed: address_records.phone" in str(e):
                return jsonify({"成功": False, "消息": "该手机号已经登记过地址"}), 400
            else:
                return jsonify({"成功": False, "消息": "该信息已经登记过"}), 400
        except Exception as e:
            print(f"保存数据失败: {str(e)}")
            # 如果保存失败，删除已上传的文件
            try:
                if front_photo_filename:
                    front_photo_path = os.path.join(upload_dir, os.path.basename(front_photo_filename))
                    if os.path.exists(front_photo_path):
                        os.remove(front_photo_path)
                        print(f"删除正面照片: {front_photo_path}")
                if back_photo_filename:
                    back_photo_path = os.path.join(upload_dir, os.path.basename(back_photo_filename))
                    if os.path.exists(back_photo_path):
                        os.remove(back_photo_path)
                        print(f"删除背面照片: {back_photo_path}")
            except Exception as clean_e:
                print(f"清理照片失败: {str(clean_e)}")
            
            return jsonify({"成功": False, "消息": f"保存数据失败：{str(e)}"}), 500

    except Exception as e:
        import traceback
        print(f"地址登记外层错误: {str(e)}")
        print(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({"成功": False, "消息": f"登记失败：{str(e)}"}), 500

@main.route('/search', methods=['GET'])
@with_db_connection
def search(conn=None):
    try:
        # 获取查询参数
        phone = request.args.get('phone', '').strip()
        name = request.args.get('name', '').strip()
        id_number = request.args.get('id_number', '').strip()

        # 验证必填字段
        if not all([phone, name, id_number]):
            return jsonify({
                "成功": False,
                "消息": "请填写手机号码、姓名和身份证号码"
            }), 400

        print(f"搜索条件: phone={phone}, name={name}, id_number={id_number}")
        
        cursor = conn.cursor()
        results = {"激活登记": None, "地址登记": None}
        
        # 构建查询条件（必须同时匹配三个字段）
        conditions = [
            "phone = ?",
            "name = ?",
            "id_number = ?"
        ]
        params = [phone, name, id_number]
        where_clause = " AND ".join(conditions)
        
        # 搜索激活登记
        try:
            activation_query = f"""
                SELECT id, phone, name, id_number, card_number, card_type, submit_time
                FROM card_activations 
                WHERE {where_clause}
                ORDER BY submit_time DESC
                LIMIT 1
            """
            print(f"激活登记查询: {activation_query}")
            print(f"参数: {params}")
            
            cursor.execute(activation_query, params)
            activation_result = cursor.fetchone()
            
            if activation_result:
                results["激活登记"] = dict(activation_result)
                print(f"找到激活登记: {results['激活登记']}")
        except Exception as e:
            print(f"搜索激活登记出错: {str(e)}")
            
        # 搜索地址登记
        try:
            address_query = f"""
                SELECT id, phone, name, id_number, delivery_phone, delivery_address,
                       card_type, submit_time
                FROM address_records 
                WHERE {where_clause}
                ORDER BY submit_time DESC
                LIMIT 1
            """
            print(f"地址登记查询: {address_query}")
            print(f"参数: {params}")
            
            cursor.execute(address_query, params)
            address_result = cursor.fetchone()
            
            if address_result:
                results["地址登记"] = dict(address_result)
                print(f"找到地址登记: {results['地址登记']}")
        except Exception as e:
            print(f"搜索地址登记出错: {str(e)}")

        if not results["激活登记"] and not results["地址登记"]:
            print("未找到任何记录")
            return jsonify({
                "成功": False,
                "消息": "未找到相关记录"
            }), 404

        print(f"返回结果: {results}")
        return jsonify({
            "成功": True,
            "结果": results
        })

    except Exception as e:
        print(f"搜索失败: {str(e)}")
        return jsonify({
            "成功": False,
            "消息": f"搜索失败：{str(e)}"
        }), 500

@main.route('/update_address_info', methods=['POST'])
@with_db_connection
def update_address_info(conn=None):
    # ... 更新地址信息代码 ...
    pass

@main.route('/adminhou')
def admin_page():
    return render_template('adminhou.html')

@main.route('/admin_dashboard')
@with_db_connection
def admin_dashboard(conn=None):
    try:
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 获取激活登记统计
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN date(submit_time) = ? THEN 1 ELSE 0 END) as today
            FROM card_activations
        """, (today,))
        activation_stats = cursor.fetchone()
        
        # 获取地址登记统计
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN date(submit_time) = ? THEN 1 ELSE 0 END) as today
            FROM address_records
        """, (today,))
        address_stats = cursor.fetchone()
        
        # 获取卡片类型分布
        cursor.execute("""
            SELECT card_type, COUNT(*) as count
            FROM card_activations
            GROUP BY card_type
        """)
        card_type_stats = {row['card_type']: row['count'] for row in cursor.fetchall()}
        
        # 获取发货状态统计
        cursor.execute("""
            SELECT 
                COALESCE(shipping_status, 'pending') as status,
                COUNT(*) as count
            FROM address_records
            GROUP BY COALESCE(shipping_status, 'pending')
        """)
        shipping_stats = {row['status']: row['count'] for row in cursor.fetchall()}
        
        # 获取未发货数量按卡片类型统计
        cursor.execute("""
            SELECT 
                card_type,
                COUNT(*) as count
            FROM address_records
            WHERE COALESCE(shipping_status, 'pending') = 'pending'
            GROUP BY card_type
        """)
        pending_by_type = {row['card_type']: row['count'] for row in cursor.fetchall()}
        
        # 返回统计数据
        return jsonify({
            'status': 'success',
            'total_activations': activation_stats['total'] or 0,
            'today_activations': activation_stats['today'] or 0,
            'total_addresses': address_stats['total'] or 0,
            'today_addresses': address_stats['today'] or 0,
            'card_type_stats': {
                'platinum': card_type_stats.get('platinum', 0),
                'black': card_type_stats.get('black', 0),
                'supreme': card_type_stats.get('supreme', 0)
            },
            'shipping_stats': {
                'shipped': shipping_stats.get('shipped', 0),
                'pending': shipping_stats.get('pending', 0),
                'cancelled': shipping_stats.get('cancelled', 0)
            },
            'pending_by_type': {
                'platinum': pending_by_type.get('platinum', 0),
                'black': pending_by_type.get('black', 0),
                'supreme': pending_by_type.get('supreme', 0)
            }
        })
        
    except Exception as e:
        print(f"获取仪表盘数据失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取数据失败：{str(e)}'
        }), 500

@main.route('/admin_search')
@with_db_connection
def admin_search(conn=None):
    try:
        # 获取查询参数
        query = request.args.get('query', '').strip()
        phone = request.args.get('phone', '').strip()
        
        if not query and not phone:
            return jsonify({'成功': False, '消息': '请提供搜索条件'}), 400
            
        # 使用phone参数或query参数
        search_phone = phone or query
        
        print(f"开始搜索手机号: {search_phone}")
        cursor = conn.cursor()
        
        # 查询信息
        results = {
            "激活登记": None,
            "地址登记": None,
            "账户信息": None
        }
        
        # 查询账户信息（可选）
        cursor.execute("SELECT phone, card_level, create_time FROM accounts WHERE phone = ?", (search_phone,))
        account = cursor.fetchone()
        if account:
            results["账户信息"] = dict(account)
            print(f"找到账户信息: {results['账户信息']}")
        
        # 搜索激活登记
        cursor.execute("""
            SELECT id, phone, name, id_number, card_number, card_type, submit_time
            FROM card_activations 
            WHERE phone = ?
            ORDER BY submit_time DESC
            LIMIT 1
        """, (search_phone,))
        activation = cursor.fetchone()
        if activation:
            results["激活登记"] = dict(activation)
            print(f"找到激活登记: {results['激活登记']}")
        
        # 搜索地址登记
        cursor.execute("""
            SELECT id, phone, name, id_number, delivery_phone, delivery_address,
                   card_type, submit_time, 
                   COALESCE(shipping_status, 'pending') as shipping_status,
                   shipping_time
            FROM address_records 
            WHERE phone = ?
            ORDER BY submit_time DESC
            LIMIT 1
        """, (search_phone,))
        address = cursor.fetchone()
        if address:
            results["地址登记"] = dict(address)
            print(f"找到地址登记: {results['地址登记']}")
        
        # 如果没有找到任何信息，返回错误
        if not results["激活登记"] and not results["地址登记"] and not results["账户信息"]:
            return jsonify({'成功': False, '消息': f'未找到手机号 {search_phone} 的任何信息'}), 404
        
        # 组织一个单一的结果对象用于前端展示
        # 优先使用登记信息中的数据，其次使用账户信息
        result = {
            "phone": search_phone,
            "card_level": None,
            "activated": activation is not None,
            "shipping_status": address["shipping_status"] if address else "pending",
            "name": None,
            "id_number": None
        }
        
        # 填充姓名和身份证号
        if activation:
            result["name"] = activation["name"]
            result["id_number"] = activation["id_number"]
            result["card_level"] = activation["card_type"]
        elif address:
            result["name"] = address["name"]
            result["id_number"] = address["id_number"]
            result["card_level"] = address["card_type"]
        
        # 如果还没有卡等级，但有账户信息，使用账户中的卡等级
        if not result["card_level"] and account:
            result["card_level"] = account["card_level"]
        
        # 如果仍然没有卡等级，设为未知
        if not result["card_level"]:
            result["card_level"] = "unknown"
        
        print(f"返回结果: {result}")
        print(f"详细信息: {results}")
        
        return jsonify({
            "成功": True,
            "结果": results,
            "result": result
        })
        
    except Exception as e:
        print(f"搜索失败: {str(e)}")
        print(f"错误类型: {type(e)}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({'成功': False, '消息': f'搜索失败：{str(e)}'}), 500

@main.route('/admin_update', methods=['POST'])
@with_db_connection
def admin_update(conn=None):
    try:
        data = request.get_json()
        if not data or 'type' not in data or 'data' not in data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400
            
        record_type = data['type']
        record_data = data['data']
        
        if not record_data.get('id'):
            return jsonify({'success': False, 'message': '记录ID不能为空'}), 400
            
        cursor = conn.cursor()
        
        if record_type == 'activation':
            # 验证数据（管理员修改可不填身份证）
            if not all([record_data.get(field) for field in ['phone', 'name', 'card_number', 'card_type']]):
                return jsonify({'success': False, 'message': '请填写所有必要信息'}), 400
                
            # 检查手机号是否已被其他记录使用
            cursor.execute("""
                SELECT id FROM card_activations 
                WHERE phone = ? AND id != ?
            """, (record_data['phone'], record_data['id']))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': '该手机号已被其他记录使用'}), 400
                
            # 检查卡号是否已被其他记录使用
            cursor.execute("""
                SELECT id FROM card_activations 
                WHERE card_number = ? AND id != ?
            """, (record_data['card_number'], record_data['id']))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': '该卡号已被其他记录使用'}), 400
                
            # 更新记录
            cursor.execute("""
                UPDATE card_activations 
                SET phone = ?, name = ?, id_number = ?, card_number = ?, card_type = ?
                WHERE id = ?
            """, (
                record_data['phone'],
                record_data['name'],
                record_data['id_number'],
                record_data['card_number'],
                record_data['card_type'],
                record_data['id']
            ))
            
        elif record_type == 'address':
            # 验证数据（管理员修改可不填身份证）
            if not all([record_data.get(field) for field in ['phone', 'name', 'delivery_phone', 'delivery_address', 'card_type']]):
                return jsonify({'success': False, 'message': '请填写所有必要信息'}), 400
                
            # 检查手机号是否已被其他记录使用
            cursor.execute("""
                SELECT id FROM address_records 
                WHERE phone = ? AND id != ?
            """, (record_data['phone'], record_data['id']))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': '该手机号已被其他记录使用'}), 400
                
            # 更新记录
            cursor.execute("""
                UPDATE address_records 
                SET phone = ?, name = ?, id_number = ?, delivery_phone = ?, 
                    delivery_address = ?, card_type = ?
                WHERE id = ?
            """, (
                record_data['phone'],
                record_data['name'],
                record_data['id_number'],
                record_data['delivery_phone'],
                record_data['delivery_address'],
                record_data['card_type'],
                record_data['id']
            ))
            
        else:
            return jsonify({'success': False, 'message': '无效的记录类型'}), 400
            
        conn.commit()
        return jsonify({'success': True, 'message': '更新成功'})
        
    except Exception as e:
        print(f"更新记录失败: {str(e)}")
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@main.route('/admin_delete', methods=['POST'])
@with_db_connection
def admin_delete(conn=None):
    try:
        data = request.get_json()
        if not data or 'type' not in data or 'id' not in data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400
            
        record_type = data['type']
        record_id = data['id']
        
        cursor = conn.cursor()
        
        if record_type == 'activation':
            # 获取照片路径
            cursor.execute("""
                SELECT id_front_photo, id_back_photo 
                FROM card_activations 
                WHERE id = ?
            """, (record_id,))
            photos = cursor.fetchone()
            
            if photos:
                # 删除照片文件
                for photo in [photos['id_front_photo'], photos['id_back_photo']]:
                    if photo:
                        try:
                            photo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', photo)
                            if os.path.exists(photo_path):
                                os.remove(photo_path)
                                print(f"删除照片: {photo_path}")
                        except Exception as e:
                            print(f"删除照片失败: {str(e)}")
            
            # 删除记录
            cursor.execute("DELETE FROM card_activations WHERE id = ?", (record_id,))
            
        elif record_type == 'address':
            # 获取照片路径
            cursor.execute("""
                SELECT id_front_photo, id_back_photo 
                FROM address_records 
                WHERE id = ?
            """, (record_id,))
            photos = cursor.fetchone()
            
            if photos:
                # 删除照片文件
                for photo in [photos['id_front_photo'], photos['id_back_photo']]:
                    if photo:
                        try:
                            photo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', photo)
                            if os.path.exists(photo_path):
                                os.remove(photo_path)
                                print(f"删除照片: {photo_path}")
                        except Exception as e:
                            print(f"删除照片失败: {str(e)}")
            
            # 删除记录
            cursor.execute("DELETE FROM address_records WHERE id = ?", (record_id,))
            
        else:
            return jsonify({'success': False, 'message': '无效的记录类型'}), 400
            
        conn.commit()
        return jsonify({'success': True, 'message': '删除成功'})
        
    except Exception as e:
        print(f"删除记录失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'}), 500

@main.route('/admin_add_record/<record_type>', methods=['POST'])
@with_db_connection
def admin_add_record(record_type, conn=None):
    # 示例逻辑：添加记录，根据 record_type 执行相应操作
    return jsonify({'success': True, 'message': f'{record_type} 记录已添加'})

@main.route('/update_shipping_status', methods=['POST'])
@with_db_connection
@validate_json_input('phones', 'status')
def update_shipping_status(conn=None):
    try:
        data = request.get_json()
        phones = data['phones']
        status = data['status']
        
        # 验证状态值
        valid_statuses = ['pending', 'shipped', 'cancelled']
        if status not in valid_statuses:
            return jsonify({'success': False, 'message': '无效的状态值'}), 400
            
        cursor = conn.cursor()
        
        # 检查是否所有手机号都存在
        not_found = []
        updated_count = 0
        
        for phone in phones:
            # 检查手机号是否存在
            cursor.execute("SELECT 1 FROM address_records WHERE phone = ?", (phone,))
            if not cursor.fetchone():
                not_found.append(phone)
                continue
                
            # 更新发货状态
            if status == 'shipped':
                # 如果改为已发货状态，记录发货时间
                shipping_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    UPDATE address_records 
                    SET shipping_status = ?, shipping_time = ?
                    WHERE phone = ?
                """, (status, shipping_time, phone))
            else:
                cursor.execute("""
                    UPDATE address_records 
                    SET shipping_status = ?
                    WHERE phone = ?
                """, (status, phone))
                
            updated_count += cursor.rowcount
            
        conn.commit()
        
        return jsonify({
            'success': True, 
            'message': f'成功更新 {updated_count} 条记录，{len(not_found)} 条记录未找到',
            'updated_count': updated_count,
            'not_found': len(not_found),
            'not_found_phones': not_found[:10]  # 只返回前10个未找到的手机号，避免数据过大
        })
        
    except Exception as e:
        print(f"更新发货状态失败: {str(e)}")
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@main.route('/admin_add_account', methods=['POST'])
@with_db_connection
def admin_add_account(conn=None):
    try:
        data = request.get_json()
        if not data or 'phone' not in data or 'card_level' not in data:
            return jsonify({'success': False, 'message': '请提供手机号码和金融卡等级'}), 400
            
        phone = data['phone'].strip()
        card_level = data['card_level'].strip().lower()
        
        # 验证手机号格式
        if not re.match(r'^1[3-9]\d{9}$', phone):
            return jsonify({'success': False, 'message': '请输入有效的手机号码'}), 400
            
        # 验证金融卡等级
        valid_levels = {'platinum', 'black', 'supreme'}
        if card_level not in valid_levels:
            return jsonify({'success': False, 'message': '无效的金融卡等级'}), 400
            
        cursor = conn.cursor()
        
        # 检查手机号是否已存在
        cursor.execute("SELECT 1 FROM accounts WHERE phone = ?", (phone,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '该手机号已注册'}), 400
            
        # 添加账户，包含金融卡等级
        create_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO accounts (phone, card_level, create_time)
            VALUES (?, ?, ?)
        """, (phone, card_level, create_time))
        
        conn.commit()
        return jsonify({'success': True, 'message': '账户添加成功'})
        
    except Exception as e:
        print(f"添加账户失败: {str(e)}")
        return jsonify({'success': False, 'message': f'添加失败：{str(e)}'}), 500

@main.route('/admin_batch_add_accounts', methods=['POST'])
@with_db_connection
def admin_batch_add_accounts(conn=None):
    logger = logging.getLogger(__name__)
    try:
        data = request.get_json()
        if not data or not isinstance(data.get('accounts'), list):
            logger.warning("请求数据无效：%s", data)
            return jsonify({'success': False, 'message': '请提供账户列表'}), 400
            
        accounts = data['accounts']
        if not accounts:
            logger.warning("账户列表为空")
            return jsonify({'success': False, 'message': '账户列表为空'}), 400
            
        logger.info("开始处理批量导入账户，总数：%d", len(accounts))
        cursor = conn.cursor()
        create_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        success_count = 0
        failed_records = []
        
        # 验证卡片等级是否有效
        valid_levels = {'platinum', 'black', 'supreme'}
        
        for account in accounts:
            try:
                # 验证数据格式
                if not isinstance(account, dict):
                    failed_records.append({
                        'account': account,
                        'reason': '账户数据格式无效'
                    })
                    continue
                    
                phone = account.get('phone', '').strip()
                card_level = account.get('card_level', '').strip().lower()
                
                # 验证手机号
                if not re.match(r'^1[3-9]\d{9}$', phone):
                    failed_records.append({
                        'account': account,
                        'reason': '手机号格式无效'
                    })
                    continue
                    
                # 验证卡片等级
                if card_level not in valid_levels:
                    failed_records.append({
                        'account': account,
                        'reason': f'无效的卡片等级：{card_level}'
                    })
                    continue
                    
                # 检查手机号是否已存在
                cursor.execute("SELECT 1 FROM accounts WHERE phone = ?", (phone,))
                if cursor.fetchone():
                    failed_records.append({
                        'account': account,
                        'reason': '手机号已存在'
                    })
                    continue
                    
                # 添加账户
                cursor.execute("""
                    INSERT INTO accounts (phone, card_level, create_time)
                    VALUES (?, ?, ?)
                """, (phone, card_level, create_time))
                
                success_count += 1
                logger.debug("成功添加账户: %s", phone)
                
            except Exception as e:
                logger.error("处理账户时出错: %s, 错误: %s", account, str(e))
                failed_records.append({
                    'account': account,
                    'reason': str(e)
                })
        
        conn.commit()
        logger.info("批量导入完成: 成功 %d 个, 失败 %d 个", success_count, len(failed_records))
        
        # 保存失败记录
        if failed_records:
            save_failed_records('account', failed_records)
            
        return jsonify({
            'success': True,
            'message': f'成功添加 {success_count} 个账户，失败 {len(failed_records)} 个',
            'success_count': success_count,
            'failed_count': len(failed_records),
            'has_failed_records': len(failed_records) > 0
        })
        
    except Exception as e:
        logger.error("批量添加账户失败: %s", str(e), exc_info=True)
        return jsonify({'success': False, 'message': f'添加失败：{str(e)}'}), 500

@main.route('/admin_get_accounts')
@with_db_connection
def admin_get_accounts(conn=None):
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        search = request.args.get('search', '').strip()
        
        # 计算偏移量
        offset = (page - 1) * page_size
        
        cursor = conn.cursor()
        
        # 构建查询条件
        where_clause = "WHERE phone LIKE ?" if search else ""
        search_param = f"%{search}%" if search else None
        
        # 获取总记录数
        count_sql = f"SELECT COUNT(*) as total FROM accounts {where_clause}"
        cursor.execute(count_sql, (search_param,) if search else ())
        total = cursor.fetchone()['total']
        
        # 获取分页数据
        sql = f"""
            SELECT phone, card_level, create_time
            FROM accounts
            {where_clause}
            ORDER BY create_time DESC
            LIMIT ? OFFSET ?
        """
        
        # 执行查询
        params = [search_param, page_size, offset] if search else [page_size, offset]
        cursor.execute(sql, tuple(params))
        
        accounts = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'accounts': accounts,
            'total': total,
            'page': page,
            'page_size': page_size
        })
        
    except Exception as e:
        print(f"获取账户列表失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500

@main.route('/admin_delete_account', methods=['POST'])
@with_db_connection
def admin_delete_account(conn=None):
    try:
        data = request.get_json()
        if not data or 'phone' not in data:
            return jsonify({'success': False, 'message': '请提供手机号码'}), 400
            
        phone = data['phone'].strip()
        cursor = conn.cursor()
        
        # 检查是否存在相关的激活或地址记录
        cursor.execute("""
            SELECT 1 FROM card_activations WHERE phone = ?
            UNION ALL
            SELECT 1 FROM address_records WHERE phone = ?
        """, (phone, phone))
        
        if cursor.fetchone():
            return jsonify({
                'success': False,
                'message': '该账户已有激活或地址登记记录，无法删除'
            }), 400
            
        # 删除账户
        cursor.execute("DELETE FROM accounts WHERE phone = ?", (phone,))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': '账户不存在'}), 404
            
        conn.commit()
        return jsonify({'success': True, 'message': '账户删除成功'})
        
    except Exception as e:
        print(f"删除账户失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'}), 500

@main.route('/admin_add_card', methods=['POST'])
@with_db_connection
def admin_add_card(conn=None):
    try:
        data = request.get_json()
        if not data or 'card_number' not in data:
            return jsonify({'success': False, 'message': '请提供卡号'}), 400
            
        card_number = data['card_number'].strip()
        
        # 验证卡号格式（1-19位数字）
        if not re.match(r'^\d{1,19}$', card_number):
            return jsonify({'success': False, 'message': '请输入1-19位数字的卡号'}), 400
            
        cursor = conn.cursor()
        
        # 检查卡号是否已存在
        cursor.execute("SELECT 1 FROM financial_cards WHERE card_number = ?", (card_number,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '该卡号已存在'}), 400
            
        # 添加金融卡
        create_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO financial_cards (card_number, create_time)
            VALUES (?, ?)
        """, (card_number, create_time))
        
        conn.commit()
        return jsonify({'success': True, 'message': '金融卡添加成功'})
        
    except Exception as e:
        print(f"添加金融卡失败: {str(e)}")
        return jsonify({'success': False, 'message': f'添加失败：{str(e)}'}), 500

@main.route('/admin_batch_add_cards', methods=['POST'])
@with_db_connection
def admin_batch_add_cards(conn=None):
    logger = logging.getLogger(__name__)
    try:
        data = request.get_json()
        if not data or not isinstance(data.get('cards'), list):
            logger.warning("请求数据无效：%s", data)
            return jsonify({'success': False, 'message': '请提供金融卡列表'}), 400
            
        cards = data['cards']
        if not cards:
            logger.warning("卡片列表为空")
            return jsonify({'success': False, 'message': '金融卡列表为空'}), 400
            
        logger.info("开始处理批量导入金融卡，总数：%d", len(cards))
        cursor = conn.cursor()
        create_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        success_count = 0
        failed_records = []
        
        for card in cards:
            try:
                # 验证数据格式
                if not isinstance(card, dict):
                    failed_records.append({
                        'card': card,
                        'reason': '卡片数据格式无效'
                    })
                    continue
                    
                card_number = card.get('card_number', '').strip()
                
                # 验证卡号格式
                if not re.match(r'^\d{16,19}$', card_number):
                    failed_records.append({
                        'card': card,
                        'reason': '卡号格式无效'
                    })
                    continue
                    
                # 检查卡号是否已存在
                cursor.execute("SELECT 1 FROM financial_cards WHERE card_number = ?", (card_number,))
                if cursor.fetchone():
                    failed_records.append({
                        'card': card,
                        'reason': '卡号已存在'
                    })
                    continue
                    
                # 添加金融卡
                cursor.execute("""
                    INSERT INTO financial_cards (card_number, create_time)
                    VALUES (?, ?)
                """, (card_number, create_time))
                
                success_count += 1
                logger.debug("成功添加卡号: %s", card_number)
                
            except Exception as e:
                logger.error("处理卡号时出错: %s, 错误: %s", card, str(e))
                failed_records.append({
                    'card': card,
                    'reason': str(e)
                })
        
        conn.commit()
        logger.info("批量导入完成: 成功 %d 张, 失败 %d 张", success_count, len(failed_records))
        
        # 保存失败记录
        if failed_records:
            save_failed_records('card', failed_records)
            
        return jsonify({
            'success': True,
            'message': f'成功导入 {success_count} 张金融卡，失败 {len(failed_records)} 张',
            'success_count': success_count,
            'failed_count': len(failed_records),
            'has_failed_records': len(failed_records) > 0
        })
        
    except Exception as e:
        logger.error("批量导入金融卡失败: %s", str(e), exc_info=True)
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'}), 500

@main.route('/admin_get_cards')
@with_db_connection
def admin_get_cards(conn=None):
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        search = request.args.get('search', '').strip()
        status = request.args.get('status', 'all').strip()
        
        # 计算偏移量
        offset = (page - 1) * page_size
        
        cursor = conn.cursor()
        
        # 构建查询条件
        conditions = []
        params = []
        
        if search:
            conditions.append("card_number LIKE ?")
            params.append(f"%{search}%")
            
        if status != 'all':
            conditions.append("status = ?")
            params.append(status)
            
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        # 获取总记录数
        count_sql = f"SELECT COUNT(*) as total FROM financial_cards {where_clause}"
        cursor.execute(count_sql, tuple(params))
        total = cursor.fetchone()['total']
        
        # 获取分页数据
        sql = f"""
            SELECT card_number, create_time, status
            FROM financial_cards
            {where_clause}
            ORDER BY create_time DESC
            LIMIT ? OFFSET ?
        """
        
        # 执行查询
        params.extend([page_size, offset])
        cursor.execute(sql, tuple(params))
        
        cards = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'cards': cards,
            'total': total,
            'page': page,
            'page_size': page_size
        })
        
    except Exception as e:
        print(f"获取金融卡列表失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500

@main.route('/admin_delete_card', methods=['POST'])
@with_db_connection
def admin_delete_card(conn=None):
    try:
        data = request.get_json()
        if not data or 'card_number' not in data:
            return jsonify({'success': False, 'message': '请提供卡号'}), 400
            
        card_number = data['card_number'].strip()
        cursor = conn.cursor()
        
        # 检查是否已被激活
        cursor.execute("""
            SELECT 1 FROM card_activations WHERE card_number = ?
        """, (card_number,))
        
        if cursor.fetchone():
            return jsonify({
                'success': False,
                'message': '该金融卡已被激活，无法删除'
            }), 400
            
        # 删除金融卡
        cursor.execute("DELETE FROM financial_cards WHERE card_number = ?", (card_number,))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': '金融卡不存在'}), 404
            
        conn.commit()
        return jsonify({'success': True, 'message': '金融卡删除成功'})
        
    except Exception as e:
        print(f"删除金融卡失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'}), 500

@main.route('/admin_add_activation', methods=['POST'])
@with_db_connection
def admin_add_activation(conn=None):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请提供激活登记数据'}), 400
            
        # 验证必填字段
        required_fields = ['phone', 'name', 'id_number', 'card_number', 'card_type']
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'message': '请提供所有必要信息'}), 400
            
        # 验证账户是否存在
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM accounts WHERE phone = ?", (data['phone'],))
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': '该手机号未注册，请先添加账户'}), 400
            
        # 验证金融卡是否存在且可用
        cursor.execute("""
            SELECT status FROM financial_cards 
            WHERE card_number = ?
        """, (data['card_number'],))
        card = cursor.fetchone()
        
        if not card:
            return jsonify({'success': False, 'message': '该金融卡不存在'}), 400
            
        if card['status'] != 'available':
            return jsonify({'success': False, 'message': '该金融卡已被使用或状态异常'}), 400
            
        # 检查唯一性
        cursor.execute("""
            SELECT phone, card_number 
            FROM card_activations 
            WHERE phone = ? OR card_number = ?
        """, (data['phone'], data['card_number']))
        
        existing = cursor.fetchone()
        if existing:
            if existing['phone'] == data['phone']:
                return jsonify({'success': False, 'message': '该手机号已经登记过'}), 400
            elif existing['card_number'] == data['card_number']:
                return jsonify({'success': False, 'message': '该卡号已经登记过'}), 400
                
        # 添加激活登记记录
        submit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO card_activations 
            (phone, name, id_number, card_number, card_type, submit_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data['phone'], data['name'], data['id_number'],
            data['card_number'], data['card_type'], submit_time
        ))
        
        # 更新金融卡状态
        cursor.execute("""
            UPDATE financial_cards 
            SET status = 'activated' 
            WHERE card_number = ?
        """, (data['card_number'],))
        
        conn.commit()
        return jsonify({'success': True, 'message': '激活登记添加成功'})
        
    except Exception as e:
        print(f"添加激活登记失败: {str(e)}")
        return jsonify({'success': False, 'message': f'添加失败：{str(e)}'}), 500

@main.route('/admin_batch_add_activations', methods=['POST'])
@with_db_connection
def admin_batch_add_activations(conn=None):
    try:
        # 检查是否是Excel文件上传
        if 'file' in request.files:
            file = request.files['file']
            if not file.filename:
                return jsonify({'success': False, 'message': '没有选择文件'}), 400
                
            # 检查文件类型
            if not file.filename.lower().endswith(('.xlsx', '.xls')):
                return jsonify({'success': False, 'message': '请上传Excel文件（.xlsx或.xls格式）'}), 400
                
            try:
                # 读取Excel文件
                df = pd.read_excel(file)
                
                # 验证必要的列是否存在
                required_columns = ['手机号码', '姓名', '身份证号', '金融卡号', '卡片类型']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    return jsonify({
                        'success': False,
                        'message': f'Excel文件缺少必要的列：{", ".join(missing_columns)}'
                    }), 400
                    
                # 转换DataFrame为字典列表
                activations = df.to_dict('records')
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Excel文件读取失败：{str(e)}'
                }), 400
        else:
            # JSON格式的数据
            data = request.get_json()
            if not data or 'activations' not in data:
                return jsonify({'success': False, 'message': '请提供激活登记数据列表'}), 400
                
            activations = data['activations']
            
        if not activations:
            return jsonify({'success': False, 'message': '激活登记数据列表为空'}), 400
            
        cursor = conn.cursor()
        submit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        success_count = 0
        failed_records = []
        
        for record in activations:
            try:
                # 验证必填字段
                required_fields = ['手机号码', '姓名', '身份证号', '金融卡号', '卡片类型']
                if not all(field in record for field in required_fields):
                    failed_records.append({
                        'record': record,
                        'reason': '缺少必要信息'
                    })
                    continue
                    
                # 验证账户是否存在
                cursor.execute("SELECT 1 FROM accounts WHERE phone = ?", (record['手机号码'],))
                if not cursor.fetchone():
                    failed_records.append({
                        'record': record,
                        'reason': '手机号未注册'
                    })
                    continue
                    
                # 验证金融卡是否存在且可用
                cursor.execute("""
                    SELECT status FROM financial_cards 
                    WHERE card_number = ?
                """, (record['金融卡号'],))
                card = cursor.fetchone()
                
                if not card:
                    failed_records.append({
                        'record': record,
                        'reason': '金融卡不存在'
                    })
                    continue
                    
                if card['status'] != 'available':
                    failed_records.append({
                        'record': record,
                        'reason': '金融卡已被使用或状态异常'
                    })
                    continue
                    
                # 检查唯一性
                cursor.execute("""
                    SELECT phone, card_number 
                    FROM card_activations 
                    WHERE phone = ? OR card_number = ?
                """, (record['手机号码'], record['金融卡号']))
                
                existing = cursor.fetchone()
                if existing:
                    if existing['phone'] == record['手机号码']:
                        failed_records.append({
                            'record': record,
                            'reason': '手机号已经登记过'
                        })
                    elif existing['card_number'] == record['金融卡号']:
                        failed_records.append({
                            'record': record,
                            'reason': '卡号已经登记过'
                        })
                    continue
                    
                # 添加激活登记记录
                cursor.execute("""
                    INSERT INTO card_activations 
                    (phone, name, id_number, card_number, card_type, id_front_photo, id_back_photo, submit_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record['手机号码'], record['姓名'], record['身份证号'],
                    record['金融卡号'], record['卡片类型'], 
                    'batch_import', 'batch_import',  # 为照片字段设置默认值
                    submit_time
                ))
                
                # 更新金融卡状态
                cursor.execute("""
                    UPDATE financial_cards 
                    SET status = 'activated' 
                    WHERE card_number = ?
                """, (record['金融卡号'],))
                
                success_count += 1
                
            except Exception as e:
                failed_records.append({
                    'record': record,
                    'reason': str(e)
                })
        
        conn.commit()
        
        # 保存失败记录到临时文件
        if failed_records:
            save_failed_records('activation', failed_records)
        
        return jsonify({
            'success': True,
            'message': f'成功导入 {success_count} 条记录',
            'success_count': success_count,
            'failed_count': len(failed_records),
            'has_failed_records': len(failed_records) > 0
        })
        
    except Exception as e:
        print(f"批量导入激活登记失败: {str(e)}")
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'}), 500

@main.route('/download_template/<template_type>')
def download_template(template_type):
    try:
        if template_type not in ['activation', 'address']:
            return jsonify({'success': False, 'message': '无效的模板类型'}), 400
            
        # 创建模板内容
        if template_type == 'activation':
            content = "手机号码,姓名,身份证号,金融卡号,卡片类型\n"
            content += "13800138000,张三,110101199001011234,1234567890123456,platinum\n"
            content += "13900139000,李四,110101199001011235,1234567890123457,black\n"
            content += "13700137000,王五,110101199001011236,1234567890123458,supreme\n"
            filename = "activation_template.csv"
        else:
            content = "手机号码,姓名,身份证号,收货电话,收货地址,卡片类型\n"
            content += "13800138000,张三,110101199001011234,13900139000,北京市朝阳区xxx,platinum\n"
            content += "13900139000,李四,110101199001011235,13700137000,上海市浦东新区xxx,black\n"
            content += "13700137000,王五,110101199001011236,13800138000,广州市天河区xxx,supreme\n"
            filename = "address_template.csv"
            
        # 添加BOM头，确保Excel正确识别UTF-8编码
        content = '\ufeff' + content
            
        # 设置响应头
        response = make_response(content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        print(f"下载模板失败: {str(e)}")
        return jsonify({'success': False, 'message': f'下载失败：{str(e)}'}), 500

@main.route('/download_failed_records/<import_type>')
def download_failed_records(import_type):
    try:
        if import_type not in ['activation', 'address', 'account', 'card', 'shipping']:
            return jsonify({'success': False, 'message': '无效的导入类型'}), 400
            
        # 使用FileHandler获取失败记录
        file_handler = FileHandler()
        failed_records = file_handler.get_failed_records(import_type)
        
        if not failed_records:
            return jsonify({'success': False, 'message': '没有失败记录可供下载'}), 404
            
        # 生成CSV内容
        content = '\ufeff'  # 添加BOM头
        if import_type == 'activation':
            content += "手机号码,姓名,身份证号,金融卡号,卡片类型,失败原因\n"
            for record in failed_records:
                data = record['record']
                content += f"{data.get('手机号码', '')},{data.get('姓名', '')},{data.get('身份证号', '')},"
                content += f"{data.get('金融卡号', '')},{data.get('卡片类型', '')},{record.get('reason', '')}\n"
        elif import_type == 'address':
            content += "手机号码,姓名,身份证号,收货电话,收货地址,卡片类型,失败原因\n"
            for record in failed_records:
                data = record['record']
                content += f"{data.get('手机号码', '')},{data.get('姓名', '')},{data.get('身份证号', '')},"
                content += f"{data.get('收货电话', '')},{data.get('收货地址', '')},{data.get('卡片类型', '')},{record.get('reason', '')}\n"
        elif import_type == 'account':
            content += "手机号码,失败原因\n"
            for record in failed_records:
                content += f"{record.get('phone', '')},{record.get('reason', '')}\n"
        elif import_type == 'card':
            content += "卡号,失败原因\n"
            for record in failed_records:
                content += f"{record.get('card_number', '')},{record.get('reason', '')}\n"
        else:  # shipping
            content += "手机号码,发货状态更新失败原因\n"
            for record in failed_records:
                content += f"{record.get('phone', '')},{record.get('reason', '')}\n"
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{import_type}_failed_records_{timestamp}.csv"
        
        # 设置响应头
        response = make_response(content)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
        
        # URL编码文件名
        encoded_filename = quote(filename)
        response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
        
        return response
        
    except Exception as e:
        print(f"下载失败记录时出错: {str(e)}")
        return jsonify({'success': False, 'message': f'下载失败：{str(e)}'}), 500

@main.route('/admin_batch_add_addresses', methods=['POST'])
@with_db_connection
def admin_batch_add_addresses(conn=None):
    try:
        # 检查是否是Excel文件上传
        if 'file' in request.files:
            file = request.files['file']
            if not file.filename:
                return jsonify({'success': False, 'message': '没有选择文件'}), 400
                
            # 检查文件类型
            if not file.filename.lower().endswith(('.xlsx', '.xls')):
                return jsonify({'success': False, 'message': '请上传Excel文件（.xlsx或.xls格式）'}), 400
                
            try:
                # 读取Excel文件
                df = pd.read_excel(file)
                
                # 验证必要的列是否存在
                required_columns = ['手机号码', '姓名', '身份证号', '收货电话', '收货地址', '卡片类型']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    return jsonify({
                        'success': False,
                        'message': f'Excel文件缺少必要的列：{", ".join(missing_columns)}'
                    }), 400
                    
                # 转换DataFrame为字典列表
                addresses = df.to_dict('records')
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Excel文件读取失败：{str(e)}'
                }), 400
        else:
            # JSON格式的数据
            data = request.get_json()
            if not data or 'addresses' not in data:
                return jsonify({'success': False, 'message': '请提供地址登记数据列表'}), 400
                
            addresses = data['addresses']
            
        if not addresses:
            return jsonify({'success': False, 'message': '地址登记数据列表为空'}), 400
            
        cursor = conn.cursor()
        submit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        success_count = 0
        failed_records = []
        
        for record in addresses:
            try:
                # 验证必填字段
                required_fields = ['手机号码', '姓名', '身份证号', '收货电话', '收货地址', '卡片类型']
                if not all(field in record for field in required_fields):
                    failed_records.append({
                        'record': record,
                        'reason': '缺少必要信息'
                    })
                    continue
                    
                # 验证账户是否存在
                cursor.execute("SELECT 1 FROM accounts WHERE phone = ?", (record['手机号码'],))
                if not cursor.fetchone():
                    failed_records.append({
                        'record': record,
                        'reason': '手机号未注册'
                    })
                    continue
                    
                # 检查唯一性
                cursor.execute("""
                    SELECT phone FROM address_records 
                    WHERE phone = ?
                """, (record['手机号码'],))
                
                if cursor.fetchone():
                    failed_records.append({
                        'record': record,
                        'reason': '手机号已经登记过'
                    })
                    continue
                    
                # 添加地址登记记录
                cursor.execute("""
                    INSERT INTO address_records 
                    (phone, name, id_number, delivery_phone, delivery_address, card_type, 
                     id_front_photo, id_back_photo, submit_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record['手机号码'], record['姓名'], record['身份证号'],
                    record['收货电话'], record['收货地址'], record['卡片类型'],
                    'batch_import', 'batch_import',  # 为照片字段设置默认值
                    submit_time
                ))
                
                success_count += 1
                
            except Exception as e:
                failed_records.append({
                    'record': record,
                    'reason': str(e)
                })
        
        conn.commit()
        
        # 保存失败记录到临时文件
        if failed_records:
            save_failed_records('address', failed_records)
        
        return jsonify({
            'success': True,
            'message': f'成功导入 {success_count} 条记录',
            'success_count': success_count,
            'failed_count': len(failed_records),
            'has_failed_records': len(failed_records) > 0
        })
        
    except Exception as e:
        print(f"批量导入地址登记失败: {str(e)}")
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'}), 500

@main.route('/admin_get_shipping_records')
@with_db_connection
def admin_get_shipping_records(conn=None):
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        search = request.args.get('search', '').strip()
        
        # 计算偏移量
        offset = (page - 1) * page_size
        
        cursor = conn.cursor()
        
        # 构建查询条件
        where_clause = ""
        params = []
        
        if search:
            where_clause = "WHERE phone LIKE ?"
            params = [f"%{search}%"]
        
        # 获取总记录数
        count_sql = f"""
            SELECT COUNT(*) as total 
            FROM address_records 
            {where_clause}
        """
        cursor.execute(count_sql, tuple(params) if params else ())
        total = cursor.fetchone()['total']
        
        # 获取分页数据
        sql = f"""
            SELECT id, phone, name, id_number, delivery_phone, delivery_address,
                   card_type, shipping_status, shipping_time, submit_time
            FROM address_records
            {where_clause}
            ORDER BY submit_time DESC
            LIMIT ? OFFSET ?
        """
        
        # 添加分页参数
        params.extend([page_size, offset])
        
        # 执行查询
        cursor.execute(sql, tuple(params))
        records = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'records': records,
            'total': total,
            'page': page,
            'page_size': page_size
        })
        
    except Exception as e:
        print(f"获取发货记录列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败：{str(e)}'
        }), 500

@main.route('/api/admin/export', methods=['POST'])
@with_db_connection
def export_data(conn=None):
    try:
        # 获取导出条件
        conditions = json.loads(request.form.get('conditions', '{}'))
        
        # 构建查询条件
        where_clauses = []
        params = []
        
        # 按金融卡类型筛选
        if conditions.get('card_type_enabled'):
            where_clauses.append("ar.card_type = ?")
            params.append(conditions['card_type'])
            
        # 按发货状态筛选
        if conditions.get('shipping_status_enabled'):
            where_clauses.append("COALESCE(ar.shipping_status, 'pending') = ?")
            params.append(conditions['shipping_status'])
            
        # 按手机号码筛选
        if conditions.get('phones_enabled') and conditions.get('phones'):
            phones = conditions['phones']
            if phones:
                placeholders = ','.join(['?' for _ in phones])
                where_clauses.append(f"ar.phone IN ({placeholders})")
                params.extend(phones)
                
        # 按日期范围筛选
        if conditions.get('date_enabled'):
            if conditions.get('date_start'):
                where_clauses.append("date(ar.submit_time) >= ?")
                params.append(conditions['date_start'])
            if conditions.get('date_end'):
                where_clauses.append("date(ar.submit_time) <= ?")
                params.append(conditions['date_end'])
                
        # 构建WHERE子句
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # 构建查询SQL
        sql = f"""
            SELECT ar.phone, ar.name, ar.id_number, ar.delivery_phone, ar.delivery_address,
                   ar.card_type, COALESCE(ar.shipping_status, 'pending') as shipping_status, 
                   ar.shipping_time, ar.submit_time
            FROM address_records ar
            WHERE {where_clause}
            ORDER BY ar.submit_time DESC
        """
        
        # 添加数量限制
        if conditions.get('limit_enabled') and conditions.get('limit_count'):
            sql += f" LIMIT {int(conditions['limit_count'])}"
            
        # 执行查询
        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        records = cursor.fetchall()
        
        if not records:
            return jsonify({
                'success': False,
                'message': '没有符合条件的数据'
            }), 404
            
        # 生成CSV内容
        output = StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        headers = ['手机号码', '姓名', '身份证号', '收货电话', '收货地址', '卡片类型', 
                  '发货状态', '发货时间', '提交时间']
        writer.writerow(headers)
        
        # 写入数据
        for record in records:
            row = [
                record['phone'],
                record['name'],
                record['id_number'],
                record['delivery_phone'],
                record['delivery_address'],
                getCardTypeName(record['card_type']),
                getShippingStatusName(record['shipping_status']),
                record['shipping_time'] or '',
                record['submit_time']
            ]
            writer.writerow(row)
            
        # 添加BOM头，确保Excel正确识别UTF-8编码
        output_str = '\ufeff' + output.getvalue()
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'address_records_{timestamp}.csv'
        
        # 生成响应
        response = make_response(output_str)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
        
        # URL编码文件名
        encoded_filename = quote(filename)
        response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
        
        return response
        
    except Exception as e:
        print(f"导出数据失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'导出失败：{str(e)}'
        }), 500

def getCardTypeName(type):
    """获取卡片类型名称"""
    type_names = {
        'platinum': '铂金卡',
        'black': '黑金卡',
        'supreme': '至尊卡'
    }
    return type_names.get(type, type)

def getShippingStatusName(status):
    """获取发货状态名称"""
    status_names = {
        'pending': '待发货',
        'shipped': '已发货',
        'cancelled': '已取消'
    }
    return status_names.get(status, status)

@main.route('/replay')
def replay():
    """直播回放页面"""
    return render_template('replay.html')

@main.route('/replays/<path:filename>')
def serve_video_direct(filename):
    """直接提供视频文件访问（无需static前缀）"""
    try:
        logger = logging.getLogger(__name__)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        video_dir = os.path.join(base_dir, 'static', 'replays')
        video_path = os.path.join(video_dir, filename)
        logger.info(f"请求视频文件: {filename}, 目录: {video_dir}")

        if not os.path.exists(video_path):
            logger.error(f"视频文件不存在: {video_path}")
            return "视频文件不存在", 404

        # 获取文件扩展名
        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        # 设置正确的MIME类型和编解码器
        mime_types = {
            '.mp4': 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"',  # H.264 + AAC
            '.webm': 'video/webm; codecs="vp8, vorbis"',           # WebM
            '.m4v': 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"',  # H.264 + AAC
            '.mov': 'video/quicktime',                              # QuickTime
            '.ogg': 'video/ogg; codecs="theora, vorbis"'           # Ogg
        }

        mime_type = mime_types.get(ext, 'application/octet-stream')
        file_size = os.path.getsize(video_path)

        # 检查是否为iOS设备
        user_agent = request.headers.get('User-Agent', '').lower()
        is_ios = 'iphone' in user_agent or 'ipad' in user_agent or 'ipod' in user_agent

        # 如果是iOS设备且不是MP4格式，建议下载或转换
        if is_ios and ext not in ['.mp4', '.m4v']:
            return jsonify({
                'success': False,
                'message': '当前视频格式不支持在iOS设备上直接播放，请使用MP4格式',
                'download_url': url_for('static', filename=f'replays/{filename}')
            }), 400

        # 处理范围请求
        range_header = request.headers.get('Range')
        
        if range_header:
            byte1, byte2 = 0, None
            match = re.search(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                groups = match.groups()
                if groups[0]:
                    byte1 = int(groups[0])
                if groups[1]:
                    byte2 = int(groups[1])

            if byte2 is None:
                byte2 = min(byte1 + 2*1024*1024, file_size - 1)  # 每次传输2MB
            length = byte2 - byte1 + 1

            def generate():
                try:
                    with open(video_path, 'rb') as video:
                        video.seek(byte1)
                        remaining = length
                        chunk_size = 32768  # 32KB chunks
                        while remaining:
                            chunk = video.read(min(chunk_size, remaining))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                            yield chunk
                except Exception as e:
                    logger.error(f"视频流传输错误: {str(e)}", exc_info=True)

            response = Response(
                generate(),
                206,
                mimetype=mime_type.split(';')[0],  # 只使用主MIME类型
                direct_passthrough=True
            )
            
            response.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
            response.headers.add('Accept-Ranges', 'bytes')
            response.headers.add('Content-Length', str(length))
            response.headers.add('Cache-Control', 'public, max-age=31536000')
            
            # 添加跨域支持
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
            response.headers.add('Access-Control-Allow-Headers', 'Range')
            
            # 添加编解码器信息
            if ';' in mime_type:
                response.headers.add('Content-Type', mime_type)
            
            return response
        else:
            # 对于完整请求，返回文件
            response = send_file(
                video_path,
                mimetype=mime_type.split(';')[0],
                conditional=True,
                add_etags=True
            )
            
            # 添加编解码器信息
            if ';' in mime_type:
                response.headers['Content-Type'] = mime_type
            
            response.headers.add('Cache-Control', 'public, max-age=31536000')
            response.headers.add('Accept-Ranges', 'bytes')
            return response

    except Exception as e:
        logger.error(f"视频访问失败: {str(e)}", exc_info=True)
        return "视频访问失败", 500

@main.route('/replays/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    """提供缩略图访问"""
    try:
        logger = logging.getLogger(__name__)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        thumbnail_dir = os.path.join(base_dir, 'static', 'replays', 'thumbnails')
        logger.info(f"请求缩略图: {filename}, 目录: {thumbnail_dir}")
        
        if not os.path.exists(os.path.join(thumbnail_dir, filename)):
            # 如果缩略图不存在，返回默认图片
            return send_from_directory(os.path.join(base_dir, 'static'), 'video-placeholder.jpg')
            
        return send_from_directory(thumbnail_dir, filename)
    except Exception as e:
        logger.error(f"缩略图访问失败: {str(e)}", exc_info=True)
        return "缩略图不存在", 404

@main.route('/get_replay_videos')
def get_replay_videos():
    """获取回放视频列表"""
    logger = logging.getLogger(__name__)
    try:
        # 视频目录路径
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        video_dir = os.path.join(base_dir, 'static', 'replays')
        logger.info(f"视频目录路径: {video_dir}")
        
        # 确保目录存在
        if not os.path.exists(video_dir):
            os.makedirs(video_dir)
            os.makedirs(os.path.join(video_dir, 'thumbnails'), exist_ok=True)
            logger.info("创建视频目录和缩略图目录")
            
        videos = []
        # 支持的视频格式和编码
        format_info = {
            '.mp4': {
                'name': 'MP4 (H.264)',
                'priority': 1,  # 优先级最高
                'ios_support': True
            },
            '.m4v': {
                'name': 'M4V (H.264)',
                'priority': 2,
                'ios_support': True
            },
            '.webm': {
                'name': 'WebM (VP8)',
                'priority': 3,
                'ios_support': False
            },
            '.ogg': {
                'name': 'Ogg (Theora)',
                'priority': 4,
                'ios_support': False
            }
        }
        
        # 遍历视频目录
        logger.info("开始扫描视频文件...")
        file_list = [f for f in os.listdir(video_dir) if os.path.isfile(os.path.join(video_dir, f))]
        logger.info(f"发现 {len(file_list)} 个文件")
        
        for filename in file_list:
            file_path = os.path.join(video_dir, filename)
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            
            if ext in format_info:
                try:
                    logger.info(f"处理视频文件: {filename}")
                    
                    # 获取视频信息
                    if MOVIEPY_AVAILABLE:
                        clip = VideoFileClip(file_path)
                        duration = int(clip.duration)
                        clip.close()
                        # 格式化时长
                        minutes = duration // 60
                        seconds = duration % 60
                        duration_str = f"{minutes}:{seconds:02d}"
                    else:
                        # moviepy 不可用时使用默认值
                        logger.warning("moviepy 未安装，无法获取视频时长，使用默认值")
                        duration_str = "0:00"
                    
                    # 获取文件修改时间
                    mod_time = os.path.getmtime(file_path)
                    date = datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M')
                    
                    # 提取标题（移除扩展名和日期等）
                    title = re.sub(r'[\d-_]+', ' ', filename.rsplit('.', 1)[0]).strip()
                    if not title:
                        title = filename.rsplit('.', 1)[0]
                    
                    # 检查缩略图
                    thumbnail_name = f"{filename.rsplit('.', 1)[0]}.jpg"
                    thumbnail_path = os.path.join(video_dir, 'thumbnails', thumbnail_name)
                    if not os.path.exists(thumbnail_path):
                        logger.info(f"缩略图不存在: {thumbnail_name}")
                        thumbnail_path = '/static/video-placeholder.jpg'
                    else:
                        thumbnail_path = f'/replays/thumbnails/{thumbnail_name}'
                    
                    video_info = {
                        'url': f'/replays/{filename}',
                        'title': title,
                        'date': date,
                        'duration': duration_str,
                        'thumbnail': thumbnail_path,
                        'size': os.path.getsize(file_path) // (1024 * 1024),  # 文件大小（MB）
                        'type': format_info[ext]['name'],
                        'ios_support': format_info[ext]['ios_support'],
                        'priority': format_info[ext]['priority']
                    }
                    logger.info(f"添加视频: {video_info}")
                    videos.append(video_info)
                    
                except Exception as e:
                    logger.error(f"处理视频文件出错 {filename}: {str(e)}", exc_info=True)
                    continue
        
        # 按优先级和日期排序
        videos.sort(key=lambda x: (x['priority'], x['date']), reverse=True)
        logger.info(f"总共找到 {len(videos)} 个有效视频文件")
        
        # 检查是否为iOS设备
        user_agent = request.headers.get('User-Agent', '').lower()
        is_ios = 'iphone' in user_agent or 'ipad' in user_agent or 'ipod' in user_agent
        
        return jsonify({
            'success': True,
            'videos': videos,
            'is_ios': is_ios,
            'format_support': {
                'mp4': True,  # MP4在所有平台都支持
                'webm': not is_ios,
                'ogg': not is_ios
            }
        })
        
    except Exception as e:
        logger.error(f"获取视频列表失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@main.route('/validate_account_level', methods=['POST'])
@with_db_connection
def validate_account_level(conn=None):
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        
        if not phone:
            return jsonify({"success": False, "message": "请输入手机号码"}), 400
            
        if not re.match(r'^1[3-9]\d{9}$', phone):
            return jsonify({"success": False, "message": "请输入有效的手机号码"}), 400
            
        # 验证账户是否存在并获取账户等级
        cursor = conn.cursor()
        cursor.execute("SELECT card_level FROM accounts WHERE phone = ?", (phone,))
        account = cursor.fetchone()
        
        if not account:
            return jsonify({"success": False, "message": "该手机号未注册，请先联系管理员添加账户"}), 400
            
        # 定义等级的中文名称
        level_names = {
            'platinum': '铂金卡',
            'black': '黑金卡',
            'supreme': '至尊卡'
        }
        
        return jsonify({
            "success": True,
            "card_level": account['card_level'],
            "card_level_name": level_names[account['card_level']]
        })
        
    except Exception as e:
        print(f"验证账户等级时发生错误: {str(e)}")
        return jsonify({"success": False, "message": "验证账户失败，请重试"}), 500

@main.route('/admin_get_activation')
@with_db_connection
def admin_get_activation(conn=None):
    try:
        # 获取记录ID
        record_id = request.args.get('id')
        if not record_id:
            return jsonify({'success': False, 'message': '请提供记录ID'}), 400
            
        cursor = conn.cursor()
        
        # 查询激活登记记录
        cursor.execute("""
            SELECT id, phone, name, id_number, card_number, card_type, 
                   id_front_photo, id_back_photo, submit_time
            FROM card_activations 
            WHERE id = ?
        """, (record_id,))
        
        activation = cursor.fetchone()
        if not activation:
            return jsonify({'success': False, 'message': '未找到激活登记记录'}), 404
            
        # 转换为字典
        result = dict(activation)
        
        return jsonify({
            'success': True,
            'activation': result
        })
        
    except Exception as e:
        print(f"获取激活登记记录失败: {str(e)}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'获取记录失败：{str(e)}'}), 500

@main.route('/admin_get_address')
@with_db_connection
def admin_get_address(conn=None):
    try:
        # 获取记录ID
        record_id = request.args.get('id')
        if not record_id:
            return jsonify({'success': False, 'message': '请提供记录ID'}), 400
            
        cursor = conn.cursor()
        
        # 查询地址登记记录
        cursor.execute("""
            SELECT id, phone, name, id_number, delivery_phone, delivery_address,
                   card_type, shipping_status, shipping_time, id_front_photo, 
                   id_back_photo, submit_time
            FROM address_records 
            WHERE id = ?
        """, (record_id,))
        
        address = cursor.fetchone()
        if not address:
            return jsonify({'success': False, 'message': '未找到地址登记记录'}), 404
            
        # 转换为字典
        result = dict(address)
        
        return jsonify({
            'success': True,
            'address': result
        })
        
    except Exception as e:
        print(f"获取地址登记记录失败: {str(e)}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'获取记录失败：{str(e)}'}), 500

@main.route('/admin_get_card')
@with_db_connection
def admin_get_card(conn=None):
    try:
        card_number = request.args.get('number')
        if not card_number:
            return jsonify({'success': False, 'message': '请提供卡号'}), 400
            
        cursor = conn.cursor()
        
        # 查询金融卡信息
        cursor.execute("""
            SELECT card_number, create_time, status
            FROM financial_cards
            WHERE card_number = ?
        """, (card_number,))
        
        card = cursor.fetchone()
        if not card:
            return jsonify({'success': False, 'message': '未找到该金融卡'}), 404
            
        return jsonify({
            'success': True,
            'card': dict(card)
        })
        
    except Exception as e:
        print(f"获取金融卡信息失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500

@main.route('/admin_update_card', methods=['POST'])
@with_db_connection
def admin_update_card(conn=None):
    try:
        data = request.get_json()
        if not data or 'card_number' not in data or 'status' not in data:
            return jsonify({'success': False, 'message': '请提供完整的卡片信息'}), 400
            
        card_number = data['card_number'].strip()
        status = data['status'].strip()
        
        # 验证状态值
        valid_statuses = ['available', 'used', 'locked']
        if status not in valid_statuses:
            return jsonify({'success': False, 'message': '无效的状态值'}), 400
            
        cursor = conn.cursor()
        
        # 检查卡号是否存在
        cursor.execute("SELECT 1 FROM financial_cards WHERE card_number = ?", (card_number,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': '该卡号不存在'}), 404
            
        # 更新金融卡状态
        cursor.execute("""
            UPDATE financial_cards 
            SET status = ?
            WHERE card_number = ?
        """, (status, card_number))
        
        conn.commit()
        return jsonify({'success': True, 'message': '金融卡更新成功'})
        
    except Exception as e:
        print(f"更新金融卡失败: {str(e)}")
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@main.route('/admin_delete_record', methods=['POST'])
@with_db_connection
def admin_delete_record(conn=None):
    try:
        data = request.get_json()
        if not data or 'type' not in data or 'id' not in data:
            return jsonify({'success': False, 'message': '请求数据无效'}), 400
            
        record_type = data['type']
        record_id = data['id']
        
        cursor = conn.cursor()
        
        if record_type == 'activation':
            # 检查记录是否存在
            cursor.execute("SELECT 1 FROM card_activations WHERE id = ?", (record_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': '找不到该激活登记记录'}), 404
                
            # 删除激活登记记录
            cursor.execute("DELETE FROM card_activations WHERE id = ?", (record_id,))
            
        elif record_type == 'address':
            # 检查记录是否存在
            cursor.execute("SELECT 1 FROM address_records WHERE id = ?", (record_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': '找不到该地址登记记录'}), 404
                
            # 删除地址登记记录
            cursor.execute("DELETE FROM address_records WHERE id = ?", (record_id,))
            
        else:
            return jsonify({'success': False, 'message': '无效的记录类型'}), 400
            
        # 提交事务
        conn.commit()
        
        return jsonify({
            'success': True, 
            'message': f'{record_type}记录删除成功'
        })
        
    except Exception as e:
        print(f"删除记录失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'}), 500

@main.route('/admin_search_shipping')
@with_db_connection
def admin_search_shipping(conn=None):
    try:
        phone = request.args.get('phone', '').strip()
        
        if not phone:
            return jsonify({'success': False, 'message': '请提供手机号码'}), 400
            
        # 验证手机号格式
        if not re.match(r'^1[3-9]\d{9}$', phone):
            return jsonify({'success': False, 'message': '请输入有效的手机号码'}), 400
            
        cursor = conn.cursor()
        
        # 先检查 tracking_number 列是否存在
        cursor.execute("PRAGMA table_info(address_records)")
        columns = [row['name'] if isinstance(row, dict) else row[1] for row in cursor.fetchall()]
        has_tracking_number = 'tracking_number' in columns
        
        # 根据列是否存在构建查询
        if has_tracking_number:
            cursor.execute("""
                SELECT ar.id, ar.phone, ar.name as receiver_name, ar.delivery_address as address, 
                       ar.card_type as card_level, ar.shipping_status as status, 
                       ar.tracking_number, ar.submit_time
                FROM address_records ar
                WHERE ar.phone = ?
            """, (phone,))
        else:
            cursor.execute("""
                SELECT ar.id, ar.phone, ar.name as receiver_name, ar.delivery_address as address, 
                       ar.card_type as card_level, ar.shipping_status as status, 
                       NULL as tracking_number, ar.submit_time
                FROM address_records ar
                WHERE ar.phone = ?
            """, (phone,))
        
        rows = cursor.fetchall()
        
        # 安全地转换为字典
        records = []
        for row in rows:
            if isinstance(row, dict):
                records.append(row)
            else:
                # 如果不是字典，手动构建字典
                record = {
                    'id': row[0] if len(row) > 0 else None,
                    'phone': row[1] if len(row) > 1 else '',
                    'receiver_name': row[2] if len(row) > 2 else '',
                    'address': row[3] if len(row) > 3 else '',
                    'card_level': row[4] if len(row) > 4 else '',
                    'status': row[5] if len(row) > 5 else '',
                    'tracking_number': row[6] if len(row) > 6 else None,
                    'submit_time': row[7] if len(row) > 7 else ''
                }
                records.append(record)
        
        return jsonify({
            'success': True,
            'records': records
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"查询发货信息失败: {str(e)}")
        logger.error(f"错误详情: {error_trace}")
        print(f"查询发货信息失败: {str(e)}")
        print(f"错误详情: {error_trace}")
        return jsonify({'success': False, 'message': f'查询失败：{str(e)}'}), 500

@main.route('/admin_get_shipping')
@with_db_connection
def admin_get_shipping(conn=None):
    try:
        phone = request.args.get('phone', '').strip()
        
        if not phone:
            return jsonify({'success': False, 'message': '请提供手机号码'}), 400
            
        # 验证手机号格式
        if not re.match(r'^1[3-9]\d{9}$', phone):
            return jsonify({'success': False, 'message': '请输入有效的手机号码'}), 400
            
        cursor = conn.cursor()
        
        # 查询地址记录
        cursor.execute("""
            SELECT ar.id, ar.phone, ar.name as receiver_name, ar.delivery_address as address,
                   ar.card_type, ar.shipping_status as status, ar.submit_time
            FROM address_records ar
            WHERE ar.phone = ?
        """, (phone,))
        
        record = cursor.fetchone()
        if not record:
            return jsonify({'success': False, 'message': '未找到该手机号码的发货记录'}), 404
            
        # 构建返回的发货信息
        shipping_info = dict(record)
        
        return jsonify({
            'success': True,
            'shipping': shipping_info
        })
        
    except Exception as e:
        print(f"获取发货信息失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500

@main.route('/admin_update_tracking', methods=['POST'])
@with_db_connection
def admin_update_tracking(conn=None):
    try:
        data = request.get_json()
        if not data or 'phone' not in data or 'tracking_number' not in data:
            return jsonify({'success': False, 'message': '请求数据无效'}), 400
            
        phone = data['phone'].strip()
        tracking_number = data['tracking_number'].strip()
        
        # 验证手机号格式
        if not re.match(r'^1[3-9]\d{9}$', phone):
            return jsonify({'success': False, 'message': '请输入有效的手机号码'}), 400
            
        cursor = conn.cursor()
        
        # 检查记录是否存在
        cursor.execute("SELECT 1 FROM address_records WHERE phone = ?", (phone,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': '未找到该手机号码的发货记录'}), 404
            
        # 如果快递单号不为空，则同时更新发货状态为"已发货"
        if tracking_number:
            shipping_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                UPDATE address_records 
                SET tracking_number = ?, shipping_status = 'shipped', shipping_time = ?
                WHERE phone = ?
            """, (tracking_number, shipping_time, phone))
        else:
            # 如果快递单号为空，仅更新快递单号
            cursor.execute("""
                UPDATE address_records 
                SET tracking_number = ?
                WHERE phone = ?
            """, (tracking_number, phone))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': '快递单号更新成功'
        })
        
    except Exception as e:
        print(f"更新快递单号失败: {str(e)}")
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@main.route('/admin_update_shipping', methods=['POST'])
@with_db_connection
def admin_update_shipping(conn=None):
    try:
        data = request.get_json()
        if not data or 'phone' not in data or 'status' not in data:
            return jsonify({'success': False, 'message': '请求数据无效'}), 400
            
        phone = data['phone'].strip()
        status = data['status'].strip()
        
        # 验证手机号格式
        if not re.match(r'^1[3-9]\d{9}$', phone):
            return jsonify({'success': False, 'message': '请输入有效的手机号码'}), 400
            
        # 验证状态值
        valid_statuses = ['pending', 'shipped', 'cancelled']
        if status not in valid_statuses:
            return jsonify({'success': False, 'message': '无效的状态值'}), 400
            
        cursor = conn.cursor()
        
        # 检查记录是否存在
        cursor.execute("SELECT 1 FROM address_records WHERE phone = ?", (phone,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': '未找到该手机号码的发货记录'}), 404
            
        # 更新发货状态
        if status == 'shipped':
            shipping_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                UPDATE address_records 
                SET shipping_status = ?, shipping_time = ?
                WHERE phone = ?
            """, (status, shipping_time, phone))
        else:
            cursor.execute("""
                UPDATE address_records 
                SET shipping_status = ?, shipping_time = NULL
                WHERE phone = ?
            """, (status, phone))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': '发货信息更新成功'
        })
        
    except Exception as e:
        print(f"更新发货信息失败: {str(e)}")
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@main.route('/admin_update_account', methods=['POST'])
@with_db_connection
def admin_update_account(conn=None):
    try:
        data = request.get_json()
        if not data or 'phone' not in data or 'card_level' not in data:
            return jsonify({'success': False, 'message': '请提供手机号码和金融卡等级'}), 400
            
        phone = data['phone'].strip()
        card_level = data['card_level'].strip().lower()
        
        # 验证手机号格式
        if not re.match(r'^1[3-9]\d{9}$', phone):
            return jsonify({'success': False, 'message': '请输入有效的手机号码'}), 400
            
        # 验证金融卡等级
        valid_levels = {'platinum', 'black', 'supreme'}
        if card_level not in valid_levels:
            return jsonify({'success': False, 'message': '无效的金融卡等级'}), 400
            
        cursor = conn.cursor()
        
        # 检查账户是否存在
        cursor.execute("SELECT 1 FROM accounts WHERE phone = ?", (phone,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': '账户不存在'}), 404
            
        # 更新账户金融卡等级
        cursor.execute("""
            UPDATE accounts 
            SET card_level = ?
            WHERE phone = ?
        """, (card_level, phone))
        
        conn.commit()
        return jsonify({'success': True, 'message': '账户更新成功'})
        
    except Exception as e:
        print(f"更新账户失败: {str(e)}")
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@main.route('/api/admin/accounts/search')
@with_db_connection
def admin_search_accounts(conn=None):
    """搜索账户API"""
    try:
        # 获取搜索参数
        phone = request.args.get('phone', '')
        level = request.args.get('level', 'all')
        status = request.args.get('status', 'all')
        
        # 构建SQL查询
        sql = """
            SELECT a.phone, a.card_level, a.create_time,
                   CASE WHEN c.phone IS NOT NULL THEN 1 ELSE 0 END as is_activated
            FROM accounts a
            LEFT JOIN card_activations c ON a.phone = c.phone
            WHERE 1=1
        """
        params = []
        
        # 添加搜索条件
        if phone:
            sql += " AND a.phone LIKE ?"
            params.append(f"%{phone}%")
        
        if level != 'all':
            sql += " AND a.card_level = ?"
            params.append(level)
        
        if status != 'all':
            if status == 'activated':
                sql += " AND c.phone IS NOT NULL"
            elif status == 'not_activated':
                sql += " AND c.phone IS NULL"
                
        # 添加排序
        sql += " ORDER BY a.create_time DESC"
        
        # 打印SQL查询和参数以便调试
        print(f"执行搜索查询: {sql}")
        print(f"参数: {params}")
        
        # 执行查询
        cursor = conn.cursor()
        cursor.execute(sql, params)
        results = cursor.fetchall()
        
        print(f"查询结果数量: {len(results)}")
        if results:
            print(f"第一行结果: {results[0]}")
            print(f"列数: {len(results[0])}")
        
        # 格式化结果
        accounts = []
        for row in results:
            try:
                # 检查row是否为字典
                if isinstance(row, dict):
                    # 如果是字典，直接使用键值访问
                    account = {
                        'phone': row.get('phone', ''),
                        'card_level': row.get('card_level', ''),
                        'is_activated': bool(row.get('is_activated', 0)),
                        'registration_time': row.get('create_time', ''),
                        'last_updated': row.get('create_time', '')
                    }
                else:
                    # 如果是元组，按索引访问（旧的方式）
                    account = {
                        'phone': row[0],
                        'card_level': row[1],
                        'registration_time': row[2],
                        'last_updated': row[2],
                        'is_activated': bool(row[3]) if len(row) > 3 else False
                    }
                accounts.append(account)
            except Exception as row_e:
                print(f"处理行数据错误: {str(row_e)}, 行数据: {row}")
        
        return jsonify({
            'success': True,
            'accounts': accounts
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"搜索账户失败: {str(e)}")
        print(f"错误详情: {error_trace}")
        return jsonify({
            'success': False,
            'message': f'搜索账户失败: {str(e)}'
        })

@main.route('/api/admin/accounts/search_new')
@with_db_connection
def admin_search_accounts_new(conn=None):
    """新的搜索账户API"""
    try:
        # 获取搜索参数
        phone = request.args.get('phone', '')
        level = request.args.get('level', 'all')
        status = request.args.get('status', 'all')
        
        # 设置返回行为字典格式
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 构建SQL查询
        sql = """
            SELECT a.phone, a.card_level, a.create_time,
                   CASE WHEN c.phone IS NOT NULL THEN 1 ELSE 0 END as is_activated
            FROM accounts a
            LEFT JOIN card_activations c ON a.phone = c.phone
            WHERE 1=1
        """
        params = []
        
        # 添加搜索条件
        if phone:
            sql += " AND a.phone LIKE ?"
            params.append(f"%{phone}%")
        
        if level != 'all':
            sql += " AND a.card_level = ?"
            params.append(level)
        
        if status != 'all':
            if status == 'activated':
                sql += " AND c.phone IS NOT NULL"
            elif status == 'not_activated':
                sql += " AND c.phone IS NULL"
                
        # 添加排序
        sql += " ORDER BY a.create_time DESC"
        
        # 打印SQL查询和参数以便调试
        print(f"执行新搜索查询: {sql}")
        print(f"参数: {params}")
        
        # 执行查询
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        print(f"查询结果数量: {len(rows)}")
        
        # 格式化结果
        accounts = []
        for row in rows:
            accounts.append({
                'phone': row['phone'],
                'card_level': row['card_level'],
                'registration_time': row['create_time'],
                'last_updated': row['create_time'],
                'is_activated': bool(row['is_activated'])
            })
        
        print(f"格式化后的账户数量: {len(accounts)}")
        
        return jsonify({
            'success': True,
            'accounts': accounts
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"新搜索账户失败: {str(e)}")
        print(f"错误详情: {error_trace}")
        return jsonify({
            'success': False,
            'message': f'搜索账户失败: {str(e)}'
        })

# ... 其他主要路由 ... 