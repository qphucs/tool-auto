@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Lan dau chay: dang tao moi truong Python va cai thu vien...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt || goto :error
)
start "" ".venv\Scripts\pythonw.exe" -m app
exit /b 0

:error
echo Cai dat that bai. Kiem tra Python 3.12 da duoc cai chua.
pause
exit /b 1
