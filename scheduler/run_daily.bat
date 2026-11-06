@echo off
rem Daily run: last TARGET2 business day. Exit code: 0 validated, 1 with reservations, 2 not validated, 3 crash.
cd /d "%~dp0\.."
python -m riskreport.cli run --inbox data\inbox --runs runs >> runs\scheduler.log 2>&1
exit /b %ERRORLEVEL%
