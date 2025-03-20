@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: 基础配置 - 按需修改 ↓
set "APP_NAME=DouYin Live Recorder"
set "PORT=5000"              :: 需确保和 Flask 应用的监听端口一致
set "APP_DIR=%~dp0"
:: 基础配置 - 按需修改 ↑ 

:: 固定配置
set "VENV_PATH=%APP_DIR%venv"
set "PID_FILE=%APP_DIR%main.pid"
set "LOG_FILE=%APP_DIR%main.log"
set "PYTHONIOENCODING=utf8"
set "PYTHONUTF8=1"

:: 切换到应用目录
cd /d "%APP_DIR%" || (
    echo Cannot change to application directory: %APP_DIR%
    exit /b 1
)

goto :parse_command

:: 状态检查
:stat
@echo off >nul 2>&1
@REM for /f  %%a in ('wmic process where "commandline like '%%main.py%%' and name like '%%python%%'" get processid /format:csv 2^>nul ^| findstr /r "[0-9]"') do (
@REM     echo Found running instance with PID: %%a
@REM     exit /b 0
@REM ) >nul 2>&1
(for /f "tokens=2 delims=," %%a in ('wmic process where "commandline like '%%main.py%%' and name like '%%python%%'" get processid /format:csv 2^>nul') do (
    echo Found running instance with PID: %%a
    echo %%a | findstr /r "^[0-9][0-9]*$" >nul && (
        echo Found running instance with PID: %%a
        exit /b 0
    )
)) >nul 2>&1
echo %APP_NAME% is not running
exit /b 1

:: 启动服务
:start
if exist "%PID_FILE%" del "%PID_FILE%"

:: 验证虚拟环境
if not exist "%VENV_PATH%\Scripts\python.exe" (
    echo Virtual environment not found in venv
    echo Suggested fix: python -m venv venv
    exit /b 1
)

echo Starting %APP_NAME%...
start /b cmd /c "set PYTHONIOENCODING=utf8 && "%VENV_PATH%\Scripts\python.exe" main.py > "%LOG_FILE%" 2>&1"

timeout /t 2 /nobreak >nul

:: 获取进程 PID
for /f "tokens=2 delims=," %%a in ('wmic process where "commandline like '%%main.py%%' and name like '%%python%%'" get processid /format:csv ^| findstr /r "[0-9]"') do (
    echo %%a > "%PID_FILE%"
    echo %APP_NAME% started successfully with PID: %%a
    echo Log file: %LOG_FILE%
    exit /b 0
)

echo %APP_NAME% failed to start. Please check log file
type "%LOG_FILE%"
exit /b 1

:: 停止服务
:stop

:: 然后停止进程
for /f %%a in ('wmic process where "commandline like '%%Mozilla%%' and name like '%%ffmpeg.exe%%'" get processid ^| findstr /r "[0-9]"') do (
    echo Attempting graceful shutdown of PID: %%a
    :: 发送 CTRL+C 信号
    taskkill /PID %%a >nul 2>&1
    
    :: 等待进程自行退出
    timeout /t 10 /nobreak >nul
    :: 检查进程是否还在运行
    tasklist /FI "PID eq %%a" 2>nul | find "%%a" >nul
    if not errorlevel 1 (
        echo Graceful shutdown failed, forcing termination of PID: %%a
        taskkill /F /PID %%a >nul 2>&1
    ) else (
        echo Process terminated gracefully
    )
)
for /f %%a in ('wmic process where "commandline like '%%main.py%%' and name like '%%python%%'" get processid ^| findstr /r "[0-9]"') do (
    echo Attempting graceful shutdown of PID: %%a
    :: 发送 CTRL+C 信号
    taskkill /PID %%a >nul 2>&1
    
    :: 等待进程自行退出
    timeout /t 10 /nobreak >nul
    :: 检查进程是否还在运行
    tasklist /FI "PID eq %%a" 2>nul | find "%%a" >nul
    if not errorlevel 1 (
        echo Graceful shutdown failed, forcing termination of PID: %%a
        taskkill /F /PID %%a >nul 2>&1
    ) else (
        echo Process terminated gracefully
    )
)

if exist "%PID_FILE%" del "%PID_FILE%"
exit /b 0

:: 重启服务
:restart
call :stop
timeout /t 2 /nobreak >nul
goto :start

:: 查看日志
:logs
if exist "%LOG_FILE%" (
    type "%LOG_FILE%"
) else (
    echo Log file does not exist
)
exit /b 0

:: 命令解析
:parse_command
if "%~1"=="" (
    echo Usage: %~n0 {start^|stop^|restart^|stat^|logs}
    exit /b 1
)
if /i "%~1"=="start" goto :start
if /i "%~1"=="stop" goto :stop
if /i "%~1"=="status" goto :stat
if /i "%~1"=="restart" goto :restart
if /i "%~1"=="logs" goto :logs
echo Invalid command: %~1
echo Usage: %~n0 {start^|stop^|restart^|stat^|logs}
exit /b 1