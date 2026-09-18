@echo off
rem ---------------------------------------------------------------------
rem  blastlab - open the PySide6 (Qt) interface.
rem
rem  Since 2026-09-17 the Qt GUI is what "python -m blastlab" opens, so
rem  this launcher passes no GUI flag: it stays correct even if --qt is
rem  retired. The Tkinter GUI is still there as "blastlab.bat --tk",
rem  kept as the way back by owner decision (2026-09-18).
rem
rem  Safe to double-click from anywhere: it runs from its own folder, so
rem  Python finds the blastlab package whatever the current directory is.
rem  ASCII only on purpose - a .bat is read in the console codepage.
rem ---------------------------------------------------------------------

title blastlab
setlocal

rem Run from this script's own folder (%~dp0 keeps the trailing backslash,
rem and the quotes survive the spaces and the dash in the OneDrive path).
pushd "%~dp0" || (
    echo [blastlab] cannot enter "%~dp0"
    pause
    exit /b 1
)

rem A clear sentence beats a raw traceback. Three things can be missing.
where python >nul 2>&1 || (
    echo [blastlab] Python was not found on PATH.
    echo            Install Python 3.12 or newer, then run this again.
    goto :fail
)

if not exist "blastlab\__main__.py" (
    echo [blastlab] this launcher is not next to the blastlab package.
    echo            Expected "%CD%\blastlab\__main__.py".
    goto :fail
)

python -c "import PySide6" >nul 2>&1 || (
    echo [blastlab] PySide6 is missing, so the Qt interface cannot start.
    echo            Install it with:  python -m pip install -r requirements.txt
    echo            Or open the Tkinter interface with:  blastlab.bat --tk
    goto :fail
)

rem %* forwards everything, so "blastlab_qt.bat --case my.json" works.
python -m blastlab %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo [blastlab] exited with code %RC%.
    goto :fail
)
popd
endlocal
exit /b 0

:fail
rem Pause only on failure: a double-click would otherwise close the
rem window before the reason could be read.
echo.
pause
popd
endlocal
exit /b 1
