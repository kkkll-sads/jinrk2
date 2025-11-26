from flask import Blueprint, jsonify, request
from models.database import DatabasePool

api = Blueprint('api', __name__)

@api.route('/query')
def query():
    # ... API查询代码 ...
    pass

# ... 其他API路由 ... 