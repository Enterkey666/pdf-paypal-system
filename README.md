PDF一括処理 & PayPal決済リンク発行システム

概要

PDFファイルをアップロードして、請求金額と請求先情報を自動抽出し、PayPal決済用のリンクを自動生成するシステムです。複数のPDFファイルをバッチ処理することができます。ゲスト決済対応のPayPalリンクを生成し、請求業務を効率化します。

主な機能

PDFファイルのアップロード（ドラッグ＆ドロップ対応）
請求金額の自動抽出（自動抽出できない場合は手動入力可能）
請求先名の自動抽出（“〇〇様”の形式で表示）
PayPal決済リンクの自動生成（アカウント不要のゲスト決済対応）
複数ファイルの一括処理
PayPal APIの設定管理機能
設定のインポート/エクスポート機能
処理履歴の管理と表示

特徴

AI OCR機能: Google Cloud Vision API、Microsoft Azure Form Recognizer、Tesseract OCRの選択が可能
高精度な請求金額抽出: 様々な形式の請求書・領収書から金額を正確に抽出
顧客名の自動検出: 文書左上を優先的に検索し、請求先の名前を抽出
ゲスト決済対応: PayPalアカウントがなくてもクレジットカードで支払い可能
簡単な設定画面: PayPal API認証情報の設定や接続テストがブラウザから可能
処理状況の可視化: ファイル処理中のプログレスバー表示
本番環境表示: 本番環境での運用時に明確な表示で警告

技術仕様

バックエンド: Python + Flask
フロントエンド: HTML/CSS/JavaScript + Bootstrap 5
PDF処理:
  pdfplumber (テキスト抽出、表分析)
  PyPDF2 (互換性向上)
  pdf2image + Tesseract OCR (画像ベースのPDF対応)
  pdfminer.six (複雑なエンコーディングのPDF対応)
AI OCR: Google Cloud Vision API、Microsoft Azure Form Recognizer、Tesseract OCR
決済API: PayPal API (v2)
設定管理: JSON形式での保存・管理

使い方

## ローカル環境での利用

### Windowsの場合

1. ZIPファイルを展開後、`run_app.bat`をダブルクリックします。
2. 初回起動時は自動セットアップが行われます。Pythonがインストールされていない場合は自動インストーラーが起動します。必要なライブラリの自動インストールも行われます。デスクトップにショートカットを作成するか選択できます。
3. ブラウザが自動的に開き、アプリケーションにアクセスできます。

### macOSの場合

1. ターミナルを開きます。
2. アプリケーションのディレクトリに移動します：`cd /path/to/pdf-paypal-system`
3. `./run_app.sh`を実行してアプリケーションを起動します。
4. または、`Start_PDF_PayPal_System.command`をFinderからダブルクリックして起動することもできます。
5. ブラウザが自動的に開き、アプリケーションのインターフェースが表示されます。

### 手動起動方法

1. ローカルサーバーを起動: `python app.py`
2. ブラウザでアクセス: `http://localhost:8080`
3. 設定ページでPayPal API情報とOCR設定を行います。
4. ホームページでPDFファイルをアップロードして処理します。
5. 生成された決済リンクを利用して支払いを受け付けます。

## ウェブアプリケーションとしての利用

### Render.comでのデプロイ

1. GitHubアカウントにこのリポジトリをフォークまたはクローンします。
2. [Render.com](https://render.com/)にアクセスし、アカウントを作成またはログインします。
3. ダッシュボードから「New +」→「Web Service」を選択します。
4. GitHubリポジトリを接続し、このプロジェクトを選択します。
5. 以下の設定を行います：
   - **Name**: 任意のアプリ名
   - **Region**: お好みの地域（アジア圏ならSingaporeがおすすめ）
   - **Branch**: `main`
   - **Runtime**: `Docker`
   - **Instance Type**: 無料枠で良い場合は「Free」
6. 環境変数を設定します（`.env.example`を参考）：
   - `PAYPAL_CLIENT_ID`: PayPalのクライアントID
   - `PAYPAL_CLIENT_SECRET`: PayPalのクライアントシークレット
   - `PAYPAL_MODE`: `sandbox`または`live`
   - `SECRET_KEY`: セッション用のランダムな文字列
   - `ENABLE_CSRF_PROTECTION`（任意）: true/false
   - `SESSION_LIFETIME`（任意）: セッション有効期間（分）
   - OCRやAI連携用のAPIキーも必要に応じて設定
7. 「Create Web Service」をクリックしてデプロイを開始します。

---

## セキュリティ・カスタマイズ
- `.env.example`や`config.example.json`を参考に、必要な環境変数を設定してください。
- `SECRET_KEY`は必ずランダムな値に変更してください。
- CSRF対策やセッション有効期間なども環境変数で柔軟に制御できます。

---

## docker-compose拡張例（DBや外部サービス追加時）
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8080:8080"
    env_file:
      - .env
    volumes:
      - ./results:/app/results
      - ./uploads:/app/uploads
    # dbやredis等のサービスを追加可能
  # db:
  #   image: postgres:15
  #   ...
```

### Dockerを使った自己ホスティング

1. リポジトリをクローンします：`git clone https://github.com/yourusername/pdf-paypal-system.git`
2. プロジェクトディレクトリに移動します：`cd pdf-paypal-system`
3. Dockerイメージをビルドします：`docker build -t pdf-paypal-system .`
4. コンテナを実行します：
   ```
   docker run -p 8080:8080 \
   -e PAYPAL_CLIENT_ID=your_client_id \
   -e PAYPAL_CLIENT_SECRET=your_client_secret \
   -e PAYPAL_MODE=sandbox \
   -e SECRET_KEY=your_random_secret \
   pdf-paypal-system
   ```
5. ブラウザで `http://localhost:8080` にアクセスします。

---
