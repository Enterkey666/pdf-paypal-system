#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# デバッグ用の最小限のFlaskアプリケーション
# 段階的に機能を追加して問題を特定するために使用

import os
import sys
import logging
import traceback
from flask import Flask, jsonify, render_template, request, redirect, url_for

# ロガーの設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# システムパスの設定
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
    logger.info(f"Added {current_dir} to sys.path")

# インストールされているパッケージの一覧を表示
logger.info("=== インストールされているパッケージ ===")
try:
    import pkg_resources
    installed_packages = sorted([f"{pkg.key}=={pkg.version}" for pkg in pkg_resources.working_set])
    for pkg in installed_packages:
        logger.info(pkg)
except Exception as e:
    logger.error(f"パッケージ一覧の取得エラー: {str(e)}")

# 環境変数の読み込み
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("環境変数を.envファイルから読み込みました")
except ImportError:
    logger.warning("python-dotenvがインストールされていないため、.envファイルからの環境変数の読み込みをスキップします")
except Exception as e:
    logger.error(f"環境変数の読み込みエラー: {str(e)}")

# Flaskアプリケーションの作成
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

# 環境変数の表示
logger.info("=== 環境変数 ===")
for key in ['PORT', 'UPLOAD_FOLDER', 'RESULTS_FOLDER', 'SECRET_KEY', 'PAYPAL_CLIENT_ID', 'PAYPAL_CLIENT_SECRET']:
    value = os.environ.get(key, 'Not set')
    # SECRET_KEYとPAYPAL関連の値はセキュリティ上の理由から値を表示しない
    if key in ['SECRET_KEY', 'PAYPAL_CLIENT_ID', 'PAYPAL_CLIENT_SECRET'] and value != 'Not set':
        logger.info(f"{key}: [設定済み]")
    else:
        logger.info(f"{key}: {value}")

# ルーティング
@app.route('/')
def index():
    return render_template('index.html', title="PDF PayPal System - デバッグモード")

@app.route('/health')
def health():
    # システム情報を含むヘルスチェック
    import platform
    health_info = {
        "status": "healthy",
        "python_version": sys.version,
        "platform": platform.platform(),
        "environment": os.environ.get('FLASK_ENV', 'production'),
        "upload_folder": app.config['UPLOAD_FOLDER'],
        "results_folder": app.config['RESULTS_FOLDER'],
        "secret_key_set": app.config['SECRET_KEY'] != 'default-dev-key-change-in-production',
        "paypal_config_set": os.environ.get('PAYPAL_CLIENT_ID') is not None
    }
    return jsonify(health_info)

@app.route('/debug')
def debug():
    # デバッグ情報を表示するページ
    debug_info = {
        "routes": [str(rule) for rule in app.url_map.iter_rules()],
        "blueprints": list(app.blueprints.keys()) if hasattr(app, 'blueprints') else [],
        "config": {k: v for k, v in app.config.items() if k not in ['SECRET_KEY']}
    }
    return jsonify(debug_info)

# エラーハンドラー
@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"error": "Page not found", "status_code": 404}), 404

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({"error": "Internal server error", "status_code": 500}), 500

# アプリケーション初期化関数
def create_app():
    logger.info("=== アプリケーション初期化 ===")
    
    # ルート情報の表示
    logger.info("=== ルート情報 ===")
    try:
        for rule in app.url_map.iter_rules():
            logger.info(f"Route: {rule.endpoint} - {rule.rule} - {rule.methods}")
    except Exception as e:
        logger.error(f"ルート情報表示エラー: {str(e)}")
    
    logger.info("アプリケーション初期化が完了しました")
    return app

# Gunicorn用のアプリケーションオブジェクト
application = create_app()

# アプリ実行（開発環境用）
if __name__ == '__main__':
    import argparse
    
    # コマンドライン引数を処理
    parser = argparse.ArgumentParser(description='PDF PayPal System - Debug Mode')
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
