@echo off
rem Mo giao dien tra cuu Lexo trong trinh duyet (chay tren may, khong can mang).
rem Can da tao moi truong .venv va cai thu vien (xem README, muc Cai dat).
rem Tim theo nghia va tach hanh vi can Ollama dang chay; khong co thi giao dien tu dung tim theo tu khoa.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co moi truong .venv. Mo README.md, muc Cai dat, de tao moi truong truoc.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run src\ui\app_tra_cuu.py --browser.gatherUsageStats false
if errorlevel 1 pause
