@echo off
pushd "%~dp0"
echo ====================================
echo   School Management - Starting...
echo ====================================
echo.
echo Please wait, the application is starting...
set "PY="
python -V >nul 2>nul && set "PY=python"
if not defined PY ( py -3 -V >nul 2>nul && set "PY=py -3" )
if not defined PY (
    echo Python 3.10+ was not found.
    popd
    pause
    exit /b 1
)
%PY% app.py
echo.
echo ====================================
echo   Application is running...
echo   Close this window to stop the program.
echo ====================================
popd
pause
