@echo off
rem Mo giao dien Chuc nang 2 (phan tich vu an) cua Lexo trong trinh duyet (chay tren may, khong can mang).
rem Can da tao moi truong .venv va cai thu vien (xem README, muc Cai dat).
rem Soan ban cao buoc can Ollama dang chay va da co mo hinh qwen3:8b; khong co thi giao dien chi goi y cac Dieu lien quan.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co moi truong .venv. Mo README.md, muc Cai dat, de tao moi truong truoc.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run src\ui\app_vu_an.py --browser.gatherUsageStats false
if errorlevel 1 pause
