@echo off
REM PDF処理 & PayPal決済リンク発行システム起動スクリプト

echo PDF処理 & PayPal決済リンク発行システムを起動しています...

REM Pythonが存在するか確認
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ======================================================
    echo エラー: Pythonがインストールされていません
    echo ======================================================
    echo.
    echo このアプリケーションを実行するには、Pythonのインストールが必要です。
    echo 以下の手順でインストールしてください：
    echo 1. https://www.python.org/downloads/ にアクセス
    echo 2. 「Download Python」ボタンをクリック
    echo 3. インストーラーを実行（「Add Python to PATH」にチェックを入れてください）
    echo 4. インストール完了後、このバッチファイルを再度実行してください
    echo.
    pause
    exit /b 1
)

REM requirements.txtの存在確認
if not exist requirements.txt (
    echo requirements.txtが見つかりません。必要なパッケージを個別にインストールします...
    pip install flask pdfplumber requests python-dotenv
) else (
    REM 必要なライブラリがインストールされているか確認
    echo 必要なライブラリを確認しています...
    pip show flask >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo 必要なライブラリをインストールしています...
        pip install -r requirements.txt
        if %ERRORLEVEL% neq 0 (
            echo requirements.txtからのインストールに失敗しました。必要なパッケージを個別にインストールします...
            pip install flask pdfplumber requests python-dotenv
            if %ERRORLEVEL% neq 0 (
                echo ======================================================
                echo エラー: ライブラリのインストールに失敗しました
                echo ======================================================
                echo.
                echo インターネット接続を確認し、再度お試しください。
                echo または管理者権限でコマンドプロンプトを開き、以下のコマンドを実行してください：
                echo pip install flask pdfplumber requests python-dotenv
                echo.
                pause
                exit /b 1
            )
        )
    )
)

REM アプリケーションを起動
echo アプリケーションを起動しています...
start "" http://localhost:5000
python app.py

exit /b 0
