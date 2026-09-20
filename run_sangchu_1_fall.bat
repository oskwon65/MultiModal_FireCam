@echo off
cd /d D:\multi_modal
call C:\Users\KICT-SC\anaconda3\Scripts\activate.bat mfpcam
:loop
python -m openpifpaf.fall_detection sangchu_1
echo [%date% %time%] fall_detection sangchu_1 exited, restart in 10s...
timeout /t 10 /nobreak >nul
goto loop
