FROM python:3.9-slim

WORKDIR /app

# 必要なライブラリのインストール
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-jpn \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 必要なPythonパッケージのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードのコピー
COPY . .

# アップロードとダウンロードフォルダの作成
RUN mkdir -p uploads results

# PYTHONPATHを設定してアプリディレクトリを検索パスに追加（より明示的に）
ENV PYTHONPATH="/app:/app/modules:/app/utils:${PYTHONPATH}"
RUN echo "PYTHONPATH set to $PYTHONPATH"

# 環境変数の設定
ENV PORT=8080

# ポートの公開
EXPOSE 8080

# Gunicornでアプリケーションを起動（パスを明示的に指定）
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 \
    --pythonpath /app \
    --log-level debug \
    --capture-output \
    --enable-stdio-inheritance \
    app:application
