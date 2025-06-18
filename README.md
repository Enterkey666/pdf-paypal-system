# PDF一括処理 & PayPal決済リンク発行システム

## 概要

PDFファイルをアップロードして、請求金額と請求先情報を自動抽出し、PayPal決済用のリンクを自動生成するシステムです。複数のPDFファイルをバッチ処理することができます。ゲスト決済対応のPayPalリンクを生成し、請求業務を効率化します。

## 最新の更新内容（2025年6月17日）

- **履歴削除機能の修正と強化**:
  - ルーティングの不一致を解消（`/delete_history`と`/history/delete`の二重定義を修正）
  - ファイルパスの不一致を修正（`UPLOAD_FOLDER`から`RESULTS_FOLDER`に変更）
  - PayPal API連携による注文情報の削除機能追加
  - エラーハンドリングの強化と詳細な結果表示

- **ナビゲーションUIの改善**:
  - ナビゲーションリンクとバッジの幅を拡大（`min-width: 120px`設定）
  - パディングの増加とテキスト中央揃え
  - ホバーエフェクトの追加（浮き上がる効果とシャドウ）

- **履歴表示機能の改善**:
  - 処理日時（タイムスタンプ）の表示を追加
  - ゲストユーザーへの履歴表示機能の追加
  - 顧客名表示の不一致を解消

- **顧客名抽出ロジックの改善** (2025年6月14日):
  - 「〜様」「御中」パターン検出の正確性向上
  - 括弧（日本語・英語）の除去と空白正規化の前処理追加
  - テキストフィルタリングの最適化（「合計」「小計」などを含む行の除外）
  - フィルタリング後のテキストが短すぎる場合の元テキスト使用機能
  - ファイル名からの顧客名抽出機能強化

## 主な機能

- PDFファイルのアップロード（ドラッグ＆ドロップ対応）
- 請求金額の自動抽出（自動抽出できない場合は手動入力可能）
- 請求先名の自動抽出（「〇〇様」「〇〇御中」の形式で正確に検出）
- PayPal決済リンクの自動生成（アカウント不要のゲスト決済対応）
- 複数ファイルの一括処理
- PayPal APIの設定管理機能
- 設定のインポート/エクスポート機能
- 処理履歴の管理と表示（ゲストユーザーも閲覧可能）
- 代替候補からの選択機能

## 特徴

- **AI OCR機能**: Google Cloud Vision API、Microsoft Azure Form Recognizer、Tesseract OCRの選択が可能
- **高精度な請求金額抽出**: 様々な形式の請求書・領収書から金額を正確に抽出
- **顧客名の自動検出**: 文書左上を優先的に検索し、「〜様」「御中」パターンを正確に検出
- **代替候補機能**: 複数の顧客名候補から選択可能
- **ゲスト決済対応**: PayPalアカウントがなくてもクレジットカードで支払い可能
- **簡単な設定画面**: PayPal API認証情報の設定や接続テストがブラウザから可能
- **処理状況の可視化**: ファイル処理中のプログレスバー表示
- **本番環境表示**: 本番環境での運用時に明確な表示で警告
- **テキストフィルタリング**: 金額関連の行を自動除外し、顧客名抽出精度を向上

## 技術仕様

- **バックエンド**: Python + Flask
- **フロントエンド**: HTML/CSS/JavaScript + Bootstrap 5
- **PDF処理**:
  - pdfplumber (テキスト抽出、表分析)
  - PyPDF2 (互換性向上)
  - pdf2image + Tesseract OCR (画像ベースのPDF対応)
  - pdfminer.six (複雑なエンコーディングのPDF対応)
- **顧客名抽出**:
  - 正規表現パターンマッチング
  - キャッシュ機能と代替候補管理
  - ファイル名からの抽出フォールバック
- **AI OCR**: Google Cloud Vision API、Microsoft Azure Form Recognizer、Tesseract OCR
- **決済API**: PayPal API (v2)
- **設定管理**: JSON形式での保存・管理
- **キャッシュ機能**: メモリ内キャッシュ、タイムスタンプ管理

## 使い方

### ローカル環境での利用

#### Windowsの場合

1. ZIPファイルを展開後、`run_app.bat`をダブルクリックします。
2. 初回起動時は自動セットアップが行われます。Pythonがインストールされていない場合は自動インストーラーが起動します。
3. ブラウザが自動的に開き、アプリケーションにアクセスできます。

#### macOSの場合

1. ターミナルを開きます。
2. アプリケーションのディレクトリに移動します：`cd /path/to/pdf-paypal-system`
3. `./run_app.sh`を実行してアプリケーションを起動します。
4. または、`Start_PDF_PayPal_System.command`をFinderからダブルクリックして起動することもできます。

#### 手動起動方法

1. ローカルサーバーを起動: `python app.py`
2. ブラウザでアクセス: `http://localhost:8080`
3. 設定ページでPayPal API情報とOCR設定を行います。
4. ホームページでPDFファイルをアップロードして処理します。

### ウェブアプリケーションとしての利用

#### Render.comでのデプロイ

1. GitHubアカウントにこのリポジトリをフォークまたはクローンします。
2. [Render.com](https://render.com/)にアクセスし、アカウントを作成またはログインします。
3. ダッシュボードから「New +」→「Web Service」を選択します。
4. GitHubリポジトリを接続し、このプロジェクトを選択します。
5. 以下の設定を行います：
   - **Name**: 任意のアプリ名
   - **Region**: お好みの地域（アジア圈ならSingaporeがおすすめ）
   - **Branch**: `main`
   - **Runtime**: `Docker`
   - **Instance Type**: 無料枠で良い場合は「Free」
6. 環境変数を設定します：
   - `PAYPAL_CLIENT_ID`: PayPalのクライアントID
   - `PAYPAL_CLIENT_SECRET`: PayPalのクライアントシークレット
   - `PAYPAL_MODE`: `sandbox`または`live`
   - `SECRET_KEY`: セッション用のランダムな文字列
   - `S3_BUCKET_NAME`: PDFファイル保存用のS3バケット名（推奨）
   - `AWS_ACCESS_KEY`: S3アクセス用（推奨）
   - `AWS_SECRET_KEY`: S3アクセス用（推奨）
   - `REDIS_URL`: キャッシュの永続化用（オプション）
   - OCRやAI連携用のAPIキーも必要に応じて設定

---

## セキュリティ・カスタマイズ
- `.env.example`や`config.example.json`を参考に、必要な環境変数を設定してください。
- `SECRET_KEY`は必ずランダムな値に変更してください。
- CSRF対策やセッション有効期間なども環境変数で柔軟に制御できます。

## Renderデプロイに向けた改善点

### 必要な機能

1. **環境変数対応**
   - コード内で`os.environ.get()`を使用して環境変数から設定を読み込むように修正
   - 例: `PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID', config.get('paypal_client_id'))`

2. **ファイルストレージの対応**
   - S3互換ストレージの統合
   - アップロードされたPDFファイルの保存先を外部ストレージに変更

3. **Gunicornの設定**
   - `Procfile`の作成: `web: gunicorn app:app`
   - スレッド数やタイムアウトの最適化

### 実装済みの機能

1. **バッチ処理機能**
   - 複数のPDFファイルを一度に処理する機能
   - 処理状況のプログレスバー表示

2. **ユーザー認証**
   - 管理者ログイン機能（デフォルト: admin/admin）
   - 一部機能へのアクセス制限

3. **処理履歴の保存と表示**
   - 過去に処理したPDFの履歴をJSON形式で保存
   - 履歴の詳細表示と削除機能
   - PayPal連携による注文情報の削除

### 今後の拡張予定

1. **キャッシュの永続化**
   - Redis等を使用した永続的なキャッシュの実装
   - アプリ再起動後もキャッシュが維持されるように

2. **ヘルスチェックエンドポイント**
   - アプリケーションの状態を監視するためのエンドポイント
   - Renderでの自動ヘルスチェックに対応

3. **レポート機能**
   - 処理履歴の統計情報表示
   - エクスポート機能の強化

---

## 最新の改善内容の詳細

### 顧客名抽出ロジックの改善

- **テキストフィルタリングの最適化**
  ```python
  # 金額関連の行を除外するフィルタリング
  filtered_text = "\n".join([line for line in text.split('\n') if not any(term in line for term in ['合計', '小計', '総額', '金額'])])
  # フィルタリング後のテキストが短すぎる場合は元のテキストを使用
  if len(filtered_text) < 50:
      filtered_text = text
  ```

- **代替候補取得の修正**
  ```python
  # キャッシュキーを生成して代替候補を取得
  cache_key = filename if filename else hashlib.md5(text[:1000].encode()).hexdigest()
  customer_alternatives = customer_extractor.get_alternatives(cache_key)
  ```

これらの改善により、顧客名抽出の精度が向上し、エラーの発生が減少しました。
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
