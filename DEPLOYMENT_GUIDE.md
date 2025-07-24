# 🚀 PDF-PayPal-Stripe システム デプロイ・運用ガイド

## 📋 概要

このドキュメントは、PDF-PayPal-Stripeシステムのデプロイメントと運用管理について詳細に説明します。

## 🏗️ システム構成

```
PDF-PayPal-Stripe System
├── Web Application (Flask)
├── Database (PostgreSQL)
├── Cache (Redis)
├── Monitoring (Prometheus + Grafana)
├── File Storage (Local/Cloud)
└── Payment APIs (Stripe + PayPal)
```

## 🛠️ デプロイ前準備

### 1. 必要なソフトウェア

```bash
# 必須ソフトウェア
- Docker Engine 20.10+
- Docker Compose 2.0+
- Git
- Curl

# オプション
- Python 3.9+
- PostgreSQL Client
- Redis CLI
```

### 2. システム要件

#### 最小要件
- **CPU**: 2コア
- **メモリ**: 4GB RAM
- **ストレージ**: 20GB SSD
- **ネットワーク**: 100Mbps

#### 推奨要件
- **CPU**: 4コア
- **メモリ**: 8GB RAM
- **ストレージ**: 50GB SSD
- **ネットワーク**: 1Gbps

### 3. 環境変数設定

```bash
# .env.example をコピーして設定
cp .env.example .env

# 必須設定項目を編集
nano .env
```

#### 重要な設定項目

```bash
# 🔐 セキュリティ設定
SECRET_KEY=your-32-character-secret-key-here
ENCRYPTION_KEY=your-32-character-encryption-key-here

# 💳 Stripe設定
STRIPE_MODE=test  # 本番では live に変更
STRIPE_SECRET_KEY_TEST=sk_test_your_key
STRIPE_PUBLISHABLE_KEY_TEST=pk_test_your_key

# 💰 PayPal設定
PAYPAL_MODE=sandbox  # 本番では live に変更
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret

# 🗃️ データベース設定
POSTGRES_PASSWORD=strong_password_here
```

## 🚀 デプロイ手順

### 1. 自動デプロイ（推奨）

```bash
# デプロイスクリプトの実行権限を付与
chmod +x deploy.sh

# 開発環境デプロイ
./deploy.sh development

# ステージング環境デプロイ
./deploy.sh staging --backup

# 本番環境デプロイ
./deploy.sh production --backup --force
```

### 2. 手動デプロイ

```bash
# 1. リポジトリのクローン
git clone https://github.com/your-repo/pdf-paypal-system.git
cd pdf-paypal-system

# 2. 環境設定
cp .env.example .env
# .env ファイルを編集

# 3. Dockerイメージのビルド
docker-compose build

# 4. サービスの起動
docker-compose up -d

# 5. ヘルスチェック
curl http://localhost:8080/health
```

### 3. クラウドデプロイ

#### AWS EC2

```bash
# 1. EC2インスタンス作成
aws ec2 run-instances \
  --image-id ami-0abcdef1234567890 \
  --count 1 \
  --instance-type t3.medium \
  --key-name your-key-pair \
  --security-group-ids sg-903004f8

# 2. セキュリティグループ設定
aws ec2 authorize-security-group-ingress \
  --group-id sg-903004f8 \
  --protocol tcp \
  --port 8080 \
  --cidr 0.0.0.0/0
```

#### Google Cloud Run

```bash
# Cloud Build設定でデプロイ
gcloud builds submit --config cloudbuild.yaml

# 直接デプロイ
gcloud run deploy pdf-paypal-system \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated
```

## 📊 監視とログ

### 1. アクセス先

```bash
# アプリケーション
http://localhost:8080

# Grafana ダッシュボード
http://localhost:3000
Username: admin
Password: [GRAFANA_PASSWORD from .env]

# Prometheus メトリクス
http://localhost:9090
```

### 2. 監視項目

#### システムメトリクス
- CPU使用率
- メモリ使用量
- ディスク使用量
- ネットワークトラフィック

#### アプリケーションメトリクス
- レスポンス時間
- リクエスト数
- エラー率
- アクティブユーザー数

#### 決済APIメトリクス
- Stripe API呼び出し回数
- PayPal API呼び出し回数
- 決済成功率
- API応答時間

### 3. アラート設定

```yaml
# Prometheusアラートルール例
groups:
  - name: pdf-paypal-alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "高いエラー率を検出"
```

## 💾 バックアップ管理

### 1. 自動バックアップ

```bash
# バックアップマネージャーの設定
python backup_manager.py schedule

# 手動バックアップ実行
python backup_manager.py backup

# バックアップ一覧確認
python backup_manager.py list
```

### 2. バックアップ内容

- **データベース**: PostgreSQLダンプ
- **設定ファイル**: .env, config.json
- **アップロードファイル**: uploads/ディレクトリ
- **ログファイル**: logs/ディレクトリ

### 3. 復元手順

```bash
# データベース復元
python backup_manager.py restore --file backups/database/db_backup_20240115_120000.sql

# ファイル復元
tar -xzf backups/files/files_backup_20240115_120000.tar.gz
```

## 🔧 運用手順

### 1. 日常運用

#### 毎日の確認事項
- [ ] システム稼働状況確認
- [ ] エラーログ確認
- [ ] ディスク使用量確認
- [ ] バックアップ完了確認

#### 週次の確認事項
- [ ] パフォーマンスメトリクス確認
- [ ] セキュリティログ確認
- [ ] 古いバックアップ削除
- [ ] システム更新確認

#### 月次の確認事項
- [ ] 決済レポート作成
- [ ] システムリソース見直し
- [ ] セキュリティ監査
- [ ] 災害復旧テスト

### 2. APIキー更新手順

#### Stripe APIキー更新

```bash
# 1. 新しいAPIキーを.envに設定
nano .env

# 2. アプリケーション再起動
docker-compose restart app

# 3. 動作確認
curl -X POST http://localhost:8080/api/stripe/test
```

#### PayPal APIキー更新

```bash
# 1. PayPal Developer Consoleで新しいキーを取得
# 2. .envファイルを更新
nano .env

# 3. アプリケーション再起動
docker-compose restart app

# 4. 動作確認
curl -X POST http://localhost:8080/api/paypal/test
```

### 3. スケールアップ手順

#### 水平スケール（複数インスタンス）

```yaml
# docker-compose.yml
services:
  app:
    scale: 3  # 3つのインスタンスを起動
    
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

#### 垂直スケール（リソース増強）

```yaml
# docker-compose.yml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

## 🚨 トラブルシューティング

### 1. よくある問題と解決方法

#### アプリケーションが起動しない

```bash
# 1. ログ確認
docker-compose logs app

# 2. 設定ファイル確認
cat .env | grep -E "SECRET_KEY|STRIPE|PAYPAL"

# 3. データベース接続確認
docker-compose exec postgres psql -U pdf_user -d pdf_paypal_db -c "SELECT 1;"
```

#### 決済処理エラー

```bash
# 1. Stripe接続テスト
curl -X POST http://localhost:8080/api/stripe/config/validate

# 2. PayPal接続テスト
curl -X POST http://localhost:8080/api/paypal/config/validate

# 3. APIキー確認
echo $STRIPE_SECRET_KEY_TEST | head -c 20
```

#### パフォーマンス問題

```bash
# 1. リソース使用量確認
docker stats

# 2. スロークエリ確認
docker-compose exec postgres psql -U pdf_user -d pdf_paypal_db -c "
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC LIMIT 10;"

# 3. Redisメモリ使用量確認
docker-compose exec redis redis-cli info memory
```

### 2. 緊急時対応手順

#### サービス停止

```bash
# 1. 緊急停止
docker-compose down

# 2. データベースバックアップ
docker-compose exec postgres pg_dump -U pdf_user pdf_paypal_db > emergency_backup.sql

# 3. ログ保存
cp -r logs/ emergency_logs_$(date +%Y%m%d_%H%M%S)/
```

#### 災害復旧

```bash
# 1. 新環境での復旧
git clone https://github.com/your-repo/pdf-paypal-system.git
cd pdf-paypal-system

# 2. バックアップから設定復元
cp /backup/.env .env

# 3. データベース復元
docker-compose up -d postgres
docker-compose exec postgres psql -U pdf_user -d pdf_paypal_db < emergency_backup.sql

# 4. 全サービス起動
docker-compose up -d

# 5. 動作確認
./deploy.sh staging --no-tests
```

## 🔐 セキュリティ対策

### 1. 定期セキュリティチェック

```bash
# 1. 依存関係脆弱性チェック
pip install safety
safety check -r requirements.txt

# 2. Dockerイメージ脆弱性チェック
docker scan pdf-paypal-stripe_app

# 3. SSL証明書確認
openssl s_client -connect your-domain.com:443 -servername your-domain.com
```

### 2. セキュリティ設定

#### HTTPS強制化

```nginx
# nginx.conf
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    
    location / {
        proxy_pass http://app:8080;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

#### ファイアウォール設定

```bash
# UFW設定例
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 5432/tcp  # PostgreSQLは外部アクセス禁止
```

## 📈 パフォーマンス最適化

### 1. データベース最適化

```sql
-- インデックス追加
CREATE INDEX idx_payments_created_at ON payments(created_at);
CREATE INDEX idx_users_email ON users(email);

-- VACUUM実行
VACUUM ANALYZE;

-- 統計情報更新
ANALYZE;
```

### 2. アプリケーション最適化

```python
# Redisキャッシュ設定
CACHE_CONFIG = {
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_URL': 'redis://redis:6379/0',
    'CACHE_DEFAULT_TIMEOUT': 300
}

# データベース接続プール
DATABASE_CONFIG = {
    'pool_size': 20,
    'max_overflow': 30,
    'pool_timeout': 60,
    'pool_recycle': 3600
}
```

### 3. 監視ダッシュボード

```json
{
  "dashboard": {
    "title": "PDF-PayPal-Stripe System",
    "panels": [
      {
        "title": "Response Time",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(http_requests_total{status=~\"5..\"}[5m]) / rate(http_requests_total[5m])"
          }
        ]
      }
    ]
  }
}
```

## 📞 サポート・連絡先

### 技術サポート
- **ドキュメント**: 本ガイド + README.md
- **ログファイル**: logs/app.log, logs/error.log
- **監視ダッシュボード**: http://localhost:3000

### 緊急時連絡先
- **システム管理者**: [ADMIN_EMAIL]
- **エラー通知**: [ERROR_NOTIFICATION_EMAIL]
- **Slack通知**: [SLACK_WEBHOOK_URL]

---

*このガイドは定期的に更新されます。最新版は常にGitリポジトリから確認してください。*
