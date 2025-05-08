@echo off
title PDF Setup

echo ===================================================
echo  PDF Processing System Setup
echo ===================================================
echo.
echo This setup wizard will configure the application.
echo.

REM Create desktop shortcut
echo Do you want to create a desktop shortcut?
echo This will allow you to start the app directly from your desktop.
choice /C YN /M "Create desktop shortcut? (Y/N)"
if %ERRORLEVEL% equ 1 (
    echo Creating shortcut...
    
    REM Get current directory path
    set CURRENT_DIR=%~dp0
    set CURRENT_DIR=%CURRENT_DIR:~0,-1%
    
    REM Set shortcut paths
    set SHORTCUT_PATH=%USERPROFILE%\Desktop\PDF_System.lnk
    set APP_PATH=%CURRENT_DIR%\app.py
    set ICON_PATH=%CURRENT_DIR%\static\favicon.ico
    
    REM Create shortcut using VBScript
    echo Set oWS = WScript.CreateObject("WScript.Shell") > "%TEMP%\CreateShortcut.vbs"
    echo sLinkFile = "%SHORTCUT_PATH%" >> "%TEMP%\CreateShortcut.vbs"
    echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%TEMP%\CreateShortcut.vbs"
    echo oLink.TargetPath = "pythonw" >> "%TEMP%\CreateShortcut.vbs"
    echo oLink.Arguments = "%APP_PATH%" >> "%TEMP%\CreateShortcut.vbs"
    echo oLink.WorkingDirectory = "%CURRENT_DIR%" >> "%TEMP%\CreateShortcut.vbs"
    echo oLink.Description = "PDF Processing System" >> "%TEMP%\CreateShortcut.vbs"
    echo oLink.IconLocation = "%ICON_PATH%" >> "%TEMP%\CreateShortcut.vbs"
    echo oLink.Save >> "%TEMP%\CreateShortcut.vbs"
    
    REM Execute VBScript to create shortcut
    cscript /nologo "%TEMP%\CreateShortcut.vbs"
    del "%TEMP%\CreateShortcut.vbs"
    
    if exist "%SHORTCUT_PATH%" (
        echo Shortcut created successfully.
        echo "PDF_System" icon has been created on your desktop.
    ) else (
        echo Failed to create shortcut.
    )
    echo.
)

REM Check if user wants to start the application now
echo Do you want to start the application now?
choice /C YN /M "Start application now? (Y/N)"
if %ERRORLEVEL% equ 1 (
    echo Starting application...
    echo Browser will open automatically.
    echo.
    echo Note: To exit the application, close this command window or press Ctrl+C.
    echo.
    start "" http://localhost:5000
    python app.py
) else (
    echo.
    echo Setup completed.
    echo To start the application, click the desktop shortcut or
    echo run the command "python app.py" in this folder.
    echo.
    pause
)
