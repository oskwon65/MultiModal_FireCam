@echo off
cd /d D:\multi_modal
call C:\Users\KICT-SC\anaconda3\Scripts\activate.bat mfpcam
:loop
python source\server_to_db.py sangchu_1
echo [%date% %time%] server_to_db sangchu_1 exited, restart in 10s...
timeout /t 10 /nobreak >nul
goto loop
