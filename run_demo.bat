@echo off
REM Windows 一键演示（不需要联网、不需要 API Key）
setlocal
set PYTHONUTF8=1
set PYTHONPATH=%~dp0src

python -m ai_listing.cli run --input data\sample_products.csv --provider mock
if errorlevel 1 goto fail
echo.
echo [OK] 结果已生成到 out\ 目录
pause
exit /b 0

:fail
echo [FAIL] 运行出错，请检查是否已 pip install -e ".[dev]"
pause
exit /b 1
