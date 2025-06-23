# Google Cloud Platform 商用デプロイガイド

## 📋 概要

PDF処理とPayPal決済システムをGoogle Cloud Platformで商用WEBアプリとして販売するためのデプロイガイドです。

## 🚀 デプロイオプション

### 1. Cloud Run（推奨）✨
- **料金**: 使用量ベース（月額$0〜）
- **特徴**: サーバーレス、自動スケーリング
- **適用**: 中小〜大規模トラフィック

### 2. App Engine
- **料金**: 固定料金 + トラフィック
- **特徴**: フルマネージド
- **適用**: 安定したトラフィック

## 📦 事前準備

### 1. Google Cloud アカウント
```bash
# Google Cloud CLIのインストール
# https://cloud.google.com/sdk/docs/install

# ログイン
gcloud auth login

# プロジェクト作成
gcloud projects create your-project-id
gcloud config set project your-project-id
```

### 2. 必要なAPI有効化
```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

### 3. 環境変数設定
`.env.production`ファイルを作成し、以下を設定：

```env
# セキュリティ
SECRET_KEY=your-strong-secret-key
ADMIN_USERNAME=your-admin-username
ADMIN_PASSWORD=your-secure-password

# PayPal設定
PAYPAL_MODE=live  # 本番: live, テスト: sandbox
PAYPAL_CLIENT_ID=your-paypal-client-id
PAYPAL_CLIENT_SECRET=your-paypal-client-secret
```

## 🛠️ デプロイ手順

### 自動セットアップ（推奨）
```bash
# Windowsの場合
setup_gcp_production.bat

# Linux/macOSの場合
chmod +x deploy.sh
./deploy.sh cloud-run
```

### 手動デプロイ

#### Cloud Run
```bash
# ビルドとデプロイ
gcloud run deploy pdf-paypal-system \
  --source . \
  --region asia-northeast1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2
```

#### App Engine
```bash
# デプロイ
gcloud app deploy app.yaml
```

## 💰 料金体系例

### Cloud Run
- **0-100万リクエスト/月**: 無料
- **CPU使用量**: $0.00024/vCPU秒
- **メモリ使用量**: $0.0000025/GB秒
- **予想月額**: $10-50（中規模利用時）

### App Engine
- **基本料金**: $0.05/インスタンス時間
- **予想月額**: $50-200（24時間稼働時）

## 🔒 セキュリティ設定

### 1. SSL証明書（自動）
```bash
# カスタムドメイン追加
gcloud run domain-mappings create \
  --service pdf-paypal-system \
  --domain your-domain.com \
  --region asia-northeast1
```

### 2. IAM設定
```bash
# サービスアカウント作成
gcloud iam service-accounts create pdf-paypal-sa

# 最小権限の付与
gcloud projects add-iam-policy-binding your-project-id \
  --member serviceAccount:pdf-paypal-sa@your-project-id.iam.gserviceaccount.com \
  --role roles/storage.objectViewer
```

### 3. 環境変数の暗号化
```bash
# Secret Managerを使用
gcloud secrets create paypal-client-secret --data-file=-
echo "your-secret" | gcloud secrets versions add paypal-client-secret --data-file=-
```

## 📊 モニタリング設定

### 1. Cloud Monitoring
```bash
# アラートポリシー作成
gcloud alpha monitoring policies create \
  --policy-from-file=monitoring-policy.yaml
```

### 2. Cloud Logging
```bash
# ログ基準のアラート
gcloud logging sinks create error-sink \
  storage.googleapis.com/your-bucket \
  --log-filter='severity >= ERROR'
```

## 🔧 カスタムドメイン設定

### 1. ドメイン検証
```bash
# ドメイン所有権の確認
gcloud domains verify your-domain.com
```

### 2. DNS設定
```
# A record
your-domain.com → Cloud Run IPアドレス

# CNAME record  
www.your-domain.com → ghs.googlehosted.com
```

## 📈 スケーリング設定

### Cloud Run
```yaml
# cloudbuild.yaml
- name: 'gcr.io/cloud-builders/gcloud'
  args: [
    'run', 'deploy', 'pdf-paypal-system',
    '--min-instances', '1',
    '--max-instances', '100',
    '--concurrency', '1000'
  ]
```

### App Engine
```yaml
# app.yaml
automatic_scaling:
  min_instances: 1
  max_instances: 20
  target_cpu_utilization: 0.6
```

## 💸 コスト最適化

### 1. リソース制限
```bash
# CPU・メモリ制限設定
gcloud run services update pdf-paypal-system \
  --cpu 1 \
  --memory 1Gi \
  --region asia-northeast1
```

### 2. 課金アラート
```bash
# 予算アラート設定
gcloud billing budgets create \
  --billing-account YOUR_BILLING_ACCOUNT \
  --display-name "PDF PayPal Budget" \
  --budget-amount 100USD
```

## 🔍 トラブルシューティング

### よくある問題

#### 1. デプロイエラー
```bash
# ログ確認
gcloud run services logs read pdf-paypal-system --region asia-northeast1

# ビルドログ確認  
gcloud builds log BUILD_ID
```

#### 2. 環境変数エラー
```bash
# 環境変数確認
gcloud run services describe pdf-paypal-system --region asia-northeast1
```

#### 3. 権限エラー
```bash
# IAM確認
gcloud projects get-iam-policy your-project-id
```

## 📞 サポート

### 技術サポート
- Google Cloud サポート: [https://cloud.google.com/support](https://cloud.google.com/support)
- PayPal 開発者サポート: [https://developer.paypal.com/support](https://developer.paypal.com/support)

### リソース
- [Cloud Run ドキュメント](https://cloud.google.com/run/docs)
- [App Engine ドキュメント](https://cloud.google.com/appengine/docs)
- [Cloud Build ドキュメント](https://cloud.google.com/build/docs)

## 📝 商用ライセンス

本システムを商用利用する場合は、以下を確認してください：

1. **PayPal商用アカウント**: 必須
2. **使用ライブラリのライセンス**: 各ライブラリの商用利用条件
3. **Google Cloudの利用規約**: 商用利用条件

---

## 🎯 次のステップ

1. ✅ デプロイ完了
2. 🔐 セキュリティ設定
3. 🌐 カスタムドメイン
4. 📊 モニタリング設定
5. 💰 課金アラート設定
6. 🚀 本格運用開始

**おめでとうございます！🎉 商用WEBアプリの準備が整いました！**
