@echo off
set "FLASK_ENV=production"
set "SECRET_KEY=+Dm2%%3;|;9%%v"
set "HOST=127.0.0.1"
set "PORT=8080"

if not exist "logs" mkdir "logs"
if not exist "static\uploads" mkdir "static\uploads"
if not exist "temp" mkdir "temp"

echo Starting server at http://127.0.0.1:8080
echo Press Ctrl+C to stop

"C:\Users\1212\AppData\Local\Programs\Python\Python310\python.exe" "run.py"
pause 