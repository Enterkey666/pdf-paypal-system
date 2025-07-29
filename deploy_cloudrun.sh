#!/bin/bash

# Cloud Run デプロイスクリプト

echo "☁️ Google Cloud Run デプロイを開始します"
echo "======================================="

# Google Cloud SDK の確認
if ! command -v gcloud &> /dev/null; then
    echo "❌ Google Cloud SDK がインストールされていません"
    echo "インストール方法: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# プロジェクト設定
echo "📋 利用可能なGCPプロジェクト:"
gcloud projects list

read -p "使用するプロジェクトID: " PROJECT_ID
gcloud config set project $PROJECT_ID

# リージョン設定
echo ""
echo "デプロイリージョンを選択してください:"
echo "1) asia-northeast1 (東京)"
echo "2) asia-northeast2 (大阪)"
echo "3) us-central1 (アイオワ)"
echo "4) europe-west1 (ベルギー)"
read -p "選択 [1-4]: " region_choice

case $region_choice in
    1) REGION="asia-northeast1" ;;
    2) REGION="asia-northeast2" ;;
    3) REGION="us-central1" ;;
    4) REGION="europe-west1" ;;
    *) REGION="asia-northeast1" ;;
esac

# サービス名設定
SERVICE_NAME="pdf-paypal-system"
read -p "サービス名 (デフォルト: $SERVICE_NAME): " custom_service_name
if [ ! -z "$custom_service_name" ]; then
    SERVICE_NAME="$custom_service_name"
fi

# 必要なAPIを有効化
echo ""
echo "🔧 必要なAPIを有効化中..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com

# Container Registry の設定
echo "🐳 Container Registry を設定中..."
gcloud auth configure-docker

# 環境変数の設定
echo ""
echo "🔧 環境変数を設定してください:"

# config.jsonから読み込み（可能な場合）
if [ -f "config.json" ] && command -v jq &> /dev/null; then
    echo "📄 config.jsonから設定を読み込み..."
    PAYPAL_CLIENT_ID=$(jq -r '.paypal_client_id' config.json)
    PAYPAL_CLIENT_SECRET=$(jq -r '.paypal_client_secret' config.json)
    STRIPE_SECRET_KEY=$(jq -r '.stripe_secret_key_test' config.json)
    PAYPAL_MODE=$(jq -r '.paypal_mode' config.json)
    DEFAULT_CURRENCY=$(jq -r '.default_currency' config.json)
else
    # 手動入力
    read -p "PayPal Client ID: " PAYPAL_CLIENT_ID
    read -s -p "PayPal Client Secret (非表示): " PAYPAL_CLIENT_SECRET
    echo ""
    read -s -p "Stripe Secret Key (非表示): " STRIPE_SECRET_KEY
    echo ""
    PAYPAL_MODE="sandbox"
    DEFAULT_CURRENCY="JPY"
fi

# Cloud Build でビルド・デプロイ
echo ""
echo "🏗️ Cloud Build でビルド・デプロイ中..."
gcloud run deploy $SERVICE_NAME \
    --source . \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --set-env-vars "PAYPAL_CLIENT_ID=$PAYPAL_CLIENT_ID,PAYPAL_CLIENT_SECRET=$PAYPAL_CLIENT_SECRET,STRIPE_SECRET_KEY=$STRIPE_SECRET_KEY,PAYPAL_MODE=$PAYPAL_MODE,DEFAULT_CURRENCY=$DEFAULT_CURRENCY" \
    --memory 1Gi \
    --cpu 1 \
    --timeout 300 \
    --max-instances 10

echo ""
echo "✅ Cloud Run デプロイが完了しました！"
echo ""
echo "🌐 サービスURL:"
gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)'

echo ""
echo "📊 Cloud Console:"
echo "https://console.cloud.google.com/run/detail/$REGION/$SERVICE_NAME/metrics?project=$PROJECT_ID"

echo ""
echo "🔧 環境変数の追加/変更は以下のコマンドで行えます:"
echo "gcloud run services update $SERVICE_NAME --region $REGION --set-env-vars KEY=VALUE"