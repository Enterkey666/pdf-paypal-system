@echo off
chcp 65001 > nul

REM PDF PayPal System - ローカル起動スクリプト (Windows用)

echo 🚀 PDF PayPal System ローカル開発環境を起動します
echo ==================================================

REM 現在のディレクトリを確認
echo 📂 作業ディレクトリ: %CD%

REM Python仮想環境の確認・作成
if not exist "venv" (
    echo 🐍 Python仮想環境を作成中...
    python -m venv venv
)

REM 仮想環境をアクティベート
echo 📦 仮想環境をアクティベート中...
call venv\Scripts\activate.bat

REM 依存関係のインストール
echo 📚 依存関係をインストール中...
pip install -r requirements.txt

REM 設定ファイルの確認
if not exist "config.json" (
    echo ⚠️  config.json が見つかりません
    echo config.example.json をコピーして設定してください
    
    if exist "config.example.json" (
        copy config.example.json config.json > nul
        echo ✅ config.json を作成しました（config.example.jsonからコピー）
    )
)

REM ログディレクトリ作成
if not exist "logs" mkdir logs

REM オプション選択
echo.
echo 起動オプションを選択してください:
echo 1^) 従来版アプリ (app.py^)
echo 2^) ローカル開発版 (local_app.py^) - 推奨
echo 3^) Firebase Emulator
echo.
set /p choice="選択 [1-3]: "

if "%choice%"=="1" (
    echo 🌐 従来版アプリを起動中...
    echo URL: http://localhost:5000
    python app.py
) else if "%choice%"=="2" (
    echo 🛠️  ローカル開発版を起動中...
    echo URL: http://localhost:5000
    echo 設定確認: http://localhost:5000/config
    echo ヘルスチェック: http://localhost:5000/health
    python local_app.py
) else if "%choice%"=="3" (
    echo 🔥 Firebase Emulatorを起動中...
    
    REM Firebase CLIの確認
    firebase --version > nul 2>&1
    if errorlevel 1 (
        echo ❌ Firebase CLI がインストールされていません
        echo インストール方法:
        echo npm install -g firebase-tools
        pause
        exit /b 1
    )
    
    echo Firebase Emulator UI: http://localhost:4000
    echo Functions: http://localhost:5001
    echo Firestore: http://localhost:8080
    echo Storage: http://localhost:9199
    echo Hosting: http://localhost:5000
    
    firebase emulators:start
) else (
    echo ❌ 無効な選択です
    pause
    exit /b 1
)

pause