# Firebase + Cloud Functions 移行ガイド

## 概要
PDF PayPal SystemをFirebase + Cloud Functionsアーキテクチャに移行するためのガイドです。

## アーキテクチャ変更点

### 従来のシステム
- **Web Server**: Flask + Gunicorn
- **Database**: SQLite
- **Storage**: ローカルファイルシステム
- **Hosting**: Google Cloud Run

### 新システム
- **Web Server**: Cloud Functions (Python)
- **Database**: Cloud Firestore
- **Storage**: Cloud Storage
- **Hosting**: Firebase Hosting

## コスト最適化

### 無料枠内での運用
- **Firebase Hosting**: 10GB転送/月（無料）
- **Cloud Functions**: 200万回呼び出し/月（無料）
- **Firestore**: 1GB保存、50,000回読み取り/日（無料）
- **Cloud Storage**: $0.20/月（10GB）

## 必要なファイル

### 1. Firebase設定ファイル
- `firebase.json` - Firebase プロジェクト設定
- `firestore.rules` - Firestore セキュリティルール
- `firestore.indexes.json` - Firestore インデックス設定
- `storage.rules` - Cloud Storage セキュリティルール

### 2. Cloud Functions
- `functions/main.py` - メイン処理
- `functions/requirements.txt` - Python依存関係
- `functions/firestore_adapter.py` - Firestore操作アダプター
- `functions/storage_adapter.py` - Cloud Storage操作アダプター

### 3. フロントエンド
- `public/index.html` - Firebase Hosting用のWebページ

## セットアップ手順

### 1. Firebase プロジェクト作成
```bash
# Firebase CLI インストール
npm install -g firebase-tools

# Firebase ログイン
firebase login

# プロジェクト初期化
firebase init
```

### 2. 環境変数設定
```bash
# Cloud Functions用環境変数
firebase functions:config:set \
  paypal.mode="sandbox" \
  paypal.client_id="YOUR_PAYPAL_CLIENT_ID" \
  paypal.client_secret="YOUR_PAYPAL_CLIENT_SECRET" \
  stripe.secret_key="YOUR_STRIPE_SECRET_KEY" \
  stripe.publishable_key="YOUR_STRIPE_PUBLISHABLE_KEY" \
  app.default_currency="JPY"
```

### 3. デプロイ
```bash
# 全体デプロイ
firebase deploy

# Functions のみ
firebase deploy --only functions

# Hosting のみ
firebase deploy --only hosting
```

## データ移行

### SQLite → Firestore
```python
# 既存のデータをFirestoreに移行するスクリプト例
import sqlite3
from firebase_admin import credentials, firestore, initialize_app

# Firebase初期化
cred = credentials.Certificate('path/to/serviceAccountKey.json')
initialize_app(cred)
db = firestore.client()

# SQLiteからデータ読み込み
conn = sqlite3.connect('data/pdf_paypal.db')
cursor = conn.cursor()

# ユーザーデータ移行
cursor.execute("SELECT * FROM users")
users = cursor.fetchall()
for user in users:
    user_doc = {
        'username': user[1],
        'email': user[2],
        'password_hash': user[3],
        'created_at': user[4],
        # 他のフィールド...
    }
    db.collection('users').add(user_doc)

conn.close()
```

### ファイル移行
```python
# ローカルファイルをCloud Storageに移行
from google.cloud import storage
import os

client = storage.Client()
bucket = client.bucket('your-bucket-name')

# uploadsフォルダの移行
for root, dirs, files in os.walk('uploads'):
    for file in files:
        local_path = os.path.join(root, file)
        blob_path = local_path.replace('\\', '/')
        
        blob = bucket.blob(blob_path)
        blob.upload_from_filename(local_path)
        print(f"Uploaded: {local_path} -> {blob_path}")
```

## API エンドポイント

### Cloud Functions エンドポイント
- `POST /api/create-payment-link` - 決済リンク作成
- `POST /api/pdf-process` - PDF処理
- `POST /webhook/stripe` - Stripe Webhook
- `POST /webhook/paypal` - PayPal Webhook
- `GET /health` - ヘルスチェック

### 認証
Firebase Authenticationを使用した認証システム：
```javascript
// フロントエンドでの認証
firebase.auth().onAuthStateChanged((user) => {
    if (user) {
        // ログイン済み
    } else {
        // 未ログイン
    }
});
```

## セキュリティ

### Firestore Rules
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // ユーザーデータは本人のみアクセス可能
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
    
    // 決済データは本人のみアクセス可能
    match /payments/{paymentId} {
      allow read, write: if request.auth != null && 
        resource.data.user_id == request.auth.uid;
    }
  }
}
```

### Cloud Storage Rules
```javascript
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    // ユーザーファイルは本人のみアクセス可能
    match /uploads/{userId}/{allPaths=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

## モニタリング

### Firebase Console
- **Functions**: 実行ログ、エラー監視
- **Firestore**: データベース使用量
- **Storage**: ストレージ使用量
- **Hosting**: アクセス統計

### ログ確認
```bash
# Cloud Functions ログ
firebase functions:log

# リアルタイムログ
firebase functions:log --follow
```

## トラブルシューティング

### よくある問題

1. **Functions のタイムアウト**
   ```python
   # タイムアウト時間を調整
   @functions_framework.http
   def my_function(request):
       # 処理...
   ```

2. **Firestore 権限エラー**
   - `firestore.rules` を確認
   - 認証状態を確認

3. **CORS エラー**
   ```python
   from flask_cors import CORS
   CORS(app)
   ```

### パフォーマンス最適化

1. **Firestore クエリ最適化**
   ```python
   # インデックスを使用したクエリ
   query = db.collection('payments')\
     .where('user_id', '==', user_id)\
     .order_by('created_at', direction=firestore.Query.DESCENDING)\
     .limit(10)
   ```

2. **Cloud Storage 最適化**
   ```python
   # 署名付きURLで一時的なアクセス
   blob = bucket.blob(file_path)
   url = blob.generate_signed_url(expiration=datetime.now() + timedelta(hours=1))
   ```

## 今後の拡張

### マルチテナント対応
- ユーザーごとの設定分離
- 組織レベルでの権限管理

### 自動スケーリング
- Cloud Functions の自動スケーリング活用
- Firestore の自動スケーリング

### 分析・レポート
- Firebase Analytics 導入
- BigQuery 連携でのデータ分析

## まとめ
Firebase + Cloud Functionsへの移行により、以下の利点が得られます：
- **コスト削減**: 無料枠での運用が可能
- **スケーラビリティ**: 自動スケーリング
- **メンテナンス軽減**: サーバーレス運用
- **セキュリティ向上**: Firebase の統合セキュリティ