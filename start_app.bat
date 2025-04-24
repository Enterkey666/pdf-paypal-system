@echo off
REM PDF処理 & PayPal決済リンク発行システム起動スクリプト

echo PDF処理 & PayPal決済リンク発行システムを起動しています...

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

REM アプリケーションを起動
echo アプリケーションを起動しています...
start "" http://localhost:5000
python app.py

exit /b 0
