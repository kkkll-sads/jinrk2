#!/bin/bash

export FLASK_ENV=production
export SECRET_KEY="+Dm2%%3;|;9%%v"

# 创建必要目录
mkdir -p logs
mkdir -p static/uploads  
mkdir -p temp

echo "Starting server at http://localhost:5000"
echo "Press Ctrl+C to stop"

# 使用python3作为默认命令，如果不存在则使用python
PYTHON_CMD=python3
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD=python
fi

$PYTHON_CMD run.py 