# PDF PayPal System - Web Application Deployment Guide

## 概要

PDF PayPal System Web Applicationは、第三者が独自のGCP環境に簡単にデプロイできるように設計されたウェブアプリケーションです。PDFファイルから顧客情報と金額を自動抽出し、PayPal決済リンクを生成する機能を提供します。

## 特徴

- 🌐 **ウェブベースの設定インターフェース**: ブラウザから簡単にPayPal API設定が可能
- 🔒 **セキュアな設定管理**: 環境変数やローカル設定ファイルで認証情報を安全に管理
- 📱 **レスポンシブデザイン**: デスクトップ・モバイル両対応
- 🚀 **Google Cloud Platform対応**: App Engineでの簡単デプロイ
- 💳 **PayPal Sandbox/Live対応**: テスト環境と本番環境の切り替えが可能

## 前提条件

1. **Google Cloud Platform アカウント**
   - GCPアカウントとプロジェクトの作成
   - 課金の有効化（無料枠内でも利用可能）

2. **PayPal Developer アカウント**
   - PayPal Developerアカウントの作成
   - Sandbox/Live APIクレデンシャルの取得

3. **ローカル環境**
   - Google Cloud SDK のインストール
   - Python 3.9以上

## デプロイ手順

### 1. Google Cloud SDK のセットアップ

```bash
# Google Cloud SDK をインストール（まだの場合）
# https://cloud.google.com/sdk/docs/install からダウンロード

# gcloud の認証
gcloud auth login

# プロジェクトの設定
gcloud config set project YOUR_PROJECT_ID
```

### 2. アプリケーションのデプロイ

```bash
# デプロイスクリプトを実行
./deploy_webapp_gcp.sh
```

スクリプトが以下の処理を自動実行します：
- 必要なGoogle Cloud APIの有効化
- App Engineアプリケーションの作成（初回のみ）
- アプリケーションファイルのデプロイ
- デプロイ完了後のURLの表示

### 3. 初期設定

デプロイ完了後、ブラウザでアプリケーションURLにアクセスし：

1. **設定ページ** (`/settings`) にアクセス
2. **PayPal API設定** を入力
   - クライアントID
   - クライアントシークレット  
   - 動作モード（Sandbox/Live）
3. **接続テスト** を実行して設定を確認
4. **設定を保存**

### 4. アプリケーションの使用

1. ホームページでPDFファイルをアップロード
2. 自動的に顧客情報と金額が抽出される
3. PayPal決済リンクが生成される
4. 生成されたリンクをコピーして顧客に送信

## ファイル構成

```
pdf-paypal-system/
├── webapp.py                 # メインアプリケーション
├── webapp.yaml              # App Engine設定
├── requirements-webapp.txt  # Python依存関係
├── deploy_webapp_gcp.sh     # デプロイスクリプト
├── extractors.py           # PDF解析機能
└── templates/              # HTMLテンプレート
    ├── webapp_index.html
    ├── webapp_settings.html
    ├── webapp_result.html
    ├── webapp_payment_success.html
    └── webapp_payment_cancel.html
```

## PayPal API設定

### Sandbox（テスト環境）

1. [PayPal Developer Dashboard](https://developer.paypal.com/) にログイン
2. **Apps & Credentials** → **Sandbox** タブ
3. **Create App** でアプリケーション作成
4. **Client ID** と **Client Secret** をコピー

### Live（本番環境）

1. PayPal Developer Dashboard の **Live** タブ
2. 本番用アプリケーションを作成
3. PayPalの審査を通過後、本番クレデンシャルを取得

## セキュリティ考慮事項

- **API クレデンシャル**: 設定ファイルや環境変数で安全に管理
- **HTTPS**: App Engineは自動的にHTTPS化
- **ファイルアップロード**: PDFファイルのみ許可、一時保存後削除
- **設定アクセス**: 管理者パスワードでの保護（オプション）

## トラブルシューティング

### デプロイエラー

```bash
# gcloud の再認証
gcloud auth login

# プロジェクト設定の確認
gcloud config get-value project

# App Engine リージョンの確認
gcloud app describe
```

### PayPal API エラー

- クライアントIDとシークレットの確認
- Sandbox/Liveモードの設定確認
- PayPal Developer Dashboardでアプリの状態確認

### PDFファイル処理エラー

- ファイルサイズの確認（10MB以下推奨）
- PDFファイルの破損チェック
- 日本語テキストの抽出精度確認

## サポート・カスタマイズ

このウェブアプリケーションは、第三者が独自の要件に合わせてカスタマイズできるように設計されています。

### 主要なカスタマイズポイント

- **デザインテーマ**: CSSの変更でブランディング対応
- **通貨設定**: JPY以外の通貨サポート
- **PDF解析ロジック**: 特定の帳票フォーマットに対応
- **決済フロー**: PayPal以外の決済プロバイダー連携

## 料金体系

### Google Cloud Platform

- **App Engine**: 無料枠内で月間数万リクエストまで無料
- **Cloud Storage**: 初期設定では不使用
- **Cloud Build**: デプロイ時のみ使用

### PayPal

- **取引手数料**: PayPalの標準手数料が適用
- **API使用料**: 無料（取引手数料に含まれる）

## ライセンス

このアプリケーションは、第三者による商用利用・改変を許可しています。詳細はライセンスファイルを参照してください。

---

## 緊急サポート

デプロイや設定で問題が発生した場合は、Google Cloud Supportまたは開発元にお問い合わせください。