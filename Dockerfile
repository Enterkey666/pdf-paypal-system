# ====================================
# PDF-PayPal-Stripe システム Dockerfile
# ====================================

# Python 3.9をベースイメージとして使用
FROM python:3.9-slim

# メンテナ情報
LABEL maintainer="PDF-PayPal-Stripe System Team"
LABEL description="PDF processing system with PayPal and Stripe payment integration"
LABEL version="1.0.0"

# 作業ディレクトリを設定
WORKDIR /app

# システムの更新と必要なパッケージのインストール
RUN apt-get update && apt-get install -y \
    # OCR関連
    tesseract-ocr \
    tesseract-ocr-jpn \
    tesseract-ocr-eng \
    # PDF処理関連
    poppler-utils \
    # データベース関連
    libpq-dev \
    # コンパイル関連
    gcc \
    g++ \
    # OpenCV関連
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # ヘルスチェック用
    curl \
    # セキュリティ更新
    && apt-get upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 必要なディレクトリを作成
RUN mkdir -p /app/uploads \
    && mkdir -p /app/results \
    && mkdir -p /app/logs \
    && mkdir -p /app/data \
    && mkdir -p /app/backups \
    && mkdir -p /app/static \
    && mkdir -p /app/templates \
    && mkdir -p /app/test_reports

# Pythonの依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY . .

# 環境変数の設定
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONPATH="/app:/app/modules:/app/utils:${PYTHONPATH}"
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
ENV PORT=8080

# セキュリティ: 非rootユーザーを作成
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app \
    && chmod -R 755 /app

# ログディレクトリの権限設定
RUN chown -R app:app /app/logs \
    && chmod -R 766 /app/logs

# 非rootユーザーに切り替え
USER app

# ヘルスチェック用エンドポイントの設定
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# ポートを公開
EXPOSE 8080

# アプリケーションの起動コマンド (本番環境向け設定)
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--worker-connections", "1000", \
     "--timeout", "120", \
     "--keepalive", "2", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--preload", \
     "--log-level", "info", \
     "--access-logfile", "/app/logs/access.log", \
     "--error-logfile", "/app/logs/error.log", \
     "--capture-output", \
     "app:app"]
