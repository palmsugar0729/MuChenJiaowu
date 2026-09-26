@echo off
REM 构建独立 exe，输出到 dist/SalaryCounter.exe
python -m PyInstaller --onefile --windowed --name SalaryCounter main.py
echo.
echo Build complete. Output: dist\SalaryCounter.exe
pause
