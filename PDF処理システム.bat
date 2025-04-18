@echo off
REM PDF処理 & PayPal決済リンク発行システム 直接起動スクリプト
REM このファイルは解凍後すぐに使えるようにルートディレクトリに配置されています

echo PDF処理 & PayPal決済リンク発行システムを起動しています...

REM カレントディレクトリを取得
set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%

REM Pythonが存在するか確認
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo エラー: Pythonが見つかりません。Pythonをインストールしてください。
    echo https://www.python.org/downloads/ からダウンロードできます。
    pause
    exit /b 1
)

REM 必要なライブラリがインストールされているか確認
echo 必要なライブラリを確認しています...
pip show flask >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo 必要なライブラリをインストールしています...
    pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo エラー: ライブラリのインストールに失敗しました。
        pause
        exit /b 1
    )
)

REM 初回起動時にデスクトップショートカットを作成
if not exist "%USERPROFILE%\Desktop\PDF処理システム.lnk" (
    echo デスクトップにショートカットを作成しています...
    call create_shortcut.bat
)

REM アプリケーションを起動
echo アプリケーションを起動しています...
start "" http://localhost:5000
python app.py

exit /b 0
