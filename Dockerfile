FROM python:3.9-slim

WORKDIR /app

# Tesseract OCRのインストール
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-jpn \
    tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 必要なPythonパッケージのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードのコピー
COPY . .

# アップロードとダウンロードフォルダの作成
RUN mkdir -p uploads results

# 環境変数の設定
ENV PORT=8080

# ポートの公開
EXPOSE 8080

# アプリケーションの実行
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
