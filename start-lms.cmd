@echo off
setlocal
cd /d "%~dp0"
echo Project: %CD%
echo Python environment should be classroom. MYSQL_PASSWORD must already be configured.
echo Stop any old LMS server on port 8000 before starting this project.
python manage.py check
if errorlevel 1 exit /b 1
python manage.py runserver 127.0.0.1:8000
