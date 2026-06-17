@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo   AScript MCP 微信视频号采集管线
echo ================================================
echo.

echo   用法:
echo     run.bat                        默认运行（采集 2 个视频）
echo     set WEIXIN_MAX_VIDEOS=5 ^&^& run.bat   指定采集视频数量
echo     set WEIXIN_MAX_VIDEOS=0 ^&^& run.bat   全量采集（不限制，自动停止）
echo.

if "%1"=="" (
    conda run -n zscq python core/main.py
) else (
    conda run -n zscq python core/main.py %*
)
pause
