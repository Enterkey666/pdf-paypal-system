#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WSGI entry point for the PDF PayPal System
Renderなどのホスティングサービス用のエントリーポイント
"""

import os
import sys

# カレントディレクトリをPYTHONPATHに追加（デプロイ環境用）
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# アプリケーションをインポート
from app import create_app

# WSGIアプリケーションを作成
application = create_app()

# Gunicornなどから参照されるapp変数
app = application

if __name__ == "__main__":
    # 直接実行された場合は開発サーバーを起動
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
    
    # アプリ初期化と起動
    port = args.port
    host = args.host
    debug_mode = args.debug or os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    print(f"アプリ起動: host={host}, port={port}, debug={debug_mode}")
    app.run(debug=debug_mode, host=host, port=port)
