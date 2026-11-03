@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONPATH=%~dp0src"

echo ============================================
echo  AI Listing Pipeline - Offline Demo
echo  (mock model, no API key required)
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Install Python 3.10+ and try again.
    goto end
)

python -c "import yaml, openpyxl, requests" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing dependencies ...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install failed.
        goto end
    )
)

python -m ai_listing.cli run --input data\sample_products.csv --provider mock
if errorlevel 1 (
    echo.
    echo [FAILED] See the error above.
    goto end
)

echo.
echo [DONE] Outputs are in the "out" folder:
echo        out\listings.xlsx        result table
echo        out\listing_export.csv   upload-ready CSV
echo        out\report.md            run report

:end
echo.
pause
