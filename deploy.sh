#!/bin/bash

# Google Cloud Platform デプロイスクリプト
# 使用法: ./deploy.sh [cloud-run|app-engine]

set -e

# カラー出力の設定
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ログ関数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# デプロイタイプを決定
DEPLOY_TYPE=${1:-cloud-run}

log_info "Google Cloud Platform デプロイスクリプト"
log_info "デプロイタイプ: $DEPLOY_TYPE"

# 必要なファイルの確認
if [[ ! -f "app.py" ]]; then
    log_error "app.pyが見つかりません"
    exit 1
fi

if [[ ! -f "requirements.txt" ]]; then
    log_error "requirements.txtが見つかりません"
    exit 1
fi

# Google Cloud CLIがインストールされているか確認
if ! command -v gcloud &> /dev/null; then
    log_error "Google Cloud CLIがインストールされていません"
    log_info "インストール方法: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Google Cloud プロジェクトIDを取得
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [[ -z "$PROJECT_ID" ]]; then
    log_error "Google Cloudプロジェクトが設定されていません"
    log_info "設定方法: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

log_info "使用プロジェクト: $PROJECT_ID"

# 環境変数の確認
ENV_FILE=".env"
if [[ -f "$ENV_FILE" ]]; then
    log_info "環境変数ファイル (.env) が見つかりました"
    
    # 必要な環境変数をチェック
    REQUIRED_VARS=("PAYPAL_CLIENT_ID" "PAYPAL_CLIENT_SECRET" "SECRET_KEY" "ADMIN_USERNAME" "ADMIN_PASSWORD")
    
    for var in "${REQUIRED_VARS[@]}"; do
        if ! grep -q "^$var=" "$ENV_FILE"; then
            log_warning "$var が .env ファイルに設定されていません"
        fi
    done
else
    log_warning ".envファイルが見つかりません。本番環境では必須です。"
fi

# デプロイタイプに応じた処理
case $DEPLOY_TYPE in
    "cloud-run")
        log_info "Cloud Runにデプロイします..."
        
        # 必要なAPIを有効化
        log_info "必要なAPIを有効化しています..."
        gcloud services enable run.googleapis.com
        gcloud services enable cloudbuild.googleapis.com
        gcloud services enable containerregistry.googleapis.com
        
        # Cloud Buildでビルド・デプロイ
        if [[ -f "cloudbuild.yaml" ]]; then
            log_info "Cloud Buildを使用してデプロイします..."
            gcloud builds submit --config cloudbuild.yaml
        else
            log_info "直接Cloud Runにデプロイします..."
            
            # Dockerfileの確認
            if [[ ! -f "Dockerfile" ]]; then
                log_error "Dockerfileが見つかりません"
                exit 1
            fi
            
            # ビルドとデプロイを実行
            gcloud run deploy pdf-paypal-system \
                --source . \
                --region asia-northeast1 \
                --platform managed \
                --allow-unauthenticated \
                --port 8080 \
                --memory 2Gi \
                --cpu 2 \
                --timeout 300 \
                --max-instances 100 \
                --set-env-vars "FLASK_DEBUG=false,USE_TEMP_DIR=true,GOOGLE_CLOUD=true"
        fi
        
        # デプロイ結果を取得
        SERVICE_URL=$(gcloud run services describe pdf-paypal-system --region=asia-northeast1 --format="value(status.url)")
        log_success "Cloud Runデプロイ完了!"
        log_success "サービスURL: $SERVICE_URL"
        ;;
        
    "app-engine")
        log_info "App Engineにデプロイします..."
        
        # 必要なAPIを有効化
        log_info "App Engine APIを有効化しています..."
        gcloud services enable appengine.googleapis.com
        
        # App Engineアプリを初期化（必要な場合）
        if ! gcloud app describe &>/dev/null; then
            log_info "App Engineアプリを初期化します..."
            gcloud app create --region=asia-northeast1
        fi
        
        # app.yamlの確認
        if [[ ! -f "app.yaml" ]]; then
            log_error "app.yamlが見つかりません"
            exit 1
        fi
        
        # デプロイ実行
        log_info "App Engineにデプロイしています..."
        gcloud app deploy app.yaml --quiet
        
        # デプロイ結果を取得
        SERVICE_URL=$(gcloud app browse --no-launch-browser 2>&1 | grep -o 'https://[^[:space:]]*')
        log_success "App Engineデプロイ完了!"
        log_success "サービスURL: $SERVICE_URL"
        ;;
        
    *)
        log_error "無効なデプロイタイプ: $DEPLOY_TYPE"
        log_info "使用法: ./deploy.sh [cloud-run|app-engine]"
        exit 1
        ;;
esac

# セキュリティ確認
log_info "セキュリティチェック..."
log_warning "デプロイ後に以下を確認してください:"
echo "  - SSL証明書の設定"
echo "  - 環境変数の設定"
echo "  - セキュリティポリシー"
echo "  - アクセス制御"

log_success "デプロイプロセス完了!"
