@echo off
cd /d "C:\Users\proxx\OneDrive\Desktop\Programas\Agente_OPE"
call .venv\Scripts\activate.bat
python -m uvicorn app.main:app --host 0.0.0.0 --port 8100
pause