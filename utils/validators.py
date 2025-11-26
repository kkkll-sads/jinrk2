import re
from functools import wraps
from flask import request, jsonify

def validate_phone(phone):
    """验证手机号格式"""
    if not phone or not isinstance(phone, str):
        return False
    return bool(re.match(r'^1[3-9]\d{9}$', phone))

def validate_id_number(id_number):
    """验证身份证号格式"""
    if not id_number or not isinstance(id_number, str):
        return False
    return bool(re.match(r'^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dX]$', id_number))

def validate_card_number(card_number):
    """验证金融卡号格式"""
    if not card_number or not isinstance(card_number, str):
        return False
    return bool(re.match(r'^\d{16,19}$', card_number))

def validate_text_length(text, min_length=1, max_length=500):
    """验证文本长度"""
    if not text or not isinstance(text, str):
        return False
    text_length = len(text.strip())
    return min_length <= text_length <= max_length

def validate_image_file(file):
    """验证图片文件"""
    if not file:
        return False
    # 检查文件扩展名
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    filename = file.filename.lower()
    return '.' in filename and filename.rsplit('.', 1)[1] in allowed_extensions

# 验证装饰器
def validate_json_input(*required_fields):
    """验证JSON输入的装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': '无效的请求数据'}), 400
            
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return jsonify({
                    'success': False, 
                    'message': f'缺少必要字段：{", ".join(missing_fields)}'
                }), 400
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator 