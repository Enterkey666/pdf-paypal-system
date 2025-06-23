@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: Google Cloud Platform 商用デプロイ セットアップスクリプト

echo ===================================================
echo Google Cloud Platform 商用デプロイ セットアップ
echo ===================================================
echo.

:: カラー設定
set "GREEN=[32m"
set "YELLOW=[33m"
set "RED=[31m"
set "BLUE=[34m"
set "RESET=[0m"

:: ステップ1: Google Cloud CLIの確認
echo %BLUE%[1/7] Google Cloud CLIの確認%RESET%
where gcloud >nul 2>&1
if errorlevel 1 (
    echo %RED%エラー: Google Cloud CLIがインストールされていません%RESET%
    echo.
    echo Google Cloud CLIをインストールしてください:
    echo https://cloud.google.com/sdk/docs/install
    echo.
    pause
    exit /b 1
)
echo %GREEN%✓ Google Cloud CLIが見つかりました%RESET%
echo.

:: ステップ2: ログイン確認
echo %BLUE%[2/7] Google Cloudへのログイン確認%RESET%
gcloud auth list --filter=status:ACTIVE --format="value(account)" >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%Google Cloudにログインしていません。ログインを開始します...%RESET%
    gcloud auth login
    if errorlevel 1 (
        echo %RED%ログインに失敗しました%RESET%
        pause
        exit /b 1
    )
)
echo %GREEN%✓ Google Cloudにログインしています%RESET%
echo.

:: ステップ3: プロジェクトIDの設定
echo %BLUE%[3/7] Google Cloudプロジェクトの設定%RESET%
for /f "delims=" %%i in ('gcloud config get-value project 2^>nul') do set PROJECT_ID=%%i

if "!PROJECT_ID!"=="" (
    echo プロジェクトが設定されていません。
    echo.
    echo 利用可能なプロジェクト:
    gcloud projects list
    echo.
    set /p PROJECT_ID="使用するプロジェクトIDを入力してください: "
    
    gcloud config set project !PROJECT_ID!
    if errorlevel 1 (
        echo %RED%プロジェクトの設定に失敗しました%RESET%
        pause
        exit /b 1
    )
)

echo %GREEN%✓ プロジェクト: !PROJECT_ID!%RESET%
echo.

:: ステップ4: 必要なAPIの有効化
echo %BLUE%[4/7] 必要なAPIの有効化%RESET%
echo Cloud Run API を有効化中...
gcloud services enable run.googleapis.com --quiet

echo Cloud Build API を有効化中...
gcloud services enable cloudbuild.googleapis.com --quiet

echo Container Registry API を有効化中...
gcloud services enable containerregistry.googleapis.com --quiet

echo App Engine Admin API を有効化中...
gcloud services enable appengine.googleapis.com --quiet

echo %GREEN%✓ 必要なAPIが有効化されました%RESET%
echo.

:: ステップ5: 環境変数の設定
echo %BLUE%[5/7] 環境変数の設定%RESET%

if not exist ".env.production" (
    echo %YELLOW%.env.productionファイルが見つかりません%RESET%
    echo テンプレートファイルをコピーしています...
    
    if exist ".env.sample" (
        copy ".env.sample" ".env.production" >nul
    ) else (
        echo 警告: .env.sampleも見つかりません。手動で.env.productionを設定してください。
    )
)

echo.
echo %YELLOW%重要: 以下の環境変数を必ず設定してください：%RESET%
echo   - SECRET_KEY (強力なランダムキー)
echo   - ADMIN_USERNAME
echo   - ADMIN_PASSWORD  
echo   - PAYPAL_CLIENT_ID
echo   - PAYPAL_CLIENT_SECRET
echo   - PAYPAL_MODE (live または sandbox)
echo.

set /p SETUP_ENV="環境変数を今すぐ設定しますか？ (y/n): "
if /i "!SETUP_ENV!"=="y" (
    notepad ".env.production"
    echo 設定が完了したらEnterキーを押してください...
    pause >nul
)

:: ステップ6: デプロイ方法の選択
echo %BLUE%[6/7] デプロイ方法の選択%RESET%
echo.
echo 1. Cloud Run (推奨) - サーバーレス、自動スケーリング
echo 2. App Engine - フルマネージド、固定料金
echo.
set /p DEPLOY_CHOICE="デプロイ方法を選択してください (1 または 2): "

if "!DEPLOY_CHOICE!"=="1" (
    set DEPLOY_TYPE=cloud-run
    echo %GREEN%Cloud Runを選択しました%RESET%
) else if "!DEPLOY_CHOICE!"=="2" (
    set DEPLOY_TYPE=app-engine
    echo %GREEN%App Engineを選択しました%RESET%
) else (
    echo %RED%無効な選択です。Cloud Runを使用します。%RESET%
    set DEPLOY_TYPE=cloud-run
)
echo.

:: ステップ7: デプロイの実行
echo %BLUE%[7/7] デプロイの実行%RESET%
echo.
echo デプロイタイプ: !DEPLOY_TYPE!
echo プロジェクト: !PROJECT_ID!
echo.

set /p CONFIRM_DEPLOY="デプロイを実行しますか？ (y/n): "
if /i "!CONFIRM_DEPLOY!"=="y" (
    echo.
    echo %YELLOW%デプロイを開始します...%RESET%
    
    if "!DEPLOY_TYPE!"=="cloud-run" (
        echo Cloud Runにデプロイ中...
        bash deploy.sh cloud-run
    ) else (
        echo App Engineにデプロイ中...
        bash deploy.sh app-engine
    )
    
    if errorlevel 1 (
        echo %RED%デプロイに失敗しました%RESET%
        echo ログを確認してください。
        pause
        exit /b 1
    )
    
    echo.
    echo %GREEN%✓ デプロイが完了しました！%RESET%
    echo.
    echo %YELLOW%次のステップ:%RESET%
    echo 1. SSL証明書の設定
    echo 2. カスタムドメインの設定
    echo 3. セキュリティポリシーの確認
    echo 4. 料金アラートの設定
    echo 5. モニタリングの設定
    echo.
) else (
    echo デプロイをキャンセルしました。
)

echo.
echo %GREEN%セットアップが完了しました！%RESET%
echo.
pause
