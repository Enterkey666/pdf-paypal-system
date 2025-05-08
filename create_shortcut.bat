@echo off
chcp 65001 > nul
REM PDF処理 & PayPal決済リンク発行システム ショートカット作成スクリプト
setlocal enabledelayedexpansion

echo PDF処理 & PayPal決済リンク発行システム のショートカットを作成しています...
echo.

REM カレントディレクトリのパスを取得
set CURRENT_DIR=%~dp0
set CURRENT_DIR=%CURRENT_DIR:~0,-1%

REM ショートカットのパスを設定
set SHORTCUT_PATH=%USERPROFILE%\Desktop\PDF処理システム.lnk
set APP_PATH=%CURRENT_DIR%\start_app.bat
set ICON_PATH=%CURRENT_DIR%\static\favicon.ico

REM VBScriptを使用してショートカットを作成
echo Set oWS = WScript.CreateObject("WScript.Shell") > "%TEMP%\CreateShortcut.vbs"
echo sLinkFile = "%SHORTCUT_PATH%" >> "%TEMP%\CreateShortcut.vbs"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%TEMP%\CreateShortcut.vbs"
echo oLink.TargetPath = "%APP_PATH%" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.WorkingDirectory = "%CURRENT_DIR%" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.Description = "PDF処理 & PayPal決済リンク発行システム" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.IconLocation = "%ICON_PATH%" >> "%TEMP%\CreateShortcut.vbs"
echo oLink.Save >> "%TEMP%\CreateShortcut.vbs"

REM VBScriptを実行してショートカットを作成
cscript /nologo "%TEMP%\CreateShortcut.vbs"
del "%TEMP%\CreateShortcut.vbs"

if exist "%SHORTCUT_PATH%" (
    echo ショートカットの作成に成功しました。
    echo デスクトップに「PDF処理システム」アイコンが作成されました。
) else (
    echo ショートカットの作成に失敗しました。
)

echo.
echo ショートカットをクリックすることでアプリケーションを起動できます。
echo.
pause
