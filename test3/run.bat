@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo   AScript MCP 截图+搜索管线
echo ================================================
echo.
echo   用法:
echo     run.bat                        纯截图5张
echo     run.bat search 关键词           搜索+截图
echo     run.bat search 关键词 张数       搜索+截图(指定张数)
echo.

if "%1"=="" (
    conda run -n zscq python main.py
) else (
    conda run -n zscq python main.py %*
)
pause
