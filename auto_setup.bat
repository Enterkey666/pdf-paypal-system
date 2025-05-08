@echo off
title PDF Processing System - Auto Setup

echo ===================================================
echo  PDF Processing System - Auto Setup
echo ===================================================
echo.

REM Check if running with admin rights
net session >nul 2>&1
set ADMIN_RIGHTS=%ERRORLEVEL%

REM Get current directory
set CURRENT_DIR=%~dp0
set CURRENT_DIR=%CURRENT_DIR:~0,-1%

REM Create popup window using VBScript
echo Creating setup wizard...
echo Set objShell = CreateObject("WScript.Shell") > "%TEMP%\popup.vbs"
echo result = MsgBox("Would you like to start the PDF Processing application now?", vbYesNo + vbQuestion, "PDF Processing System") >> "%TEMP%\popup.vbs"
echo If result = vbYes Then >> "%TEMP%\popup.vbs"
echo    objShell.Run "cmd /c cd /d ""%CURRENT_DIR%"" && call setup_wizard.bat", 1, False >> "%TEMP%\popup.vbs"
echo End If >> "%TEMP%\popup.vbs"

REM Run the popup
start /wait "" "%TEMP%\popup.vbs"
del "%TEMP%\popup.vbs" >nul 2>&1

exit /b 0
