@echo off
REM PDF処理 & PayPal決済リンク発行システム自動起動スクリプト
title PDF処理 & PayPal決済リンク発行システム

echo ===================================================
echo  PDF処理 & PayPal決済リンク発行システム セットアップ
echo ===================================================
echo.

REM 管理者権限の確認
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo 警告: 管理者権限がありません。一部の機能が制限される可能性があります。
    echo 管理者として実行することをお勧めします。
    echo.
    choice /C YN /M "続行しますか？ (Y/N)"
    if %ERRORLEVEL% equ 2 exit /b 0
    echo.
)

REM Pythonが存在するか確認
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo エラー: Pythonが見つかりません。
    echo.
    echo Pythonをインストールする必要があります。
    echo インストーラーを開きますか？
    choice /C YN /M "Pythonインストーラーを開きますか？ (Y/N)"
    if %ERRORLEVEL% equ 1 (
        echo Pythonインストーラーを開いています...
        start https://www.python.org/downloads/
    )
    echo.
    echo Pythonをインストールした後、このスクリプトを再度実行してください。
    pause
    exit /b 1
)

REM Pythonのバージョンを確認
python --version | findstr /C:"Python 3" >nul
if %ERRORLEVEL% neq 0 (
    echo 警告: Python 3が必要です。
    echo 現在のバージョン:
    python --version
    echo.
    choice /C YN /M "続行しますか？ (Y/N)"
    if %ERRORLEVEL% equ 2 exit /b 0
    echo.
)

REM 必要なライブラリがインストールされているか確認
echo 必要なライブラリを確認しています...
pip show flask >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo 必要なライブラリをインストールしています...
    echo これには数分かかる場合があります。しばらくお待ちください...
    echo.
    pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo エラー: ライブラリのインストールに失敗しました。
        echo インターネット接続を確認し、再度試してください。
        pause
        exit /b 1
    )
    echo.
    echo ライブラリのインストールが完了しました！
)

REM デスクトップにショートカットを作成
echo デスクトップにショートカットを作成しますか？
choice /C YN /M "ショートカットを作成しますか？ (Y/N)"
if %ERRORLEVEL% equ 1 (
    echo ショートカットを作成しています...
    call create_shortcut.bat >nul 2>&1
    echo デスクトップにショートカットを作成しました。
    echo.
)

REM アプリケーションを起動
echo アプリケーションを起動しています...
echo ブラウザが自動的に開きます。
echo.
echo ※ アプリケーションを終了するには、このウィンドウを閉じるか、Ctrl+Cを押してください。
echo.
start "" http://localhost:5000
python app.py

exit /b 0
