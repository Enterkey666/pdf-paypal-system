#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# PDF PayPal System - シンプルバージョン

# 必要なモジュールのインポート
import os
import sys
import logging
import tempfile
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request, redirect, url_for, send_from_directory, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# ロガーの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
load_dotenv()

# Flaskアプリケーションの設定
app = Flask(__name__)

# セッション管理のためのシークレットキー設定
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key-change-in-production')

# アップロードフォルダの設定
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads'))
RESULTS_FOLDER = os.environ.get('RESULTS_FOLDER', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results'))

# フォルダが存在しない場合は作成
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# アップロード設定
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULTS_FOLDER'] = RESULTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# ルーティング
@app.route('/')
def index():
    return render_template('index.html', title="PDF PayPal System")

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/upload')
def upload():
    return render_template('upload.html', title="ファイルアップロード")

@app.route('/settings')
def settings():
    return render_template('settings.html', title="設定")

@app.route('/history')
def history():
    return render_template('history.html', title="処理履歴")

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/results/<filename>')
def result_file(filename):
    return send_from_directory(app.config['RESULTS_FOLDER'], filename)

# アプリケーション初期化関数
def create_app():
    logger.info("=== アプリケーション初期化 ===")
    
    # 環境変数の表示（デバッグ用）
    logger.info("=== 環境変数 ===")
    for key in ['PORT', 'UPLOAD_FOLDER', 'RESULTS_FOLDER', 'SECRET_KEY']:
        value = os.environ.get(key, 'Not set')
        # SECRET_KEYはセキュリティ上の理由から値を表示しない
        if key == 'SECRET_KEY' and value != 'Not set':
            logger.info(f"{key}: [設定済み]")
        else:
            logger.info(f"{key}: {value}")
    
    # ルート情報の表示（デバッグ用）
    logger.info("=== ルート情報 ===")
    try:
        for rule in app.url_map.iter_rules():
            logger.info(f"Route: {rule.endpoint} - {rule.rule} - {rule.methods}")
    except Exception as e:
        logger.error(f"ルート情報表示エラー: {str(e)}")
    
    return app

# Gunicorn用のアプリケーションオブジェクト
application = create_app()

# アプリ実行（開発環境用）
if __name__ == '__main__':
    import argparse
    
    # コマンドライン引数を処理
    parser = argparse.ArgumentParser(description='PDF PayPal System')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8080)),
                        help='ポート番号 (デフォルト: 8080 または環境変数PORT)')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='ホスト (デフォルト: 0.0.0.0)')
    parser.add_argument('--debug', action='store_true',
                        help='デバッグモードを有効にする')
    
    args = parser.parse_args()
    
    # アプリ起動パラメータ
    port = args.port
    host = args.host
    debug_mode = args.debug or os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    logger.info(f"アプリ起動: host={host}, port={port}, debug={debug_mode}")
    
    # アプリケーションを実行
    application.run(debug=debug_mode, host=host, port=port)
