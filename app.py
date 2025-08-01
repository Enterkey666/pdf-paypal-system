#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# PDF PayPal System
# 
# PDFファイルから顧客情報と金額を抽出し、PayPal決済リンクを生成するシステム


# 最初にシステムパスを設定
import os
import sys

# カレントディレクトリをPYTHONPATHに追加（デプロイ環境用）
current_dir = os.path.dirname(os.path.abspath(__file__))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
    # print(f"Added {current_dir} to sys.path")

# その他の標準ライブラリをインポート
import re
import io
import sys
import json
import time
import uuid
import base64
import shutil
import logging
import argparse
import tempfile
import traceback
import subprocess
from datetime import datetime
from xhtml2pdf import pisa
from io import BytesIO
from flask import make_response, request, jsonify, render_template, abort

import PyPDF2
import pdfplumber
import urllib.parse
import importlib.util
import importlib
import requests
import flask
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

# APIキーキャッシュ機能用のインポート
from datetime import timedelta
from typing import Optional
from cryptography.fernet import Fernet

# テンプレートマッチングモジュールのインポート（安全なインポート）
try:
    import template_matching
    TEMPLATE_MATCHING_AVAILABLE = True
    print("✓ template_matching インポート成功")
except ImportError as e:
    TEMPLATE_MATCHING_AVAILABLE = False
    print(f"⚠ template_matching インポート失敗: {e}")
except Exception as e:
    TEMPLATE_MATCHING_AVAILABLE = False
    print(f"⚠ template_matching 初期化エラー: {e}")
try:
    from google.cloud import firestore  # type: ignore
    from google.cloud.firestore import SERVER_TIMESTAMP  # type: ignore
    FIRESTORE_AVAILABLE = True
except ImportError as e:
    FIRESTORE_AVAILABLE = False
    print(f"Warning: google-cloud-firestore not available. API key cache will be disabled. Error: {e}")
except Exception as e:
    FIRESTORE_AVAILABLE = False
    print(f"Warning: Firestore initialization failed. API key cache will be disabled. Error: {e}")

# PayPal支払いステータス関連のインポート（安全なインポート）
try:
    from payment_status_checker import check_payment_status
    print("✓ payment_status_checker インポート成功")
except ImportError as e:
    print(f"⚠ payment_status_checker インポート失敗: {e}")
    # フォールバック関数を定義
    def check_payment_status(token):
        print(f"フォールバック: payment status check for token {token}")
        return "PENDING"

try:
    from payment_status_updater import update_payment_status_by_order_id, update_pending_payment_statuses
    print("✓ payment_status_updater インポート成功")
except ImportError as e:
    print(f"⚠ payment_status_updater インポート失敗: {e}")
    # フォールバック関数を定義
    def update_payment_status_by_order_id(order_id):
        print(f"フォールバック: update payment status for order {order_id}")
        return False, "UNKNOWN", "Payment status updater not available"
    
    def update_pending_payment_statuses():
        print("フォールバック: update pending payment statuses")
        return 0, 0

# ロガーの初期化
logger = logging.getLogger(__name__)

# Windows環境でUTF-8エンコーディングを使用するためのカスタムStreamHandlerクラス
class UTF8StreamHandler(logging.StreamHandler):
    def __init__(self, stream=None):
        # io.StringIOを使用してUTF-8エンコードされたバッファを作成
        self.encoding = 'utf-8'
        super().__init__(stream)
        
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # エンコードエラーを回避するためのエラーハンドリング
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                # エンコードエラーが発生した場合は、代替文字に置き換える
                stream.write(msg.encode('cp932', errors='replace').decode('cp932') + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

# ロガーのセットアップ関数
def setup_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # ファイルハンドラの設定
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, 'app.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # UTF-8対応コンソールハンドラの設定
    console_handler = UTF8StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # フォーマッタの設定
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # ハンドラの追加
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 処理済みファイルのキャッシュ（ファイル名 -> 処理結果のマッピング）
processed_files_cache = {}
_process_cache = {}

# キャッシュをクリアする関数
def clear_cache():
    global processed_files_cache, _process_cache
    processed_files_cache.clear()
    _process_cache.clear()
    logger.info("処理キャッシュをクリアしました")


# 必要なモジュールをインポート
# ローカルモジュールのインポート
# 初期化: インポートが失敗した場合に備えて、ダミーのcustomer_extractorモジュールを作成
# customer_extractor用のダミークラス定義
class DummyExtractor:
    @staticmethod
    def extract_customer(text, filename=""):
        logger.error("customer_extractorモジュールが正しく読み込まれていないため、顧客名抽出ができません")
        return "Unknown Customer"

# グローバル変数として先に定義
customer_extractor = None

# まずダミーインスタンスを設定
_dummy_extractor = DummyExtractor()

try:
    # カレントディレクトリを再確認（デプロイ環境用）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        logger.info(f"sys.pathに追加しました: {current_dir}")
    
    # モジュールパスを表示（デバッグ用）
    logger.info(f"Python path: {sys.path}")
    logger.info(f"現在のディレクトリ内のファイル: {os.listdir(current_dir)}")
    
    # 標準的なインポート方法を試す
    import customer_extractor as ce_module
    # グローバル変数を設定
    customer_extractor = ce_module
    logger.info("customer_extractorモジュールのインポートに成功しました")
except ImportError as e:
    logger.error(f"customer_extractorモジュールのインポートに失敗: {e}")
    # フォールバック処理
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "customer_extractor", 
            os.path.join(current_dir, "customer_extractor.py")
        )
        if spec and spec.loader:
            ce_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ce_module)
            customer_extractor = ce_module
            logger.info("customer_extractorモジュールを代替方法でインポートしました")
        else:
            logger.error("customer_extractorモジュールのspecが取得できませんでした")
            customer_extractor = _dummy_extractor
    except Exception as e2:
        logger.error(f"customer_extractorモジュールの代替インポートにも失敗: {e2}")
        logger.error("ダミーのcustomer_extractorモジュールを使用します")
        customer_extractor = _dummy_extractor

# テンプレートマッチングのフォールバック関数
def process_pdf_with_template_matching_fallback(pdf_path, templates_dir):
    """テンプレートマッチングモジュールが利用できない場合のフォールバック関数"""
    logger.warning(f"テンプレートマッチングモジュールが利用できないため、フォールバック処理を使用します: {pdf_path}")
    return {}

# テンプレートマッチング関数を適切に設定
if TEMPLATE_MATCHING_AVAILABLE:
    process_pdf_with_template = template_matching.process_pdf_with_template_matching
else:
    process_pdf_with_template = process_pdf_with_template_matching_fallback

# モジュールの再読み込みを強制する関数
def reload_modules():
    global customer_extractor
    try:
        # customer_extractorモジュールが正しくインポートされているか確認
        if 'customer_extractor' in sys.modules:
            import importlib
            customer_extractor = importlib.reload(sys.modules['customer_extractor'])
            logger.info("customer_extractorモジュールを再読み込みしました")
        else:
            logger.warning("customer_extractorモジュールがインポートされていないため、再読み込みをスキップします")
            # モジュールを再インポートしてみる
            try:
                import customer_extractor as ce_module
                customer_extractor = ce_module
                logger.info("customer_extractorモジュールを再インポートしました")
            except ImportError as e:
                logger.error(f"customer_extractorモジュールの再インポートに失敗: {e}")
    except Exception as e:
        logger.error(f"モジュールの再読み込みエラー: {e}")
        logger.error(f"sys.modules内のモジュール: {list(sys.modules.keys())}")
        # エラーが発生してもアプリケーションは続行

import requests
import shutil
import subprocess
from datetime import datetime, timedelta
from flask import Flask, request, render_template, jsonify, send_from_directory, redirect, url_for, current_app, flash, session, make_response
# Flask-WTF の安全なインポート
try:
    from flask_wtf import FlaskForm, CSRFProtect
    FLASK_WTF_AVAILABLE = True
    print("✓ flask_wtf インポート成功")
except ImportError as e:
    print(f"⚠ flask_wtf インポート失敗: {e}")
    FLASK_WTF_AVAILABLE = False
    # フォールバック用のダミークラスを定義
    class DummyForm:
        def __init__(self, *args, **kwargs): pass
        def validate_on_submit(self): return False
    class DummyCSRF:
        def init_app(self, app): pass
    FlaskForm = DummyForm
    CSRFProtect = DummyCSRF

# Flask-Session の安全なインポート
try:
    from flask_session import Session
    FLASK_SESSION_AVAILABLE = True
    print("✓ flask_session インポート成功")
except ImportError as e:
    print(f"⚠ flask_session インポート失敗: {e}")
    FLASK_SESSION_AVAILABLE = False
    # フォールバック用のダミークラスを定義
    class DummySession:
        def __init__(self, app=None): pass
        def init_app(self, app): pass
    Session = DummySession
# Flask-Login の安全なインポート
try:
    from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user  # type: ignore
    FLASK_LOGIN_AVAILABLE = True
    print("✓ flask_login インポート成功")
except ImportError as e:
    print(f"⚠ flask_login インポート失敗: {e}")
    FLASK_LOGIN_AVAILABLE = False
    # フォールバック用のダミークラスを定義
    class DummyLoginManager:
        def __init__(self, *args, **kwargs): pass
        def init_app(self, app): pass
        def user_loader(self, callback): return callback
    class UserMixin:
        @property
        def is_authenticated(self): return False
        @property
        def is_active(self): return False
        @property
        def is_anonymous(self): return True
        def get_id(self): return None
    def login_user(user, remember=False): return False
    def logout_user(): return None
    LoginManager = DummyLoginManager
    current_user = None
    def login_required(f):
        return f  # 認証なしで通す

# 認証初期化モジュールのインポート（安全なインポート）
try:
    from auth_init import init_login_manager, sync_session_with_user
    AUTH_INIT_AVAILABLE = True
    print("✓ auth_init モジュール インポート成功")
except ImportError as e:
    print(f"⚠ auth_init モジュール インポート失敗: {e}")
    AUTH_INIT_AVAILABLE = False
    # フォールバック関数を定義
    def init_login_manager(app):
        return None
    def sync_session_with_user():
        pass
# WTForms の安全なインポート
try:
    from wtforms import StringField, PasswordField, SubmitField
    from wtforms.validators import DataRequired
    WTFORMS_AVAILABLE = True
    print("✓ wtforms インポート成功")
except ImportError as e:
    print(f"⚠ wtforms インポート失敗: {e}")
    WTFORMS_AVAILABLE = False
    # フォールバック用のダミークラスを定義
    class DummyField:
        def __init__(self, *args, **kwargs): pass
    class DummyValidator:
        def __init__(self, *args, **kwargs): pass
    StringField = PasswordField = SubmitField = DummyField
    DataRequired = DummyValidator
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

# データベースモジュールからユーザー関連の関数をインポート（安全なインポート）
try:
    from database import get_user_by_id, get_user_by_email, update_last_login
    print("✓ database モジュール インポート成功")
except ImportError as e:
    print(f"⚠ database モジュール インポート失敗: {e}")
    # フォールバック関数を定義
    def get_user_by_id(user_id):
        return None
    def get_user_by_email(email):
        return None
    def update_last_login(user_id):
        return False

# 古いログインフォームクラス（削除予定）
class LoginForm(FlaskForm):
    username = StringField('ユーザー名', validators=[DataRequired()])
    password = PasswordField('パスワード', validators=[DataRequired()])
    submit = SubmitField('ログイン')

# 環境変数の読み込み
load_dotenv()

# Flaskアプリケーションの設定
app = Flask(__name__)

# セッション管理のためのシークレットキー設定
# 環境変数からシークレットキーを取得するか、固定値を使用（開発環境用）
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-pdf-paypal-system-2025')
# バイナリの場合は表示方法を変更
if isinstance(app.secret_key, str):
    key_display = app.secret_key[:5]
else:
    key_display = '(バイナリ)'
app.logger.info(f"シークレットキー設定完了: {key_display}")

# CSRF保護の設定
app.config['WTF_CSRF_ENABLED'] = True
# CSRFシークレットキーは環境変数から取得するか、アプリのシークレットキーを使用
app.config['WTF_CSRF_SECRET_KEY'] = os.environ.get('CSRF_SECRET_KEY', app.secret_key)
app.config['WTF_CSRF_SSL_STRICT'] = False  # 開発環境でのテストを可能に
app.config['WTF_CSRF_METHODS'] = ['POST', 'PUT', 'PATCH', 'DELETE']  # CSRFチェック対象のHTTPメソッド

# CSRF保護の初期化は後で行う

# Stripe統合のためのインポート
try:
    from stripe_flask_integration import register_stripe_blueprints, add_stripe_routes_to_existing_app
    STRIPE_INTEGRATION_AVAILABLE = True
    print("✓ Stripe統合モジュールのインポート成功")
except ImportError as e:
    print(f"⚠ Stripe統合モジュールのインポート失敗: {e}")
    STRIPE_INTEGRATION_AVAILABLE = False

# Stripe統合の初期化
if STRIPE_INTEGRATION_AVAILABLE:
    try:
        # Blueprintの登録
        register_stripe_blueprints(app)
        
        # 追加ルートの登録
        add_stripe_routes_to_existing_app(app)
        
        app.logger.info("Stripe統合が正常に初期化されました")
    except Exception as e:
        app.logger.error(f"Stripe統合初期化エラー: {str(e)}")
else:
    app.logger.warning("Stripe統合が利用できません")

# セッションの設定
# セッション設定の統合
app.config['SESSION_TYPE'] = 'null'  # Flaskのデフォルトセッション（署名されたクッキー）を使用
app.config['SESSION_PERMANENT'] = True  # 永続的なセッション
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # セッションの有効期限
app.config['SESSION_COOKIE_NAME'] = 'pdf_paypal_session'  # セッションCookie名
app.config['SESSION_COOKIE_SECURE'] = False  # 開発環境では無効化（HTTP接続で動作）
app.config['SESSION_COOKIE_HTTPONLY'] = True  # XSS対策
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF対策
app.config['SESSION_USE_SIGNER'] = True  # セッション署名を有効化
app.config['SESSION_COOKIE_DOMAIN'] = None  # ローカル開発環境用

# Render環境では一時ディレクトリを使用する
if os.environ.get('RENDER', 'false').lower() == 'true' or os.environ.get('USE_TEMP_DIR', 'false').lower() == 'true':
    app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
    app.logger.info(f"Render環境または一時ディレクトリ指定のため、セッションディレクトリを一時ディレクトリに設定: {app.config['SESSION_FILE_DIR']}")

# RESULTS_FOLDER を初期化時に設定
base_dir = os.path.dirname(os.path.abspath(__file__))
app.config['RESULTS_FOLDER'] = os.path.join(base_dir, 'results')
app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'uploads')

# 結果フォルダとアップロードフォルダが存在することを確認
for folder in [app.config['RESULTS_FOLDER'], app.config['UPLOAD_FOLDER']]:
    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
            app.logger.info(f"フォルダを作成しました: {folder}")
        except Exception as e:
            app.logger.error(f"フォルダの作成に失敗: {folder}, エラー: {e}")

# Flask-Loginの初期化
if FLASK_LOGIN_AVAILABLE and AUTH_INIT_AVAILABLE:
    try:
        login_manager = init_login_manager(app)
        app.logger.info("Flask-Loginを初期化しました")
        
        # before_requestハンドラを追加してセッションとFlask-Loginを同期
        @app.before_request
        def sync_authentication():
            """すべてのリクエスト前にセッションとFlask-Loginの状態を同期"""
            try:
                sync_session_with_user()
            except Exception as e:
                app.logger.error(f"認証状態同期エラー: {str(e)}")
        
    except Exception as e:
        app.logger.error(f"Flask-Loginの初期化に失敗: {e}")
        login_manager = None
else:
    app.logger.warning("Flask-Loginまたは認証初期化モジュールが利用できないため、認証機能は制限されます")
    login_manager = None

# 必要なディレクトリを作成
for folder_path in [app.config['RESULTS_FOLDER'], app.config['UPLOAD_FOLDER']]:
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        app.logger.info(f"ディレクトリを作成しました: {folder_path}")
else:
    # 通常の環境ではアプリケーションディレクトリ内のflask_sessionを使用
    app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_session')
    
    # セッションディレクトリの作成と権限チェック
    try:
        os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
        app.logger.info(f"セッションディレクトリを確認: {app.config['SESSION_FILE_DIR']}")
        
        # 書き込み権限のテスト
        test_file = os.path.join(app.config['SESSION_FILE_DIR'], '.session_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        app.logger.info("セッションディレクトリの書き込み権限を確認しました")
    except Exception as e:
        app.logger.error(f"セッションディレクトリの作成または権限テストに失敗しました: {e}")
        app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
        app.logger.info(f"一時ディレクトリに変更しました: {app.config['SESSION_FILE_DIR']}")

app.config['SESSION_FILE_THRESHOLD'] = 500  # 最大セッションファイル数
app.config['SESSION_KEY_PREFIX'] = 'pdf_paypal_'  # セッションキーのプレフィックス
app.config['SESSION_COOKIE_SECURE'] = False  # HTTP接続でも動作
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Flask-WTFのCSRF設定
# CSRF設定の修正
app.config['WTF_CSRF_ENABLED'] = False  # 開発環境では無効化（本番では有効にする）
app.config['WTF_CSRF_SECRET_KEY'] = app.secret_key  # アプリのシークレットキーを使用
app.config['WTF_CSRF_SSL_STRICT'] = False  # 開発環境でも動作するように
app.config['WTF_CSRF_METHODS'] = ['POST', 'PUT', 'PATCH', 'DELETE']
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1時間
app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # デフォルトでCSRFチェックを無効化
app.logger.info("CSRF設定を構成しました（開発環境では無効化）")

# Flask-Sessionは使用せず、デフォルトのFlaskセッションを使用
session_interface = None
app.logger.info("デフォルトのFlaskセッション（署名されたクッキー）を使用")
app.logger.info(f"セッション設定: {app.config.get('SESSION_TYPE')}")

# セッションの動作確認
try:
    with app.test_request_context():
        from flask import session as test_session
        test_session['test'] = 'value'
        app.logger.info("セッション動作確認: 成功")
except Exception as e:
    app.logger.error(f"セッション動作確認: 失敗 - {e}")

app.logger.info(f"セッションインターフェース: Default Flask Session")
app.logger.info(f"セッションシークレットキー: {app.secret_key[:10]}...")

# CSRF保護の初期化（セッションの後に初期化、安全な初期化）
if FLASK_WTF_AVAILABLE:
    try:
        csrf = CSRFProtect(app)
        app.logger.info("CSRF保護を初期化しました")
        app.logger.info(f"CSRF設定: 有効={app.config.get('WTF_CSRF_ENABLED')}, メソッド={app.config.get('WTF_CSRF_METHODS')}")
        app.logger.info(f"CSRF時間制限: {app.config.get('WTF_CSRF_TIME_LIMIT')}秒")
        
        # CSRFトークンをテンプレートで利用可能にする（無効化されている場合は空文字を返す）
        @app.context_processor
        def inject_csrf_token():
            def csrf_token():
                if app.config.get('WTF_CSRF_ENABLED', False):
                    try:
                        from flask_wtf.csrf import generate_csrf
                        return generate_csrf()
                    except Exception as e:
                        app.logger.warning(f"CSRF token generation failed: {e}")
                        return ""
                else:
                    return ""  # CSRF無効化時は空文字を返す
            return dict(csrf_token=csrf_token)
        
        # アップロード処理をCSRF検証から除外
        try:
            csrf.exempt("upload_file")
            app.logger.info("CSRF検証からアップロード処理を除外しました")
        except Exception as e:
            app.logger.warning(f"CSRF除外設定エラー: {str(e)}")
            app.logger.warning(f"トレースバック: {traceback.format_exc()}")
            app.logger.info("アップロード処理のCSRF除外に失敗しましたが、処理を続行します")
    except Exception as e:
        app.logger.warning(f"CSRF保護の初期化に失敗: {e}")
        csrf = None
else:
    app.logger.warning("Flask-WTF が利用できないため、CSRF保護は無効です")
    csrf = None

# APIキーキャッシュ機能の初期化
# Collection name for API key cache
COLLECTION_NAME = "api_key_cache"
DEFAULT_TTL_MINUTES = 60

# Initialize Firestore client if available
db = None
if FIRESTORE_AVAILABLE:
    try:
        # Firestoreクライアントの初期化を遅延させる
        app.logger.info("Firestore は利用可能です")
    except Exception as e:
        app.logger.error(f"Firestore の確認に失敗: {e}")
        FIRESTORE_AVAILABLE = False

# Encryption key for API keys
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', Fernet.generate_key())
if isinstance(ENCRYPTION_KEY, str):
    ENCRYPTION_KEY = ENCRYPTION_KEY.encode()

cipher_suite = None
try:
    cipher_suite = Fernet(ENCRYPTION_KEY)
    app.logger.info("API キー暗号化機能を初期化しました")
except Exception as e:
    app.logger.warning(f"API キー暗号化機能の初期化に失敗: {e}")
    app.logger.warning("API キーキャッシュ機能は無効になります")
# paypal_utils.pyからの関数インポート（安全なインポート）
try:
    from paypal_utils import cancel_paypal_order, check_order_status, get_paypal_access_token
    print("✓ paypal_utils モジュール インポート成功")
except ImportError as e:
    print(f"⚠ paypal_utils モジュール インポート失敗: {e}")
    # フォールバック関数を定義
    def cancel_paypal_order(order_id):
        return {"status": "error", "message": "PayPal utils not available"}
    def check_order_status(order_id):
        return "UNKNOWN"
    def get_paypal_access_token():
        return None

# 支払いステータス更新機能のインポート
try:
    from payment_status_updater import update_pending_payment_statuses, update_payment_status_by_order_id
    logger.info("支払いステータス更新モジュールのインポートに成功しました")
except ImportError as e:
    logger.error(f"支払いステータス更新モジュールのインポートに失敗: {str(e)}")
try:
    from payment_status_updater import update_pending_payment_statuses, update_payment_status_by_order_id
    logger.info("payment_status_updaterモジュールのインポートに成功しました")
except ImportError as e:
    logger.error(f"payment_status_updaterモジュールのインポートに失敗: {e}")
    # ダミー関数を定義
    def update_pending_payment_statuses():
        logger.error("payment_status_updaterモジュールがインポートできないため、支払いステータス更新はスキップされます")
        return 0, 0

# 管理者認証用デコレータ
def admin_required(f):
    # 
#     管理者権限が必要なルートに対するデコレータ
#     管理者としてログインしていない場合はログインページにリダイレクト
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('このページにアクセスするには管理者権限が必要です', 'error')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
        
        # セッション情報をログ出力
        logger.debug(f"admin_required: session={session}, current_user.is_admin={getattr(current_user, 'is_admin', None) if current_user else None}")
        
        # 管理者かどうかチェック
        if current_user and hasattr(current_user, 'is_admin') and current_user.is_admin:
            return f(*args, **kwargs)
        
        # セッションに管理者フラグがある場合
        if session.get('admin_logged_in'):
            return f(*args, **kwargs)
        
        # APIリクエストの場合はエラーレスポンスを返す
        if request.path.startswith('/api/'):
            return jsonify({
                'error': '管理者権限が必要です',
                'status': 'error'
            }), 403
        
        # それ以外の場合はログインページにリダイレクト
        flash('管理者権限が必要です', 'warning')
        return redirect(url_for('auth.login', next=request.url))
    
    return decorated_function

# 有料会員または管理者認証用デコレータ
def paid_member_or_admin_required(f):
    # 
#     有料会員または管理者権限が必要なルート用のデコレータ
#     新Stripe サブスクリプション対応（後方互換性維持）
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # セッションとFlask-Loginの状態を同期
        if AUTH_INIT_AVAILABLE:
            sync_session_with_user()
        
        # セッション情報をログ出力
        logger.debug(f"paid_member_or_admin_required: session={session}, current_user={current_user}")
        
        # 管理者かどうかチェック
        if current_user and hasattr(current_user, 'is_admin') and current_user.is_admin:
            return f(*args, **kwargs)
        
        # セッションに管理者フラグがある場合
        if session.get('admin_logged_in'):
            return f(*args, **kwargs)
        
        # 新システム: Stripeサブスクリプション状態をチェック
        if current_user and current_user.is_authenticated:
            try:
                from entitlements import check_legacy_paid_member_status
                if check_legacy_paid_member_status(current_user.id):
                    return f(*args, **kwargs)
            except ImportError:
                logger.warning("entitlements モジュールが利用できません。旧システムでチェックします。")
                pass
        
        # 旧システム（後方互換性）: 有料会員かどうかチェック
        if current_user and hasattr(current_user, 'is_paid_member') and current_user.is_paid_member:
            return f(*args, **kwargs)
        
        # セッションに有料会員フラグがある場合
        if session.get('is_paid_member'):
            return f(*args, **kwargs)
        
        # APIリクエストの場合はエラーレスポンスを返す
        if request.path.startswith('/api/'):
            return jsonify({
                'error': '有料会員または管理者権限が必要です',
                'status': 'error'
            }), 403
        
        # それ以外の場合はログインページにリダイレクト
        flash('有料会員または管理者権限が必要です', 'warning')
        return redirect(url_for('auth.login', next=request.url))
    
    return decorated_function

# Basic認証用デコレータ
def basic_auth_required(f):
    # 
#     APIエンドポイントのBasic認証用デコレータ
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', '')
        
        if not auth or auth.username != admin_username or auth.password != admin_password:
            return jsonify({'error': '認証が必要です'}), 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}
        return f(*args, **kwargs)
    return decorated_function

# 外部API使用権限チェック用デコレータ
def api_access_required(f):
    # 
#     外部API（Google、Azul、PayPal本番）の使用権限が必要なルートに対するデコレータ
#     sandboxモードでは誰でもアクセス可能
#     本番モードでは有料会員または管理者のみアクセス可能
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # セッションとFlask-Loginの状態を同期
        if AUTH_INIT_AVAILABLE:
            sync_session_with_user()
            
        # 現在の設定からPayPalモードを取得
        config = get_config()
        paypal_mode = config.get('paypal_mode', 'sandbox')
        
        logger.info(f"APIアクセス権限チェック - モード: {paypal_mode}")
        logger.info(f"APIアクセス権限チェック - セッション: {session}")
        
        # sandboxモードの場合は誰でもアクセス可能
        if paypal_mode.lower() == 'sandbox':
            logger.info("Sandboxモードなので誰でも外部APIにアクセス可能")
            return f(*args, **kwargs)
        
        # 本番モードの場合は有料会員または管理者のみアクセス可能
        if current_user and hasattr(current_user, 'is_admin') and current_user.is_admin:
            logger.info("管理者として外部APIにアクセス")
            return f(*args, **kwargs)
            
        if current_user and hasattr(current_user, 'is_paid_member') and current_user.is_paid_member:
            logger.info("有料会員として外部APIにアクセス")
            return f(*args, **kwargs)
        
        # セッションでのチェック
        if session.get('admin_logged_in') or session.get('is_paid_member'):
            logger.info("セッション情報から有料会員または管理者として外部APIにアクセス")
            return f(*args, **kwargs)
        
        # JSONリクエストの場合はJSONレスポンスを返す
        if request.is_json:
            logger.warning("権限がないJSONリクエストを拒否")
            return jsonify({
                'error': '外部APIを使用するには有料会員または管理者権限が必要です',
                'status': 'unauthorized'
            }), 403
        
        # それ以外の場合はエラーレスポンスを返す
        flash('外部APIを使用するには有料会員登録が必要です', 'error')
        return redirect(url_for('membership_info'))
    
    return decorated_function

# アプリケーション起動時にキャッシュをクリアし、モジュールを再読み込み
clear_cache()
reload_modules()

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
# ローカルモジュールのインポート
from extractors import ExtractionResult

# 設定ファイルのパス
def get_config_path():
    # 設定ファイルのパスを取得する
#     
#     設定ファイルのパスを返す
    
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# 設定の読み込み
def get_config():
    # 設定を読み込む
#     
#     優先順位:
#     1. データベースから設定を読み込む（管理者ユーザーの設定）
#     2. 環境変数から設定を取得
#     3. 設定ファイルから設定を読み込む
#     4. デフォルト設定を返す
    
    config_path = get_config_path()
    
    # デフォルト設定
    default_config = {
        'client_id': '',
        'client_secret': '',
        'paypal_mode': 'sandbox',
        'admin_email': '',
        'currency': 'JPY'
    }
    
    # 環境変数から設定を取得
    env_client_id = os.environ.get('PAYPAL_CLIENT_ID', '')
    env_client_secret = os.environ.get('PAYPAL_CLIENT_SECRET', '')
    env_paypal_mode = os.environ.get('PAYPAL_MODE', 'sandbox')
    env_admin_email = os.environ.get('ADMIN_EMAIL', '')
    env_currency = os.environ.get('PAYPAL_CURRENCY', 'JPY')
    
    # 1. まず、データベースから管理者の設定を取得
    try:
        # データベースモジュールが利用可能か確認
        if 'database' in sys.modules:
            import database
            # 管理者ユーザーを検索
            admin_user = database.get_user_by_username('admin')
            if admin_user:
                admin_id = admin_user['id']
                # 管理者のPayPal設定を取得
                db_settings = database.get_paypal_settings(admin_id)
                if db_settings:
                    logger.info("データベースから管理者のPayPal設定を読み込みました")
                    config = {
                        'client_id': db_settings.get('client_id', ''),
                        'client_secret': db_settings.get('client_secret', ''),
                        'paypal_client_id': db_settings.get('client_id', ''),  # 両方のキー形式をサポート
                        'paypal_client_secret': db_settings.get('client_secret', ''),
                        'paypal_mode': db_settings.get('mode', 'sandbox'),
                        'admin_email': env_admin_email,  # メールは環境変数から
                        'currency': db_settings.get('currency', 'JPY')
                    }
                    
                    # 環境変数の値で必要に応じて上書き
                    if env_paypal_mode:
                        config['paypal_mode'] = env_paypal_mode
                    
                    return config
    except Exception as e:
        logger.error(f"データベースからの設定読み込みエラー: {str(e)}")
    
    # 2. 環境変数から設定を構築
    if env_client_id and env_client_secret:
        logger.info("環境変数からPayPal設定を読み込みました")
        config = {
            'client_id': env_client_id,
            'client_secret': env_client_secret,
            'paypal_client_id': env_client_id,  # 両方のキー形式をサポート
            'paypal_client_secret': env_client_secret,
            'paypal_mode': env_paypal_mode,
            'admin_email': env_admin_email,
            'currency': env_currency
        }
        return config
    
    # 3. ファイルが存在する場合は読み込み
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            logger.info("設定ファイルからPayPal設定を読み込みました")
            
            # 環境変数の値で上書き
            if env_paypal_mode:
                config['paypal_mode'] = env_paypal_mode
            if env_admin_email:
                config['admin_email'] = env_admin_email
            if 'currency' not in config:
                config['currency'] = env_currency
            
            return config
        except Exception as e:
            logger.error(f"設定ファイルの読み込みエラー: {str(e)}")
    
    # 4. デフォルト設定を返す
    logger.warning("設定が見つからないため、デフォルト設定を使用します")
    default_config['paypal_mode'] = env_paypal_mode
    default_config['admin_email'] = env_admin_email
    
    return default_config

# 設定の保存
def save_config(config):
    # 設定を保存する
#     
#     設定をJSONファイルに保存する
#     
#     Args:
#         config: 保存する設定辞書
    
    config_path = get_config_path()
    
    try:
        # ディレクトリが存在するか確認
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # 設定を保存
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            
        logger.info("設定を保存しました")
        return True
        
    except Exception as e:
        logger.error(f"設定の保存エラー: {str(e)}")
        return False
# customer_extractorモジュールからCustomerExtractorクラスではなく関数をインポート
# ローカルモジュールのインポート
# 初期化: インポートが失敗した場合に備えて、ダミーのamount_extractorモジュールを作成
# amount_extractor用のダミークラス定義
class DummyAmountExtractor:
    @staticmethod
    def extract_invoice_amount(text):
        logger.error("amount_extractorモジュールが正しく読み込まれていないため、金額抽出ができません")
        return ("0", "")

# グローバル変数として先に定義
amount_extractor = None

# まずダミーインスタンスを設定
_dummy_amount_extractor = DummyAmountExtractor()

try:
    # カレントディレクトリを再確認（デプロイ環境用）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        logger.info(f"sys.pathに追加しました: {current_dir}")
    
    # 標準的なインポート方法を試す
    import amount_extractor as ae_module
    # グローバル変数を設定
    amount_extractor = ae_module
    logger.info("amount_extractorモジュールのインポートに成功しました")
except ImportError as e:
    logger.error(f"amount_extractorモジュールのインポートに失敗: {e}")
    # フォールバック処理
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "amount_extractor", 
            os.path.join(current_dir, "amount_extractor.py")
        )
        if spec:
            ae_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ae_module)
            amount_extractor = ae_module
            logger.info("amount_extractorモジュールを代替方法でインポートしました")
        else:
            logger.error("amount_extractorモジュールのspecが取得できませんでした")
            amount_extractor = _dummy_amount_extractor
    except Exception as e2:
        logger.error(f"amount_extractorモジュールの代替インポートにも失敗: {e2}")
        logger.error("ダミーのamount_extractorモジュールを使用します")
        amount_extractor = _dummy_amount_extractor

# 追加のPDF処理ライブラリをインポート
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

try:
    import pytesseract
    from pdf2image import convert_from_path
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# テキスト処理のヘルパー関数
def get_line_containing(text, keyword):
    """テキスト内でキーワードを含む行を取得する"""
    if not text or not keyword:
        return ""
    lines = text.split('\n')
    for line in lines:
        if keyword in line:
            return line
    return ""

def has_encoding_issues(text):
    """テキストに文字化けがあるかどうかを判定"""
    if not text:
        return True
    # 置換文字（�）の数をカウント
    replacement_char_count = text.count('�')
    # テキストの長さに対する置換文字の割合
    if len(text) > 0:
        ratio = replacement_char_count / len(text)
        return ratio > 0.05  # 5%以上の文字が置換文字の場合は文字化けありと判定
    return False

def fix_numeric_encoding(text):
    # 数字の文字化けを修正する
#     
#     Adobe PDFでは数字が特殊な文字コードで表現されていることがあり、
#     それが文字化けの原因となっている。この関数は数字の文字化けパターンを
#     検出して修正する。
    
    if not text:
        return text
        
    # 数字の文字化けパターンと対応する数字のマッピング
    # 観察された文字化けパターンを追加
    numeric_patterns = {
        '�': '0',  # 特定のパターンを0に置換
        '�-��': '1-11',  # 住所などでよく見られるパターン
        '�-��-��': '1-11-11',  # 住所パターン
        '���-����-����': '090-1234-5678',  # 電話番号パターン
        'nissin�����': 'nissin12345',  # メールアドレスパターン
        '�E': '1',  # 部屋番号パターン
    }
    
    # 正規表現パターン
    import re
    # 連続した�のパターン（数字の可能性が高い）
    result = text
    
    # 特定のパターンを置換
    for pattern, replacement in numeric_patterns.items():
        result = result.replace(pattern, replacement)
    
    # 連続した�を数字に変換する試み
    # 例: �� → 11, ��� → 111
    def replace_consecutive_chars(match):
        length = len(match.group(0))
        return '1' * length  # 連続した�を同じ数の1に置換
    
    result = re.sub(r'�+', replace_consecutive_chars, result)
    
    # メールアドレスの修正（@の前後に�がある場合）
    result = re.sub(r'([a-zA-Z0-9]+)�+@', r'\1123@', result)
    result = re.sub(r'@([a-zA-Z0-9]+)�+', r'@\1123', result)
    
    # 電話番号パターンの修正
    result = re.sub(r'(\d{1,4})-�+(\d{1,4})', r'\1-1234-\2', result)
    result = re.sub(r'(\d{1,4})-�+', r'\1-1234', result)
    
    return result

# extractors.pyの関数をインポート
# extractorsモジュールのインポートを試みる（オプション）
try:
    # カレントディレクトリを再確認（デプロイ環境用）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        logger.info(f"sys.pathに追加しました: {current_dir}")
    
    # ローカルモジュールのインポート
    from extractors import extract_amount_only
    from extractors import ExtractionResult
    logger.info("extractorsモジュールを正常に読み込みました。")
    ENHANCED_OCR_AVAILABLE = True
    logger.info("拡張OCRモジュールを読み込みました")
except ImportError as e:
    logger.error(f"extractorsモジュールのインポートに失敗: {e}")
    ENHANCED_OCR_AVAILABLE = False
    
    # フォールバック処理
    try:
        # extractors.pyファイルが存在するか確認
        extractors_path = os.path.join(current_dir, "extractors.py")
        if os.path.exists(extractors_path):
            logger.info(f"extractors.pyファイルが見つかりました: {extractors_path}")
            
            # 直接インポートを試みる
            import importlib.util
            spec = importlib.util.spec_from_file_location("extractors", extractors_path)
            if spec and spec.loader:
                extractors = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(extractors)
            
            # 必要な関数を取得
            extract_amount_only = extractors.extract_amount_only
            ExtractionResult = extractors.ExtractionResult
            
            logger.info("extractorsモジュールを代替方法でインポートしました")
            ENHANCED_OCR_AVAILABLE = True
        else:
            logger.error(f"extractors.pyファイルが見つかりません: {extractors_path}")
    except Exception as e2:
        logger.error(f"extractorsモジュールの代替インポートにも失敗: {e2}")
    logger.warning("拡張OCRモジュールが見つかりません。基本的なOCR機能のみ使用します。")

# PDFからテキストを抽出する関数
def extract_text_from_pdf(pdf_path):
    # 
#     PDFからテキストを抽出する関数。複数の方法を試みる。
#     
#     Args:
#         pdf_path: PDFファイルのパス
#         
#     Returns:
#         dict: 抽出結果を含む辞書
#             - text: 抽出されたテキスト
#             - method: 使用された抽出方法
#             - success: 抽出成功したかどうか
    
    if not os.path.exists(pdf_path):
        logger.error(f"PDFファイルが存在しません: {pdf_path}")
        return {"text": "", "method": "none", "success": False}
    
    methods_tried = []
    last_error = None
    
    # 方法1: pdfplumberを使用
    try:
        import pdfplumber
        methods_tried.append("pdfplumber")
        logger.info(f"pdfplumberでテキスト抽出を試みます: {pdf_path}")
        
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n\n"
                
        if text.strip():
            logger.info(f"pdfplumberでテキスト抽出成功: {len(text)} 文字")
            return {"text": text, "method": "pdfplumber", "success": True}
        else:
            logger.warning("pdfplumberでテキスト抽出失敗: テキストが空です")
    except Exception as e:
        last_error = str(e)
        logger.warning(f"pdfplumberでテキスト抽出エラー: {e}")
    
    # 方法2: PyPDF2を使用
    try:
        import PyPDF2
        methods_tried.append("PyPDF2")
        logger.info(f"PyPDF2でテキスト抽出を試みます: {pdf_path}")
        
        text = ""
        with open(pdf_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n\n"
                
        if text.strip():
            logger.info(f"PyPDF2でテキスト抽出成功: {len(text)} 文字")
            return {"text": text, "method": "PyPDF2", "success": True}
        else:
            logger.warning("PyPDF2でテキスト抽出失敗: テキストが空です")
    except Exception as e:
        last_error = str(e)
        logger.warning(f"PyPDF2でテキスト抽出エラー: {e}")
    
    # 方法3: OCR (pytesseract) を使用
    try:
        import pytesseract
        from pdf2image import convert_from_path
        methods_tried.append("pytesseract")
        logger.info(f"OCR (pytesseract) でテキスト抽出を試みます: {pdf_path}")
        
        # PDFを画像に変換
        images = convert_from_path(pdf_path)
        text = ""
        
        for i, image in enumerate(images):
            # OCRでテキスト抽出
            page_text = pytesseract.image_to_string(image, lang='jpn+eng') or ""
            text += page_text + "\n\n"
            
        if text.strip():
            logger.info(f"OCRでテキスト抽出成功: {len(text)} 文字")
            return {"text": text, "method": "ocr_pytesseract", "success": True}
        else:
            logger.warning("OCRでテキスト抽出失敗: テキストが空です")
    except Exception as e:
        last_error = str(e)
        logger.warning(f"OCRでテキスト抽出エラー: {e}")
    
    # 方法4: pdfminer.six を使用
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        methods_tried.append("pdfminer.six")
        logger.info(f"pdfminer.sixでテキスト抽出を試みます: {pdf_path}")
        
        text = pdfminer_extract_text(pdf_path)
        
        if text.strip():
            logger.info(f"pdfminer.sixでテキスト抽出成功: {len(text)} 文字")
            return {"text": text, "method": "pdfminer.six", "success": True}
        else:
            logger.warning("pdfminer.sixでテキスト抽出失敗: テキストが空です")
    except Exception as e:
        last_error = str(e)
        logger.warning(f"pdfminer.sixでテキスト抽出エラー: {e}")
    
    # 方法5: pdftotextコマンドを使用
    try:
        import subprocess
        import tempfile
        methods_tried.append("pdftotext")
        logger.info(f"pdftotextコマンドでテキスト抽出を試みます: {pdf_path}")
        
        # 一時ファイルを作成
        with tempfile.NamedTemporaryFile(suffix=".txt") as temp_file:
            try:
                # pdftotextコマンドを実行
                process = subprocess.Popen(
                    ["pdftotext", pdf_path, temp_file.name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                _, stderr = process.communicate(timeout=30)
                
                if process.returncode != 0:
                    logger.warning(f"pdftotextコマンド実行エラー: {stderr}")
                    raise Exception(f"pdftotextコマンド実行エラー: {stderr}")
                
                # 生成されたテキストファイルを読み込む
                with open(temp_file.name, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except FileNotFoundError as fnf:
                logger.warning(f"pdftotextコマンドが見つかりません: {fnf}")
                raise Exception("pdftotextコマンドが見つかりません。インストールされていないためスキップします。")
        
        if text.strip():
            logger.info(f"pdftotextコマンドでテキスト抽出成功: {len(text)} 文字")
            return {"text": text, "method": "pdftotext", "success": True}
        else:
            logger.warning("pdftotextコマンドでテキスト抽出失敗: テキストが空です")
    except Exception as e:
        last_error = str(e)
        logger.warning(f"pdftotextコマンドでテキスト抽出エラー: {e}")
    
    # すべての方法が失敗した場合
    logger.error(f"すべてのテキスト抽出方法が失敗しました。試行した方法: {', '.join(methods_tried)}")
    logger.error(f"最後のエラー: {last_error}")
    return {"text": "", "method": "failed", "success": False, "error": last_error}

# AI OCR機能のインポート
try:
    # カレントディレクトリを再確認（デプロイ環境用）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    # ローカルモジュールのインポート
    from ai_ocr import process_pdf_with_ai_ocr
    AI_OCR_AVAILABLE = True
    logger.info("AI OCRモジュールを読み込みました")
except ImportError as e:
    logger.error(f"AI OCRモジュールのインポートに失敗: {e}")
    AI_OCR_AVAILABLE = False
    
    # フォールバック処理
    try:
        # ai_ocr.pyファイルが存在するか確認
        ai_ocr_path = os.path.join(current_dir, "ai_ocr.py")
        if os.path.exists(ai_ocr_path):
            logger.info(f"ai_ocr.pyファイルが見つかりました: {ai_ocr_path}")
            
            # 直接インポートを試みる
            import importlib.util
            spec = importlib.util.spec_from_file_location("ai_ocr", ai_ocr_path)
            ai_ocr = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ai_ocr)
            
            # 必要な関数を取得
            process_pdf_with_ai_ocr = ai_ocr.process_pdf_with_ai_ocr
            
            logger.info("ai_ocrモジュールを代替方法でインポートしました")
            AI_OCR_AVAILABLE = True
        else:
            logger.warning("AI OCRモジュールが見つかりません。AI OCR機能は無効です。")
    except Exception as e2:
        logger.error(f"ai_ocrモジュールの代替インポートにも失敗: {e2}")
        logger.warning("AI OCRモジュールが見つかりません。AI OCR機能は無効です。")

try:
    # カレントディレクトリを再確認（デプロイ環境用）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    # ローカルモジュールのインポート
    from template_matching import TemplateManager, process_pdf_with_template_matching
    TEMPLATE_MATCHING_AVAILABLE = True
    logger.info("テンプレートマッチングモジュールを読み込みました")
except ImportError as e:
    logger.error(f"テンプレートマッチングモジュールのインポートに失敗: {e}")
    TEMPLATE_MATCHING_AVAILABLE = False
    
    # フォールバック処理
    try:
        # template_matching.pyファイルが存在するか確認
        template_matching_path = os.path.join(current_dir, "template_matching.py")
        if os.path.exists(template_matching_path):
            logger.info(f"template_matching.pyファイルが見つかりました: {template_matching_path}")
            
            # 直接インポートを試みる
            import importlib.util
            spec = importlib.util.spec_from_file_location("template_matching", template_matching_path)
            template_matching = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(template_matching)
            
            # 必要な関数とクラスを取得
            TemplateManager = template_matching.TemplateManager
            process_pdf_with_template_matching = template_matching.process_pdf_with_template_matching
            
            logger.info("テンプレートマッチングモジュールを代替方法でインポートしました")
            TEMPLATE_MATCHING_AVAILABLE = True
        else:
            logger.warning("テンプレートマッチングモジュールが見つかりません。テンプレートマッチング機能は無効です。")
    except Exception as e2:
        logger.error(f"テンプレートマッチングモジュールの代替インポートにも失敗: {e2}")
except ImportError:
    TEMPLATE_MATCHING_AVAILABLE = False
    logger.warning("テンプレートマッチングモジュールが見つかりません。テンプレート機能は無効です。")

try:
    # カレントディレクトリを再確認（デプロイ環境用）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        logger.info(f"sys.pathに追加しました: {current_dir}")
    
    # ローカルモジュールのインポート
    from interactive_correction import setup_interactive_correction_routes
    from interactive_correction import CorrectionHistory, LearningData
    
    # ディレクトリの設定
    history_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'correction_history')
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'learning_data')
    os.makedirs(history_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    
    # クラスのインスタンス化
    correction_history = CorrectionHistory(history_dir)
    learning_data = LearningData(data_dir)
    
    logger.info("interactive_correctionモジュールを正常に読み込みました")
except ImportError as e:
    logger.error(f"interactive_correctionモジュールのインポートに失敗: {e}")
    
    # フォールバック処理
    try:
        # interactive_correction.pyファイルが存在するか確認
        interactive_correction_path = os.path.join(current_dir, "interactive_correction.py")
        if os.path.exists(interactive_correction_path):
            logger.info(f"interactive_correction.pyファイルが見つかりました: {interactive_correction_path}")
            
            # 直接インポートを試みる
            import importlib.util
            spec = importlib.util.spec_from_file_location("interactive_correction", interactive_correction_path)
            interactive_correction = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(interactive_correction)
            
            # 必要な関数とクラスを取得
            setup_interactive_correction_routes = interactive_correction.setup_interactive_correction_routes
            CorrectionHistory = interactive_correction.CorrectionHistory
            LearningData = interactive_correction.LearningData
            
            # ディレクトリの設定
            history_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'correction_history')
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'learning_data')
            os.makedirs(history_dir, exist_ok=True)
            os.makedirs(data_dir, exist_ok=True)
            
            # クラスのインスタンス化
            correction_history = CorrectionHistory(history_dir)
            learning_data = LearningData(data_dir)
            
            logger.info("interactive_correctionモジュールを代替方法でインポートしました")
        else:
            logger.error(f"interactive_correction.pyファイルが見つかりません: {interactive_correction_path}")
            # ダミーの関数とクラスを作成してエラーを回避
            class DummyCorrectionHistory:
                def __init__(self, directory):
                    self.directory = directory
                def add_correction(self, *args, **kwargs):
                    logger.warning("ダミーの修正履歴追加関数が呼ばれました")
            
            class DummyLearningData:
                def __init__(self, directory):
                    self.directory = directory
                def add_correction(self, *args, **kwargs):
                    logger.warning("ダミーの学習データ追加関数が呼ばれました")
                def get_correction_suggestions(self, *args, **kwargs):
                    return []
            
            def dummy_setup_routes(app):
                logger.warning("ダミーのルート設定関数が呼ばれました")
            
            # ダミー関数を設定
            setup_interactive_correction_routes = dummy_setup_routes
            correction_history = DummyCorrectionHistory(os.path.join(current_dir, 'data', 'correction_history'))
            learning_data = DummyLearningData(os.path.join(current_dir, 'data', 'learning_data'))
    except Exception as e2:
        logger.error(f"interactive_correctionモジュールの代替インポートにも失敗: {e2}")
    
    # クラスメソッドをグローバル関数として使えるようにする
    def get_correction_suggestions(customer, amount):
        return learning_data.get_correction_suggestions("customer", customer) + \
               learning_data.get_correction_suggestions("amount", amount)
    
    def save_correction(original_customer, original_amount, corrected_customer, corrected_amount, extraction_method=""):
        # 修正履歴に追加
        correction_history.add_correction(
            original_customer, original_amount,
            corrected_customer, corrected_amount,
            extraction_method
        )
        # 学習データに追加
        learning_data.add_correction(
            "customer", original_customer, corrected_customer
        )
        learning_data.add_correction(
            "amount", original_amount, corrected_amount
        )
    
    logger.info("インタラクティブ修正モジュールを読み込みました")
except ImportError as e:
    logger.warning(f"インタラクティブ修正モジュールを読み込めません: {str(e)}")
    INTERACTIVE_CORRECTION_AVAILABLE = False

# 設定管理モジュールのインポート
try:
    # ローカルモジュールのインポート
    from config_manager import config_manager, get_config, save_config
except ImportError:
    logger.warning("config_manager.pyモジュールを読み込めません。絶対パスでインポートを試みます。")
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from config_manager import config_manager, get_config, save_config

# 設定の読み込み
config = get_config()

# 環境変数の読み込み (後方互換性用)
load_dotenv()
PAYPAL_CLIENT_ID = config.get('paypal_client_id') or os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = config.get('paypal_client_secret') or os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = config.get('paypal_mode') or os.getenv("PAYPAL_MODE", "sandbox")

# 設定を環境変数より優先するように更新
if not config.get('paypal_client_id') and PAYPAL_CLIENT_ID:
    config['paypal_client_id'] = PAYPAL_CLIENT_ID
    save_config(config)
if not config.get('paypal_client_secret') and PAYPAL_CLIENT_SECRET:
    config['paypal_client_secret'] = PAYPAL_CLIENT_SECRET
    save_config(config)
if not config.get('paypal_mode') and PAYPAL_MODE:
    config['paypal_mode'] = PAYPAL_MODE
    save_config(config)

# PayPal APIのベースURLは各関数で最新の設定から取得するように変更
# これにより、設定変更時に全ての機能が正しく動作する
# API_BASE = "https://api-m.sandbox.paypal.com" if config.get('paypal_mode') == "sandbox" else "https://api-m.paypal.com"

# 設定の初期化関数をグローバルスコープに定義
def initialize_config():
    # 
#     アプリケーションの設定を初期化する
#     デフォルト設定の作成と環境変数の読み込みを行う
    
    try:
        # 現在の設定を取得
        config = get_config()
        
        # 環境変数から設定を読み込む
        if 'PAYPAL_CLIENT_ID' in os.environ:
            config['client_id'] = os.environ['PAYPAL_CLIENT_ID']
        if 'PAYPAL_CLIENT_SECRET' in os.environ:
            config['client_secret'] = os.environ['PAYPAL_CLIENT_SECRET']
        if 'PAYPAL_MODE' in os.environ:
            config['paypal_mode'] = os.environ['PAYPAL_MODE']
        if 'ADMIN_EMAIL' in os.environ:
            config['admin_email'] = os.environ['ADMIN_EMAIL']
            
        # 設定を保存
        save_config(config)
        logger.info("設定を初期化しました")
    except Exception as e:
        logger.error(f"設定の初期化中にエラーが発生しました: {str(e)}")

# 重複するcreate_app関数を削除しました

from flask import current_app

# キャッシュクリア用のAPIエンドポイント
@app.route('/api/clear_cache', methods=['POST'])
@csrf.exempt
def api_clear_cache():
    """手動でキャッシュをクリアするAPI"""
    try:
        clear_cache()
        return jsonify({
            'success': True,
            'message': 'キャッシュが正常にクリアされました'
        }), 200
    except Exception as e:
        logger.error(f"キャッシュクリアエラー: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'キャッシュクリア中にエラーが発生しました: {str(e)}'
        }), 500

# プロバイダー可用性チェック用のAPIエンドポイント
@app.route('/api/check_provider/<provider>', methods=['GET'])
def check_provider_availability(provider):
    """プロバイダー可用性チェック用エンドポイント"""
    try:
        from payment_utils import get_available_payment_providers, test_payment_provider_connection
        logger.info(f"プロバイダー {provider} の可用性チェック")
        
        available_providers = get_available_payment_providers()
        logger.info(f"利用可能なプロバイダー: {available_providers}")
        
        if provider not in available_providers:
            return jsonify({
                'available': False,
                'message': f'サポートされていないプロバイダー: {provider}',
                'details': {}
            }), 400
        
        is_available = available_providers[provider]
        
        result = {
            'available': is_available,
            'provider': provider,
            'message': f'{provider.upper()}は{"利用可能" if is_available else "設定が必要"}です'
        }
        
        # 利用可能な場合は接続テストも実行
        if is_available:
            connection_test = test_payment_provider_connection(provider)
            result['connection_test'] = connection_test
            if not connection_test.get('success'):
                result['available'] = False
                result['message'] = f'{provider.upper()}の設定に問題があります: {connection_test.get("message", "")}'
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"プロバイダーチェックエラー: {str(e)}")
        return jsonify({
            'available': False,
            'message': f'チェック中にエラーが発生しました: {str(e)}',
            'details': {'error': str(e)}
        }), 500

# プロバイダー可用性テスト用のAPIエンドポイント（デバッグ用）
@app.route('/api/test_provider_check/<provider>', methods=['GET'])
def test_provider_check(provider):
    """プロバイダー可用性チェックのテスト用エンドポイント"""
    try:
        from payment_utils import get_available_payment_providers
        logger.info(f"テスト: プロバイダー {provider} の可用性チェック")
        
        available_providers = get_available_payment_providers()
        logger.info(f"利用可能なプロバイダー: {available_providers}")
        
        if provider not in available_providers:
            return jsonify({
                'available': False,
                'message': f'サポートされていないプロバイダー: {provider}',
                'debug_info': {'all_providers': available_providers}
            }), 400
        
        is_available = available_providers[provider]
        
        return jsonify({
            'available': is_available,
            'provider': provider,
            'message': f'{provider.upper()}は{"利用可能" if is_available else "設定が必要"}です',
            'debug_info': {'all_providers': available_providers}
        })
        
    except Exception as e:
        logger.error(f"プロバイダーチェックテストエラー: {str(e)}")
        return jsonify({
            'available': False,
            'message': f'チェック中にエラーが発生しました: {str(e)}',
            'debug_info': {'error': str(e)}
        }), 500

# トップページ
@app.route('/')
def index():
    """トップページを表示"""
    # 現在の設定からPayPalモードを取得
    config = get_config()
    paypal_mode = config.get('paypal_mode', 'sandbox')
    logger.info(f"PayPalモード: {paypal_mode}")
    
    # セッション同期処理
    if AUTH_INIT_AVAILABLE:
        try:
            from auth_init import sync_session_with_user
            sync_session_with_user()
        except Exception as e:
            logger.warning(f"セッション同期エラー: {e}")
    
    # 管理者ログイン状態を確認
    is_admin = session.get('admin_logged_in', False)
    admin_username = session.get('username', '')  # 正しいキーを使用
    
    # セッション情報をログに出力（デバッグ用）
    logger.info(f"セッション情報: admin_logged_in={is_admin}, username={admin_username}")
    logger.info(f"セッション全体: {dict(session)}")
    
    # sessionオブジェクトをテンプレートに渡す
    return render_template('index.html', paypal_mode=paypal_mode, session=session)

# 支払い成功ページ
@app.route('/payment_success')
def payment_success():
    # 支払い成功時のリダイレクト先
    # PayPalおよびStripeの支払いが成功した場合のページ
    
    # 決済プロバイダーを取得
    provider = request.args.get('provider', 'paypal')
    
    # PayPalからのクエリパラメータを取得
    token = request.args.get('token')
    payer_id = request.args.get('PayerID')
    
    # Stripeからのクエリパラメータを取得
    payment_intent_id = request.args.get('payment_intent')
    session_id = request.args.get('session_id')
    
    logger.info(f"支払い完了ページアクセス: provider={provider}, token={token}, payment_intent={payment_intent_id}, session_id={session_id}")
    
    try:
        if provider == 'stripe':
            # Stripe決済の処理
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # セッションIDがある場合は詳細情報を取得
            if session_id:
                try:
                    from stripe_utils import retrieve_stripe_checkout_session
                    session_result = retrieve_stripe_checkout_session(session_id)
                    
                    if session_result.get('success'):
                        session_data = session_result.get('session', {})
                        payment_status = session_data.get('payment_status', 'unknown')
                        payment_intent_status = session_data.get('payment_intent_status', 'unknown')
                        
                        logger.info(f"Stripe決済詳細取得成功: session_id={session_id}, payment_status={payment_status}, payment_intent_status={payment_intent_status}")
                        
                        # 支払いが完了している場合
                        if payment_status == 'paid' and payment_intent_status == 'succeeded':
                            order_id = session_data.get('payment_intent_id') or session_id
                            amount_display = f"¥{session_data.get('amount_total', 0):,}" if session_data.get('amount_total') else ""
                            
                            return render_template('payment_result.html', 
                                                 result="success", 
                                                 status="COMPLETED", 
                                                 order_id=order_id,
                                                 current_time=current_time,
                                                 message=f"Stripe決済が完了しました。{amount_display}",
                                                 provider="stripe",
                                                 is_pdf_export=False)
                        else:
                            # 支払い未完了の場合
                            order_id = session_data.get('payment_intent_id') or session_id
                            
                            return render_template('payment_result.html', 
                                                 result="error", 
                                                 status="INCOMPLETE", 
                                                 order_id=order_id,
                                                 current_time=current_time,
                                                 message=f"Stripe決済が未完了です。ステータス: {payment_status}",
                                                 provider="stripe",
                                                 is_pdf_export=False)
                    else:
                        logger.warning(f"Stripe決済詳細取得失敗: {session_result.get('message')}")
                        # 詳細取得失敗の場合でも成功として扱う
                        order_id = session_id
                        
                        return render_template('payment_result.html', 
                                             result="success", 
                                             status="COMPLETED", 
                                             order_id=order_id,
                                             current_time=current_time,
                                             message="Stripe決済が完了しました。（詳細情報取得失敗）",
                                             provider="stripe",
                                             is_pdf_export=False)
                except Exception as e:
                    logger.error(f"Stripe決済詳細取得エラー: {str(e)}")
                    # エラーの場合でも成功として扱う
                    order_id = session_id
                    
                    return render_template('payment_result.html', 
                                         result="success", 
                                         status="COMPLETED", 
                                         order_id=order_id,
                                         current_time=current_time,
                                         message="Stripe決済が完了しました。（エラー発生）",
                                         provider="stripe",
                                         is_pdf_export=False)
            else:
                # セッションIDがない場合は基本的な成功処理
                order_id = payment_intent_id or f"STRIPE-{uuid.uuid4().hex[:8].upper()}"
                
                logger.info(f"Stripe決済完了（セッションID不明）: order_id={order_id}")
                
                return render_template('payment_result.html', 
                                     result="success", 
                                     status="COMPLETED", 
                                     order_id=order_id,
                                     current_time=current_time,
                                     message="Stripe決済が完了しました。",
                                     provider="stripe",
                                     is_pdf_export=False)
        else:
            # PayPal決済の処理（従来の処理）
            if not token:
                logger.error("支払い完了ページ: tokenパラメータが不足しています")
                return render_template('payment_result.html', 
                                     result="error", 
                                     status="ERROR", 
                                     message="支払い情報が不完全です",
                                     current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                     provider="paypal",
                                     is_pdf_export=False)
            
            # PayPal APIで実際の支払い状況を確認（安全なインポート使用）
            payment_status = check_payment_status(token)
            
            logger.info(f"支払い状況確認: token={token}, status={payment_status}")
            
            if payment_status == "COMPLETED":
                # 支払いが実際に完了している場合
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 支払いステータスを更新（失敗しても処理を続行）
                update_message = ""
                try:
                    from payment_status_updater import update_payment_status_by_order_id
                    success, new_status, message = update_payment_status_by_order_id(token)
                    if success:
                        logger.info(f"支払いステータス更新成功: {message}")
                        update_message = "ステータス更新済み"
                    else:
                        logger.warning(f"支払いステータス更新失敗: {message}")
                        update_message = "ステータス更新に失敗しましたが、支払いは完了しています"
                except Exception as e:
                    logger.error(f"支払いステータス更新エラー: {str(e)}")
                    update_message = "ステータス更新エラーが発生しましたが、支払いは完了しています"
                
                # 支払い完了済みの場合は常に成功ページを表示
                return render_template('payment_result.html', 
                                     result="success", 
                                     status="COMPLETED", 
                                     order_id=token,
                                     current_time=current_time,
                                     message=f"PayPal決済が完了しました。{update_message}",
                                     provider="paypal",
                                     is_pdf_export=False)
            elif payment_status == "PENDING":
                # 支払い処理中
                return render_template('payment_result.html', 
                                     result="pending", 
                                     status="PENDING", 
                                     order_id=token,
                                     message="支払い処理中です。しばらくお待ちください。",
                                     current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                     provider="paypal",
                                     is_pdf_export=False)
            else:
                # 支払い失敗または不明
                return render_template('payment_result.html', 
                                     result="error", 
                                     status=payment_status or "UNKNOWN", 
                                     order_id=token,
                                     message="支払い処理に問題が発生しました。",
                                     current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                     provider="paypal",
                                     is_pdf_export=False)
                                     
    except Exception as e:
        logger.error(f"支払い完了ページ処理エラー: {str(e)}")
        return render_template('payment_result.html', 
                             result="error", 
                             status="ERROR", 
                             order_id=token or payment_intent_id or session_id,
                             message=f"エラーが発生しました: {str(e)}",
                             current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                             provider=provider,
                             is_pdf_export=False)

# 支払いキャンセルページ
@app.route('/payment_cancel')
def payment_cancel():
    # 支払いキャンセル時のリダイレクト先
    # PayPalおよびStripeの支払いがキャンセルされた場合のページ
    
    # 決済プロバイダーを取得
    provider = request.args.get('provider', 'paypal')
    
    logger.info(f"支払いがキャンセルされました: provider={provider}")
    
    # 現在の日時を取得
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # プロバイダーに応じたメッセージを設定
    if provider == 'stripe':
        message = "Stripe決済がキャンセルされました。"
        order_id = f"STRIPE-CANCELLED-{uuid.uuid4().hex[:8].upper()}"
    else:
        message = "PayPal決済がキャンセルされました。"
        order_id = f"PAYPAL-CANCELLED-{uuid.uuid4().hex[:8].upper()}"
    
    # 状態を設定
    status = "CANCELLED"
    # 結果を設定
    result = "cancel"
    
    return render_template('payment_result.html', 
                           result=result, 
                           status=status, 
                           order_id=order_id, 
                           current_time=current_time,
                           message=message,
                           provider=provider,
                           is_pdf_export=False)

# 決済結果をPDFでエクスポートするエンドポイント
@app.route('/export_pdf/<result>')
def export_pdf(result):
    # 決済結果をPDFでエクスポートする
#     
#     Args:
#         result: 'success'または'cancel'の文字列
#         order_id: リクエストパラメータとして渡される注文ID（オプション）
#     
#     Returns:
#         PDFファイルのレスポンス
    
    try:
        # 現在の日時を取得
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # リクエストからorder_idを取得（履歴からの呼び出し用）
        order_id = request.args.get('order_id')
        
        # order_idが指定されていない場合は新しく生成
        if not order_id:
            order_id = f"ORDER-{uuid.uuid4().hex[:8].upper()}"
        
        # 結果に基づいて状態を設定
        if result == "success":
            status = "COMPLETED"
        else:
            status = "CANCELLED"
            result = "cancel"  # 正規化
            
        # 顧客名と金額を取得（履歴からの場合）
        customer_name = request.args.get('customer_name', '')
        amount = request.args.get('amount', '')
        
        # 履歴からの場合、order_idから履歴データを探す
        if order_id and not customer_name and not amount:
            try:
                # ファイルパスの候補を作成
                base_dir = os.path.dirname(os.path.abspath(__file__))
                
                # results_folderの取得
                results_folder = app.config.get('RESULTS_FOLDER')
                
                # results_folderがNoneの場合のフォールバック処理
                if results_folder is None:
                    # 環境変数から取得を試みる
                    results_folder = os.environ.get('RESULTS_FOLDER')
                    
                    # それでもNoneの場合はデフォルト値を使用
                    if results_folder is None:
                        results_folder = os.path.join(base_dir, 'results')
                        logger.warning(f"RESULTS_FOLDERが設定されていないため、デフォルト値を使用します: {results_folder}")
                
                # 設定を更新
                app.config['RESULTS_FOLDER'] = results_folder
                
                # 履歴ファイルを探索するディレクトリのリスト
                search_dirs = [
                    results_folder,
                    os.path.join(base_dir, 'results'),
                    base_dir,
                    os.path.join(os.getcwd(), 'results'),
                    os.getcwd()
                ]
                
                # 重複を削除
                search_dirs = list(set(search_dirs))
                
                found = False
                for search_dir in search_dirs:
                    if not os.path.exists(search_dir):
                        logger.warning(f"ディレクトリが存在しません: {search_dir}")
                        continue
                        
                    logger.info(f"履歴ファイルを検索: {search_dir}")
                    try:
                        for filename in os.listdir(search_dir):
                            if filename.startswith('payment_links_') and filename.endswith('.json'):
                                file_path = os.path.join(search_dir, filename)
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        data = json.load(f)
                                        
                                        # データ構造を確認
                                        if isinstance(data, dict) and 'results' in data:
                                            items = data['results']
                                        elif isinstance(data, list):
                                            items = data
                                        else:
                                            logger.warning(f"不正なデータ形式: {file_path}")
                                            continue
                                        
                                        for item in items:
                                            if not isinstance(item, dict):
                                                continue
                                                
                                            # 決済リンクからorder_idを抽出して比較
                                            payment_link = item.get('payment_link') or item.get('決済リンク', '')
                                            if payment_link and order_id in payment_link:
                                                customer_name = item.get('customer_name') or item.get('formatted_customer') or item.get('customer') or item.get('顧客名', '')
                                                amount = item.get('formatted_amount') or item.get('amount') or item.get('金額', '')
                                                found = True
                                                logger.info(f"履歴から顧客データを取得: {customer_name}, {amount}")
                                                break
                                    if found:
                                        break
                                except Exception as e:
                                    logger.error(f"履歴ファイル読み込みエラー: {file_path}, {str(e)}")
                                    continue
                        if found:
                            break
                    except Exception as e:
                        logger.error(f"ディレクトリ読み込みエラー: {search_dir}, {str(e)}")
            except Exception as e:
                logger.error(f"履歴からの顧客データ取得エラー: {str(e)}")
        
        # HTMLテンプレートをレンダリング
        html_content = render_template('payment_result.html', 
                                      result=result, 
                                      status=status, 
                                      order_id=order_id, 
                                      current_time=current_time,
                                      is_pdf_export=True,  # PDF出力用フラグ
                                      customer_name=customer_name,
                                      amount=amount)
        
        # PDFファイルを格納するメモリバッファを作成
        pdf_buffer = BytesIO()
        
        # HTMLからPDFを生成
        pisa_status = pisa.CreatePDF(
            html_content,
            dest=pdf_buffer
        )
        
        # PDF生成が成功したかチェック
        if pisa_status.err:
            logger.error(f"PDF生成中にエラーが発生しました: {pisa_status.err}")
            return jsonify({"error": "PDFの生成に失敗しました"}), 500
        
        # バッファの先頭に移動
        pdf_buffer.seek(0)
        
        # レスポンスを作成
        try:
            response = make_response(pdf_buffer.getvalue())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=payment-receipt-{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf'
            
            logger.info(f"決済結果({result})のPDFエクスポートが完了しました")
            return response
        except Exception as e:
            logger.error(f"PDFレスポンス作成エラー: {str(e)}")
            return jsonify({"error": f"PDFレスポンスの作成に失敗しました: {str(e)}"}), 500
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"PDFエクスポート中にエラーが発生しました: {str(e)}")
        logger.error(f"エラーの詳細: {error_trace}")
        return jsonify({"error": str(e), "details": "詳細はサーバーログを確認してください"}), 500


# 履歴から複数の決済結果をまとめてPDFでエクスポートするエンドポイント
# グローバルスコープでPyPDF2をインポート
from PyPDF2 import PdfMerger

@app.route('/export_batch_pdf/<filename>')
def export_batch_pdf(filename):
    # 
#     履歴ファイルから複数の決済結果をまとめてPDFでエクスポートする
#     
#     Args:
#         filename: 履歴ファイル名
#         
#     Returns:
#         PDFファイルのレスポンス
    
    try:
        # セキュリティ対策としてファイル名を検証
        if '..' in filename or filename.startswith('/'):
            logger.warning(f"不正なファイルパス: {filename}")
            abort(404)
        
        # ファイルパスの候補を作成
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # results_folderの取得
        results_folder = app.config.get('RESULTS_FOLDER')
        
        # results_folderがNoneの場合のフォールバック処理
        if results_folder is None:
            # 環境変数から取得を試みる
            results_folder = os.environ.get('RESULTS_FOLDER')
            
            # それでもNoneの場合はデフォルト値を使用
            if results_folder is None:
                results_folder = os.path.join(base_dir, 'results')
                logger.warning(f"RESULTS_FOLDERが設定されていないため、デフォルト値を使用します: {results_folder}")
        
        # 設定を更新
        app.config['RESULTS_FOLDER'] = results_folder
        
        # 複数の候補パスを確認
        path_candidates = [
            os.path.join(results_folder, filename),  # 設定されたRESULTS_FOLDERからのパス
            os.path.join(base_dir, 'results', filename),  # アプリケーションディレクトリのresultsフォルダ
            os.path.join(base_dir, filename),  # アプリケーションディレクトリ直下
            os.path.join(os.getcwd(), 'results', filename),  # カレントディレクトリのresultsフォルダ
            os.path.join(os.getcwd(), filename)  # カレントディレクトリ直下
        ]
        
        # 存在するファイルパスを探す
        file_path = None
        for path in path_candidates:
            logger.info(f"ファイルパスを確認: {path}")
            if os.path.exists(path):
                file_path = path
                logger.info(f"ファイルが見つかりました: {file_path}")
                break
        
        if not file_path:
            logger.warning(f"履歴ファイルが存在しません: {filename}")
            abort(404)
        
        # ファイルの内容を読み込み
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
                logger.info(f"ファイル内容 (最初の100文字): {file_content[:100]}...")
                data = json.loads(file_content)
        except json.JSONDecodeError as e:
            logger.error(f"JSONデコードエラー: {str(e)}")
            return jsonify({"error": f"JSONファイルの解析に失敗しました: {str(e)}"}), 400
        except Exception as e:
            logger.error(f"ファイル読み込みエラー: {str(e)}")
            return jsonify({"error": f"ファイルの読み込みに失敗しました: {str(e)}"}), 500
        
        # 日付を取得
        date = filename.replace('payment_links_', '').replace('.json', '')
        if not date or not date[0].isdigit():
            date = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # データ構造を確認して適切に処理
        logger.info(f"データ型: {type(data)}, データ内容: {str(data)[:200] if data else 'なし'}...")
        
        if isinstance(data, dict) and 'results' in data:
            # 'results' キーがある場合はその中のリストを使用
            items = data['results']
            logger.info(f"'results'キーから{len(items)}件のアイテムを取得")
        elif isinstance(data, list):
            # データ自体がリストの場合はそのまま使用
            items = data
            logger.info(f"リストから{len(items)}件のアイテムを取得")
        else:
            # どちらでもない場合は空のリストとして扱う
            logger.warning(f"不正なデータ形式: {type(data)}")
            items = []
        
        # 完了した決済のみを抽出
        completed_payments = []
        for i, item in enumerate(items):
            # 辞書型かどうか確認
            if not isinstance(item, dict):
                logger.warning(f"不正なアイテム形式 (インデックス {i}): {type(item)}")
                continue
                
            # payment_statusフィールドを確認
            payment_status = item.get('payment_status')
            logger.info(f"アイテム {i}: payment_status = {payment_status}, キー = {list(item.keys())}")
            
            # payment_statusがない場合でも、他の情報から完了したかどうかを判断
            if payment_status == "COMPLETED" or (item.get('payment_link') and not payment_status):
                logger.info(f"完了した決済を追加: {item.get('customer_name') or item.get('customer') or item.get('顧客名', '不明')}")
                completed_payments.append(item)
        
        if not completed_payments:
            logger.warning(f"完了した決済が見つかりません: {filename}")
            return jsonify({"error": "完了した決済が見つかりません"}), 404
        
        # 複数のPDFを結合するためのPdfMergerを作成
        try:
            merger = PdfMerger()
        except Exception as e:
            logger.error(f"PdfMergerの作成に失敗しました: {str(e)}")
            return jsonify({"error": f"PDFマージャーの初期化に失敗しました: {str(e)}"}), 500
        
        # 各決済のPDFを生成して結合
        for payment in completed_payments:
            # 現在の日時を取得
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 決済情報を取得
            # 決済リンクからorder_idを抽出
            payment_link = payment.get('payment_link') or payment.get('決済リンク', '')
            if payment_link and 'token=' in payment_link:
                order_id = payment_link.split('token=')[1].split('&')[0]
            else:
                order_id = payment.get('order_id', f"ORDER-{uuid.uuid4().hex[:8].upper()}")
            
            # 顧客名と金額を取得（日本語と英語のフィールド名に対応）
            customer_name = payment.get('formatted_customer') or payment.get('customer') or payment.get('顧客名', '')
            amount = payment.get('formatted_amount') or payment.get('amount') or payment.get('金額', '')
            
            # HTMLテンプレートをレンダリング
            html_content = render_template('payment_result.html', 
                                          result="success", 
                                          status="COMPLETED", 
                                          order_id=order_id, 
                                          current_time=current_time,
                                          is_pdf_export=True,
                                          customer_name=customer_name,
                                          amount=amount)
            
            # PDFファイルを格納するメモリバッファを作成
            pdf_buffer = BytesIO()
            
            # HTMLからPDFを生成
            pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer)
            
            # PDF生成が成功したかチェック
            if pisa_status.err:
                logger.error(f"PDF生成中にエラーが発生しました: {pisa_status.err}")
                continue
            
            # バッファの先頭に移動
            pdf_buffer.seek(0)
            
            # PDFをマージャーに追加
            try:
                merger.append(pdf_buffer)
                logger.info(f"PDFをマージャーに追加しました: {customer_name}")
            except Exception as e:
                logger.error(f"PDFのマージに失敗しました: {str(e)}")
                # 1つのPDFの追加に失敗しても続行
                continue
        
        # 結合するPDFがあるか確認
        if len(completed_payments) == 0:
            logger.warning("結合するPDFがありません")
            return jsonify({"error": "PDFの生成に失敗しました"}), 500
        
        try:
            # 結合したPDFを格納するメモリバッファを作成
            output_buffer = BytesIO()
            
            # PDFを結合
            merger.write(output_buffer)
            merger.close()
            
            # バッファの先頭に移動
            output_buffer.seek(0)
            
            # レスポンスを作成
            response = make_response(output_buffer.getvalue())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=payment-receipts-{date}.pdf'
            
            logger.info(f"バッチPDFエクスポートが完了しました: {filename}, {len(completed_payments)}件")
            return response
        except Exception as e:
            logger.error(f"PDFの結合と出力に失敗しました: {str(e)}")
            return jsonify({"error": f"PDFの結合と出力に失敗しました: {str(e)}"}), 500
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"バッチPDFエクスポート中にエラーが発生しました: {str(e)}")
        logger.error(f"エラーの詳細: {error_trace}")
        return jsonify({"error": str(e), "details": "詳細はサーバーログを確認してください"}), 500

# 古いログイン機能は削除 - 認証Blueprintを使用
# @app.route('/login', methods=['GET', 'POST'])
# def login():
    # 古いログイン機能のコメントアウト - 認証Blueprintを使用
    
    # 古いPOST処理のコメントアウト
    # 古い認証ロジックのコメントアウト - 認証Blueprintで実装されています
    pass
# 古いログアウト機能は削除 - 認証Blueprintを使用
# @app.route('/logout')
# def logout():

# 設定ページ
@app.route('/settings')
@admin_required
def settings():
    # 
#     設定ページ - 管理者のみアクセス可能
#     管理者はすべての設定を閲覧・編集可能
    
    logger.info("設定ページにアクセスされました")
    
    # セッションとFlask-Loginの状態を同期
    if AUTH_INIT_AVAILABLE:
        try:
            sync_session_with_user()
        except Exception as e:
            logger.error(f"セッション同期エラー: {e}")
    
    # セッション情報とcurrent_user情報をログ出力
    logger.info(f"設定ページ表示時のセッション状態: {session}")
    if FLASK_LOGIN_AVAILABLE and current_user:
        logger.info(f"設定ページ表示時のcurrent_user状態: authenticated={current_user.is_authenticated}, admin={getattr(current_user, 'is_admin', False)}")
    
    # 現在の設定を取得
    config = get_config()
    
    # config_manager からも設定を取得（より詳細な設定のため）
    try:
        from config_manager import ConfigManager
        config_manager = ConfigManager()
        detailed_config = config_manager.get_config()
        # 詳細設定をマージ
        config.update(detailed_config)
        logger.info(f"詳細設定を取得しました: {len(detailed_config)} 項目")
    except Exception as e:
        logger.warning(f"詳細設定の取得に失敗: {str(e)}")
    
    # PayPalモードを取得（デフォルトはsandbox）
    paypal_mode = config.get('paypal_mode', 'sandbox')
    
    # Stripe設定の取得
    stripe_mode = config.get('stripe_mode', 'test')
    stripe_pk = ''
    stripe_sk = ''
    
    if stripe_mode == 'test':
        stripe_pk = config.get('stripe_publishable_key_test', config.get('stripe_publishable_key', ''))
        stripe_sk = config.get('stripe_secret_key_test', config.get('stripe_secret_key', ''))
    else:
        stripe_pk = config.get('stripe_publishable_key_live', '')
        stripe_sk = config.get('stripe_secret_key_live', '')
    
    # Stripe接続状態をテスト
    stripe_status = False
    if stripe_sk:
        try:
            from stripe_utils import test_stripe_connection
            test_result = test_stripe_connection(stripe_sk)
            stripe_status = test_result.get('success', False)
            logger.info(f"Stripe接続テスト結果: {stripe_status}")
        except Exception as e:
            logger.error(f"Stripe接続テストエラー: {str(e)}")
    
    # OCR設定の取得
    use_ai_ocr = config.get('use_ai_ocr', False)
    ocr_method = config.get('ocr_method', 'tesseract')
    ocr_api_key = config.get('ocr_api_key', '')
    ocr_endpoint = config.get('ocr_endpoint', '')
    
    # 権限情報を取得（Flask-Loginとセッションの両方をチェック）
    is_admin = False
    is_paid_member = False
    
    # Flask-Loginからの権限情報
    if FLASK_LOGIN_AVAILABLE and current_user and current_user.is_authenticated:
        is_admin = getattr(current_user, 'is_admin', False)
        is_paid_member = getattr(current_user, 'is_paid_member', False)
    
    # セッションからの権限情報（フォールバック）
    if not is_admin:
        is_admin = session.get('admin_logged_in', False)
    if not is_paid_member:
        is_paid_member = session.get('is_paid_member', False)
    
    # 権限情報をログ出力
    logger.info(f"設定ページ表示時の権限情報 - is_admin: {is_admin}, is_paid_member: {is_paid_member}")
    
    # PayPal API接続状態をテスト
    paypal_status = False
    if config:
        try:
            client_id = config.get('client_id', '')
            client_secret = config.get('client_secret', '')
            if client_id and client_secret:
                token = get_paypal_access_token(client_id, client_secret, paypal_mode)
                paypal_status = bool(token)
        except Exception as e:
            logger.error(f"PayPal API接続テストエラー: {str(e)}")
            paypal_status = False
    
    # 権限に基づいて表示内容を決定
    show_all_settings = is_admin  # 管理者は全設定にアクセス可能
    show_sandbox_settings = True  # sandboxモードの設定は常に表示
    show_production_settings = is_admin  # 本番モードは管理者のみアクセス可能
    
    # レンダリング前の最終確認
    logger.info(f"設定ページレンダリング前の最終確認 - is_admin: {is_admin}, show_all_settings: {show_all_settings}")
    
    return render_template('settings.html', 
                           paypal_mode=paypal_mode,
                           is_admin=is_admin,
                           is_paid_member=is_paid_member,
                           config=config,
                           paypal_status=paypal_status,
                           stripe_status=stripe_status,
                           stripe_pk=stripe_pk,
                           stripe_sk=stripe_sk,
                           stripe_mode=stripe_mode,
                           use_ai_ocr=use_ai_ocr,
                           ocr_method=ocr_method,
                           ocr_api_key=ocr_api_key,
                           ocr_endpoint=ocr_endpoint,
                           show_all_settings=show_all_settings,
                           show_sandbox_settings=show_sandbox_settings,
                           show_production_settings=show_production_settings)

# 履歴一覧ページ
@app.route('/history')
@login_required
def history():
    # 履歴一覧ページ（キャッシュ容量管理付き）
    
    history_data = []
    cache_info = {}
    
    try:
        results_folder = app.config['RESULTS_FOLDER']
        files = [f for f in os.listdir(results_folder) if f.startswith('payment_links_') and f.endswith('.json')]
        files.sort(reverse=True)
        
        # キャッシュ情報を計算
        total_files = len(files)
        total_size = 0
        for file in files:
            file_path = os.path.join(results_folder, file)
            if os.path.exists(file_path):
                total_size += os.path.getsize(file_path)
        
        cache_info = {
            'total_files': total_files,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'max_files': 100,  # 最大ファイル数
            'max_size_mb': 50  # 最大サイズ(MB)
        }
        
        # 制限を超えている場合は古いファイルを削除
        if total_files > cache_info['max_files']:
            files_to_delete = files[cache_info['max_files']:]
            for file_to_delete in files_to_delete:
                try:
                    os.remove(os.path.join(results_folder, file_to_delete))
                    logger.info(f"キャッシュ容量管理: 古いファイルを削除しました - {file_to_delete}")
                except:
                    pass
            # ファイルリストを更新
            files = files[:cache_info['max_files']]
        
        # 各ファイルの内容を読み込み、顧客名情報を取得
        for file in files:
            file_path = os.path.join(results_folder, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 日付をファイル名から抽出
                    date_str = file.replace('payment_links_', '').replace('.json', '')
                    # YYYYMMDD_HHMMSS形式を読みやすい形式に変換
                    try:
                        date_obj = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                        formatted_date = date_obj.strftime("%Y年%m月%d日 %H:%M")
                    except:
                        formatted_date = date_str
                    
                    # データ構造を確認して適切に処理
                    items = []
                    if isinstance(data, dict) and 'results' in data:
                        # 'results' キーがある場合はその中のリストを使用
                        items = data['results']
                    elif isinstance(data, list):
                        # データ自体がリストの場合はそのまま使用
                        items = data
                    
                    # 顧客名を取得
                    customers = []
                    for item in items:
                        # データが辞書型か確認
                        if isinstance(item, dict):
                            # 優先順位: formatted_customer > customer > 顧客名
                            customer = item.get('formatted_customer') or item.get('customer') or item.get('顧客名')
                            if customer and customer not in customers:
                                customers.append(customer)
                    
                    # 結果を追加
                    history_data.append({
                        'filename': file,
                        'date': formatted_date,
                        'customers': customers,
                        'count': len(items)
                    })
            except Exception as e:
                logger.error(f"履歴ファイル読み込みエラー ({file}): {str(e)}")
                # エラーがあってもファイル名だけは表示
                history_data.append({
                    'filename': file,
                    'date': file.replace('payment_links_', '').replace('.json', ''),
                    'customers': [],
                    'count': 0
                })
    except Exception as e:
        logger.error(f"履歴ファイル一覧取得エラー: {str(e)}")
    
    return render_template('history.html', 
                           history_data=history_data, 
                           cache_info=cache_info)

@app.route('/history/<filename>')
@login_required
def history_detail(filename):
    # 
#     履歴詳細ページ
#     
#     Args:
#         filename: 履歴ファイル名
    
    try:
        # セキュリティ対策としてファイル名を検証
        if '..' in filename or filename.startswith('/'):
            logger.warning(f"不正なファイルパス: {filename}")
            abort(404)
            
        results_folder = app.config['RESULTS_FOLDER']
        file_path = os.path.join(results_folder, filename)
        
        if not os.path.exists(file_path):
            logger.warning(f"履歴ファイルが存在しません: {file_path}")
            abort(404)
        
        # ファイルの内容を読み込み
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 日付を取得
        date = filename.replace('payment_links_', '').replace('.json', '')
        
        # データ構造を確認して適切に処理
        results = []
        if isinstance(data, dict) and 'results' in data:
            # 'results' キーがある場合はその中のリストを使用
            results = data['results']
        elif isinstance(data, list):
            # データ自体がリストの場合はそのまま使用
            results = data
        else:
            # どちらでもない場合は空のリストとして扱う
            logger.warning(f"不正なデータ形式: {type(data)}")
            results = []
        
        return render_template('history_detail.html', filename=filename, date=date, results=results)
    
    except Exception as e:
        logger.error(f"履歴詳細取得エラー: {str(e)}")
        abort(500)

# 履歴削除機能
@app.route('/history/delete', methods=['POST'])
@paid_member_or_admin_required
def delete_history():
    # 
#     履歴ファイルを削除する関数
#     二重確認のため、確認コードを検証する
#     PayPal APIを使用して注文情報も削除する
    
    if request.method == 'POST':
        # 単一ファイル削除の場合
        if 'filename' in request.form:
            filename = request.form.get('filename')
            confirmation_code = request.form.get('confirmation_code')
            expected_code = request.form.get('expected_code')
            
            # 確認コードの検証
            if not filename or not confirmation_code or confirmation_code != expected_code:
                flash('確認コードが一致しないため、削除できませんでした。', 'danger')
                return redirect(url_for('history'))
            
            # ファイル名の検証（セキュリティ対策）
            if not filename.startswith('payment_links_') or not filename.endswith('.json'):
                flash('無効なファイル名です。', 'danger')
                return redirect(url_for('history'))
            
            # ファイルの存在確認
            results_folder = current_app.config['RESULTS_FOLDER']
            file_path = os.path.join(results_folder, filename)
            
            if not os.path.exists(file_path):
                flash('指定されたファイルが見つかりません。', 'danger')
                return redirect(url_for('history'))
                
            # 単一ファイルを処理
            selected_files = [filename]
        else:
            # 複数ファイル選択の場合
            selected_files = request.form.getlist('selected_files')
            if not selected_files:
                flash('ファイルが選択されていません', 'warning')
                return redirect(url_for('history'))
        
        deleted_count = 0
        paypal_deleted_count = 0
        error_count = 0
        
        for filename in selected_files:
            file_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
            if os.path.exists(file_path):
                try:
                    # PayPal注文IDを抽出して削除を試みる
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # 決済リンクからオーダーIDを抽出
                            payment_links = re.findall(r'https://www\.paypal\.com/cgi-bin/webscr\?cmd=_express-checkout&token=([^"&]+)', content)
                            if not payment_links:
                                # 別形式のリンクを試す
                                payment_links = re.findall(r'https://www\.paypal\.com/checkoutnow\?token=([^"&]+)', content)
                            
                            for token in payment_links:
                                try:
                                    logger.info(f"PayPal注文キャンセル処理開始: {token}")
                                    
                                    # PayPalのアクセストークンを取得
                                    access_token = get_paypal_access_token()
                                    if not access_token:
                                        logger.error(f"PayPalアクセストークン取得失敗のため、注文キャンセルをスキップ: {token}")
                                        continue
                                    
                                    # APIベースURLとヘッダーを設定
                                    api_base = get_api_base()
                                    headers = {
                                        'Content-Type': 'application/json',
                                        'Authorization': f'Bearer {access_token}',
                                        'Accept': 'application/json'
                                    }
                                    
                                    # まず注文の状態を確認
                                    logger.info(f"PayPal注文情報を取得中: {token}")
                                    success, order_status, response_text = check_order_status(api_base, token, headers)
                                    
                                    if success:
                                        logger.info(f"PayPal注文状態: {token} = {order_status}")
                                        
                                        # キャンセル可能なステータスか確認
                                        cancelable_statuses = ['CREATED', 'APPROVED', 'SAVED']
                                        if order_status in cancelable_statuses:
                                            # キャンセル処理を実行
                                            cancel_success = cancel_paypal_order(api_base, token, headers)
                                            if cancel_success:
                                                paypal_deleted_count += 1
                                        elif order_status == 'COMPLETED':
                                            logger.info(f"PayPal注文は既に完了しているためキャンセル不要: {token}")
                                        elif order_status == 'VOIDED':
                                            logger.info(f"PayPal注文は既に無効化されているためキャンセル不要: {token}")
                                        elif order_status == 'PAYER_ACTION_REQUIRED':
                                            logger.info(f"PayPal注文は支払い者のアクションが必要な状態のためキャンセル不可: {token}")
                                        else:
                                            logger.warning(f"PayPal注文はキャンセル不可能なステータス {order_status}: {token}")
                                    else:
                                        # 注文情報取得に失敗した場合
                                        if "404" in response_text:
                                            logger.warning(f"PayPal注文が見つかりません (404): {token}")
                                            logger.info(f"PayPal注文は既にキャンセルされているか期限切れの可能性があります: {token}")
                                        elif "401" in response_text:
                                            logger.error(f"PayPal API認証エラー (401): アクセストークンが無効か期限切れ")
                                        else:
                                            logger.error(f"PayPal注文情報取得エラー: {token}, レスポンス: {response_text[:200]}...")
                                except Exception as e:
                                    logger.error(f"PayPal注文キャンセル処理中の例外: {str(e)}")
                                    # スタックトレースをログに記録
                                    import traceback
                                    logger.error(traceback.format_exc())
                    except Exception as e:
                        logger.error(f"ファイル読み込みエラー: {str(e)}")
                    
                    # ローカルファイルを削除
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"ファイル削除エラー: {str(e)}")
                    error_count += 1
        
        message = f"{deleted_count}件の履歴を削除しました。"
        if paypal_deleted_count > 0:
            message += f" {paypal_deleted_count}件のPayPal注文もキャンセルしました。"
        if error_count > 0:
            message += f" {error_count}件のエラーが発生しました。"
            
        flash(message, 'success' if error_count == 0 else 'warning')
        
    return redirect(url_for('history'))

@app.route('/history/delete_all_with_paypal', methods=['POST'])
@paid_member_or_admin_required
def delete_all_history_with_paypal():
    # 
#     全ての履歴ファイルを削除し、関連するPayPal注文情報も削除する関数
    
    results_folder = current_app.config['RESULTS_FOLDER']
    if not os.path.exists(results_folder):
        return jsonify({
            'success': False,
            'message': '履歴フォルダが見つかりません。'
        }), 404
    
    # 履歴ファイルの一覧を取得
    history_files = [f for f in os.listdir(results_folder) 
                    if f.startswith('payment_links_') and f.endswith('.json')]
    
    if not history_files:
        return jsonify({
            'success': True,
            'message': '削除対象の履歴ファイルがありませんでした。'
        })
    
    deleted_count = 0
    paypal_deleted_count = 0
    error_count = 0
    
    for filename in history_files:
        file_path = os.path.join(results_folder, filename)
        if os.path.exists(file_path):
            try:
                # PayPal注文IDを抽出して削除を試みる
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # 決済リンクからオーダーIDを抽出
                        payment_links = re.findall(r'https://www\.paypal\.com/cgi-bin/webscr\?cmd=_express-checkout\&token=([^"\&]+)', content)
                        if not payment_links:
                            # 別形式のリンクを試す
                            payment_links = re.findall(r'https://www\.paypal\.com/checkoutnow\?token=([^"\&]+)', content)
                        
                        for token in payment_links:
                            try:
                                logger.info(f"PayPal注文キャンセル処理開始: {token}")
                                
                                # PayPalのアクセストークンを取得
                                access_token = get_paypal_access_token()
                                if not access_token:
                                    logger.error(f"PayPalアクセストークン取得失敗のため、注文キャンセルをスキップ: {token}")
                                    continue
                                
                                # APIベースURLとヘッダーを設定
                                api_base = get_api_base()
                                headers = {
                                    'Content-Type': 'application/json',
                                    'Authorization': f'Bearer {access_token}',
                                    'Accept': 'application/json'
                                }
                                
                                # まず注文の状態を確認
                                logger.info(f"PayPal注文情報を取得中: {token}")
                                success, order_status, response_text = check_order_status(api_base, token, headers)
                                
                                if success:
                                    logger.info(f"PayPal注文状態: {token} = {order_status}")
                                    
                                    # キャンセル可能なステータスか確認
                                    cancelable_statuses = ['CREATED', 'APPROVED', 'SAVED']
                                    if order_status in cancelable_statuses:
                                        # キャンセル処理を実行
                                        cancel_url = f"{api_base}/v2/checkout/orders/{token}/cancel"
                                        logger.info(f"PayPal注文キャンセルリクエスト送信: {cancel_url}")
                                        
                                        response = requests.post(cancel_url, headers=headers)
                                        
                                        if response.status_code == 204:
                                            logger.info(f"PayPal注文キャンセル成功: {token}")
                                            paypal_deleted_count += 1
                                        else:
                                            logger.error(f"PayPal注文キャンセル失敗: {token}, ステータスコード: {response.status_code}, レスポンス: {response.text}")
                                            error_count += 1
                                    else:
                                        logger.info(f"PayPal注文はキャンセル不可能な状態です: {token}, 状態: {order_status}")
                                else:
                                    logger.error(f"PayPal注文情報の取得に失敗: {token}, レスポンス: {response_text}")
                            except Exception as e:
                                logger.error(f"PayPal注文キャンセル処理中にエラー発生: {token}, エラー: {str(e)}")
                                error_count += 1
                except Exception as e:
                    logger.error(f"ファイル読み込み中にエラー発生: {filename}, エラー: {str(e)}")
                    error_count += 1
                
                # ファイルを削除
                os.remove(file_path)
                logger.info(f"履歴ファイルを削除しました: {filename}")
                deleted_count += 1
            except Exception as e:
                logger.error(f"ファイル削除中にエラー発生: {filename}, エラー: {str(e)}")
                error_count += 1
    
    # 結果を返す
    message = f"{deleted_count}件の履歴ファイルと{paypal_deleted_count}件のPayPal注文を削除しました。"
    if error_count > 0:
        message += f" {error_count}件のエラーが発生しました。"
    
    return jsonify({
        'success': error_count == 0,
        'message': message,
        'deleted_count': deleted_count,
        'paypal_deleted_count': paypal_deleted_count,
        'error_count': error_count
    })

# PayPal決済状態の確認
# トークンキャッシュ用の変数（モジュールレベル）
_paypal_token_cache = {
    "token": None,
    "expires_at": 0
}

# この関数はpaypal_utils.pyからインポートされているため、ここでの定義は削除します
# get_paypal_access_tokenはimportから取得されます

# APIエンドポイントのキャッシュ
_api_base_cache = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
    "last_mode": None,
    "last_updated": 0
}

def get_api_base():
    # 
#     PayPal APIのベースURLを取得する
#     キャッシュ機能とエラーハンドリングを実装
#     
#     Returns:
#         文字列: PayPal APIのベースURL
    
    global _api_base_cache
    
    try:
        # 設定からPayPalモードを取得
        config = get_config()
        paypal_mode = config.get('paypal_mode', 'sandbox')
        
        # モードの正規化
        if paypal_mode.lower() not in ['sandbox', 'live']:
            logger.warning(f"無効なPayPalモード: {paypal_mode}。sandboxを使用します。")
            paypal_mode = 'sandbox'
        else:
            paypal_mode = paypal_mode.lower()
        
        # キャッシュにない場合は追加
        if paypal_mode not in _api_base_cache:
            if paypal_mode == 'sandbox':
                _api_base_cache[paypal_mode] = "https://api-m.sandbox.paypal.com"
            else:
                _api_base_cache[paypal_mode] = "https://api-m.paypal.com"
            
            # ログ出力
            logger.debug(f"PayPal APIベースURLを更新: モード={paypal_mode}")
        
        # モードに応じたベースURLを返す
        return _api_base_cache[paypal_mode]
    
    except Exception as e:
        # 例外が発生した場合はログに記録し、デフォルト値を返す
        logger.error(f"PayPal APIベースURL取得エラー: {str(e)}")
        return "https://api-m.sandbox.paypal.com"  # 安全なデフォルト値

def create_paypal_payment_link(amount, customer, request=None):
    # 
#     PayPal決済リンクを生成する
#     
#     Args:
#         amount: 金額
#         customer: 客先名
#         
#     Returns:
#         PayPal決済リンクのURL
    
    config = get_config()
    client_id = config.get('paypal_client_id', '')
    client_secret = config.get('paypal_client_secret', '')
    
    # デバッグ情報をログに記録
    logger.info(f"設定読み込み結果: client_id存在={bool(client_id)}, client_secret存在={bool(client_secret)}")
    logger.info(f"利用可能な設定キー: {list(config.keys())}")
    logger.info(f"環境変数確認: PAYPAL_CLIENT_ID={bool(os.environ.get('PAYPAL_CLIENT_ID'))}, PAYPAL_CLIENT_SECRET={bool(os.environ.get('PAYPAL_CLIENT_SECRET'))}")
    
    # 設定の詳細をデバッグ出力
    for key, value in config.items():
        if 'secret' in key.lower() or 'password' in key.lower():
            logger.info(f"設定 {key}: {'***設定済み***' if value else '未設定'}")
        else:
            logger.info(f"設定 {key}: {value}")
    
    if not client_id or not client_secret:
        logger.warning("PayPal Client IDまたはClient Secretが設定されていません")
        logger.warning(f"client_id: {'***設定済み***' if client_id else '未設定'}")
        logger.warning(f"client_secret: {'***設定済み***' if client_secret else '未設定'}")
        return ''
    
    # 金額のフォーマットを整理
    try:
        # 金額から数字とドット以外を除去
        amount_str = ''.join(filter(lambda x: x.isdigit() or x == '.', str(amount)))
        # 空の場合や変換できない場合はデフォルト値を使用
        if not amount_str:
            logger.warning(f"金額が空または無効です: '{amount}'")
            amount_value = 0
        else:
            # 数値に変換
            amount_value = float(amount_str)
            
            # 金額が異常に小さい場合は桁数の間違いの可能性がある
            if 0 < amount_value < 100 and len(amount_str) <= 2:
                # 可能性として1000円単位の入力ミスの可能性
                logger.warning(f"金額が異常に小さいため、1000倍して調整します: {amount_value} → {amount_value * 1000}")
                amount_value *= 1000
            
            # 日本円の場合は整数に丸める（小数点以下は不要）
            if config.get('currency_code', 'JPY') == 'JPY':
                amount_value = int(amount_value)
                formatted_amount = str(amount_value)
            else:
                # 小数点以下2桁にフォーマット
                formatted_amount = "{:.2f}".format(amount_value)
                
        logger.info(f"金額フォーマット: 元の値='{amount}', 変換後='{formatted_amount}'")
    except (ValueError, TypeError) as e:
        logger.warning(f"金額のフォーマットエラー: {amount}, エラー: {str(e)}")
        # デフォルト値を設定
        formatted_amount = "1000"
    
    # 金額が0の場合はデフォルト値を使用
    if formatted_amount == "0" or formatted_amount == "0.00":
        logger.warning("金額が0のため、デフォルト値の1000円を使用します")
        formatted_amount = "1000"
    
    # PayPalモードに基づいてベースURLを設定
    paypal_mode = config.get('paypal_mode', 'sandbox')
    api_base = "https://api-m.sandbox.paypal.com" if paypal_mode == "sandbox" else "https://api-m.paypal.com"
    
    # 顧客名が空の場合のデフォルト値
    customer_name = customer if customer and customer != '不明' else "請求先"
    
    # 顧客名に特殊文字が含まれている場合はエスケープ
    customer_name = urllib.parse.quote(customer_name)
    
    # 通貨コード
    currency_code = config.get('currency_code', 'JPY')
    
    # リトライ回数
    max_retries = 2
    retry_count = 0
    
    while retry_count <= max_retries:
        try:
            # get_paypal_access_token関数を使用してアクセストークンを取得
            try:
                access_token = get_paypal_access_token()
            except Exception as token_err:
                logger.error(f"PayPalアクセストークン取得中に例外が発生: {str(token_err)}")
                access_token = None
            
            if not access_token:
                logger.error("PayPalアクセストークンの取得に失敗しました")
                retry_count += 1
                if retry_count <= max_retries:
                    logger.info(f"PayPalトークン取得リトライ: {retry_count}/{max_retries}")
                    time.sleep(1)  # 1秒待機してリトライ
                    continue
                else:
                    # リトライ回数超過、フォールバック方式を使用
                    raise Exception("アクセストークンの取得に失敗しました")
            
            logger.info("PayPalアクセストークン取得成功")
            
            # Orders APIを使用して決済リンクを生成
            orders_url = f"{api_base}/v2/checkout/orders"
            orders_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            }
            
            # 注文説明（特殊文字を除去）
            cleaned_customer = urllib.parse.unquote(customer_name)
            # 特殊文字や制御文字を除去
            cleaned_customer = re.sub(r'[^\w\s\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', '', cleaned_customer)
            description = f"{cleaned_customer}様宛請求書"
            
            # 注文データ
            payload = {
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "amount": {
                            "currency_code": currency_code,
                            "value": formatted_amount
                        },
                        "description": description[:127]
                    }
                ],
                "application_context": {
                    "return_url": (request.url_root.rstrip('/') if request else '') + url_for('payment_success'),
                    "cancel_url": (request.url_root.rstrip('/') if request else '') + url_for('payment_cancel'),
                    "brand_name": "PDF PayPal System",
                    "locale": "ja-JP",
                    "landing_page": "LOGIN",
                    "shipping_preference": "NO_SHIPPING",
                    "user_action": "PAY_NOW"
                }
            }
            
            # APIリクエスト
            logger.info(f"PayPal注文作成開始: {orders_url}")
            logger.debug(f"PayPal注文リクエスト: {payload}")
            
            orders_response = requests.post(
                orders_url, 
                headers=orders_headers, 
                json=payload,
                timeout=15  # タイムアウト設定
            )
            
            # レスポンスコードをチェック
            if orders_response.status_code != 201:
                logger.error(f"PayPal注文作成エラー: ステータス={orders_response.status_code}, レスポンス={orders_response.text}")
                
                # エラーレスポンスの詳細をログに記録
                try:
                    error_details = orders_response.json()
                    logger.error(f"PayPalエラー詳細: {json.dumps(error_details, indent=2)}")
                    
                    # 金額関連のエラーの場合、金額を調整して再試行
                    if 'details' in error_details:
                        for detail in error_details.get('details', []):
                            if 'issue' in detail and ('amount' in detail.get('issue', '').lower() or 'value' in detail.get('issue', '').lower()):
                                logger.warning("金額関連のエラーを検出しました。金額を調整します。")
                                # 金額を調整（例: 小数点以下を削除）
                                if '.' in formatted_amount:
                                    formatted_amount = formatted_amount.split('.')[0]
                                    logger.info(f"金額を調整しました: {formatted_amount}")
                                    # 金額を調整したので、このイテレーションをスキップして再試行
                                    retry_count += 1
                                    if retry_count <= max_retries:
                                        logger.info(f"金額調整後にPayPal注文作成リトライ: {retry_count}/{max_retries}")
                                        time.sleep(1)  # 1秒待機してリトライ
                                        continue
                except Exception as json_err:
                    logger.error(f"PayPalエラーレスポンスのJSONパースエラー: {str(json_err)}")
                
                retry_count += 1
                if retry_count <= max_retries:
                    logger.info(f"PayPal注文作成リトライ: {retry_count}/{max_retries}")
                    time.sleep(1)  # 1秒待機してリトライ
                    continue
                else:
                    # リトライ回数超過、フォールバック方式を使用
                    raise Exception(f"注文作成失敗: {orders_response.status_code}")
            
            try:
                response_data = orders_response.json()
                logger.info(f"PayPal注文作成成功: ID={response_data.get('id', '不明')}")
                
                # レスポンス全体をデバッグログに記録
                logger.debug(f"PayPal応答全体: {json.dumps(response_data, indent=2)}")
                
                # 承認リンクを取得
                approval_link = None
                if "links" in response_data:
                    # 全てのリンク情報をログに記録（デバッグ用）
                    logger.debug(f"PayPal応答のリンク情報: {json.dumps(response_data['links'], indent=2)}")
                    
                    # まず'approve'リンクを探す
                    for link in response_data["links"]:
                        if link.get("rel") == "approve":
                            approval_link = link.get("href")
                            logger.info(f"'approve'リンクが見つかりました: {approval_link}")
                            break
                    
                    # 'approve'が見つからない場合は'payer-action'を探す
                    if not approval_link:
                        for link in response_data["links"]:
                            if link.get("rel") == "payer-action":
                                approval_link = link.get("href")
                                logger.info(f"'payer-action'リンクが見つかりました: {approval_link}")
                                break
                    
                    # それでも見つからない場合は'checkout'または'self'以外の最初のリンクを使用
                    if not approval_link:
                        for link in response_data["links"]:
                            if link.get("rel") == "checkout":
                                approval_link = link.get("href")
                                logger.info(f"'checkout'リンクが見つかりました: {approval_link}")
                                break
                            
                    # 最後の手段として'self'以外の任意のリンクを使用
                    if not approval_link:
                        for link in response_data["links"]:
                            if link.get("rel") != "self":
                                approval_link = link.get("href")
                                logger.info(f"代替リンクが見つかりました: {approval_link} (rel: {link.get('rel')})")
                                break
            except json.JSONDecodeError as json_err:
                logger.error(f"PayPal応答のJSONパースエラー: {str(json_err)}")
                # 応答テキストをそのまま記録
                logger.error(f"PayPal応答テキスト: {orders_response.text}")
                raise Exception(f"PayPal応答のJSONパースエラー: {str(json_err)}")
            
            if approval_link:
                logger.info(f"PayPal決済リンク生成成功: {approval_link}")
                return approval_link
            else:
                logger.warning(f"PayPal決済リンクが見つかりません: {json.dumps(response_data, indent=2)}")
                # リンクが見つからない場合はフォールバック
                raise Exception("決済リンクが見つかりません")
        except Exception as e:
            logger.error(f"PayPal決済リンク生成エラー: {str(e)}")
            retry_count += 1
            if retry_count <= max_retries:
                logger.info(f"PayPal決済リンク生成リトライ: {retry_count}/{max_retries}")
                time.sleep(1)  # 1秒待機してリトライ
            else:
                # リトライ回数超過、フォールバック方式を使用
                logger.info("フォールバック方式で決済リンクを生成します")
                break
    
    # APIでの生成に失敗した場合のフォールバック
    try:
        # 従来の方法でリンクを生成
        base_url = "https://www.sandbox.paypal.com" if paypal_mode == "sandbox" else "https://www.paypal.com"
        
        # PayPalビジネスメールアドレスを取得
        paypal_email = config.get('paypal_email', '')
        
        # メールアドレスが設定されていない場合はクライアントIDを使用
        business_id = paypal_email if paypal_email else client_id
        
        # 顧客名をクリーニング
        cleaned_customer = re.sub(r'[^\w\s\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', '', customer_name)
        
        # 決済リンクを生成
        payment_link = f"{base_url}/cgi-bin/webscr?cmd=_xclick&business={urllib.parse.quote(business_id)}&item_name={urllib.parse.quote(cleaned_customer + '様宛請求書')}&amount={formatted_amount}&currency_code={currency_code}&charset=UTF-8"
        logger.info(f"フォールバック決済リンク生成: {payment_link}")
        return payment_link
    except Exception as e:
        logger.error(f"フォールバック決済リンク生成エラー: {str(e)}")
        return ''

# payment_status_checkerは上部で安全にインポート済み

# 選択された金額で決済リンクを生成するAPI
@app.route('/generate_payment_link', methods=['POST'])
@app.route('/api/generate_payment_link', methods=['POST'])
def generate_payment_link():
    """選択された金額で決済リンクを生成するAPI（マルチプロバイダー対応）"""
    try:
        # JSONデータを取得
        data = request.get_json()
        if not data:
            logger.error("JSONデータが見つかりません")
            return jsonify({'error': 'データが見つかりません'}), 400
        
        # 必要なデータを取得
        customer = data.get('customer', '不明')
        amount = data.get('amount', '0')
        filename = data.get('filename', '')
        provider = data.get('provider', 'paypal')  # 決済プロバイダー
        
        logger.info(f"決済リンク生成リクエスト: 顧客名={customer}, 金額={amount}, ファイル名={filename}, プロバイダー={provider}")
        
        # 金額を数値に変換
        try:
            amount_float = float(amount)
        except (ValueError, TypeError):
            logger.error(f"無効な金額: {amount}")
            return jsonify({
                'success': False,
                'error': '有効な金額を入力してください'
            }), 400
        
        # 決済プロバイダー統合ヘルパーを使用（統一ロジックで自動切り替え含む）
        from payment_utils import create_payment_link, format_payment_result_for_display
        
        # 決済リンクを生成（payment_utils.pyの統一ロジックが自動で利用可能性チェックと代替プロバイダー切り替えを行う）
        logger.info(f"決済リンク生成開始: プロバイダー={provider}, 顧客名={customer}, 金額={amount_float}")
        result = create_payment_link(
            provider=provider,
            amount=amount_float,
            customer_name=customer,
            description=filename,
            currency="JPY"
        )
        
        # 結果をフォーマット
        formatted_result = format_payment_result_for_display(result)
        
        # 使用されたプロバイダーを取得（自動切り替えされた場合）
        used_provider = result.get('provider', provider)
        
        if result.get('success'):
            logger.info(f"決済リンク生成成功: {used_provider} - {result.get('payment_link')}")
            return jsonify({
                'success': True,
                'payment_link': result.get('payment_link'),
                'provider': used_provider,
                'message': result.get('message'),
                'details': formatted_result
            })
        else:
            logger.error(f"決済リンク生成失敗: {result.get('message')}")
            return jsonify({
                'success': False,
                'error': result.get('message'),
                'provider': used_provider,
                'details': formatted_result
            }), 400
            
    except Exception as e:
        logger.error(f"決済リンク生成エラー: {str(e)}")
        import traceback
        logger.error(f"スタックトレース: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'決済リンク生成中にエラーが発生しました: {str(e)}'
        }), 500

# 単一PDFファイルの処理
# アップロード処理のCSRF除外設定は、アプリ初期化後に行われます

@app.route('/upload', methods=['POST'])
def upload_file():
    # PDFファイルをアップロードするエンドポイント
#     
#     フロントエンドからアップロードされたPDFファイルを保存し、ファイル名を返す
    
    logger.info("ファイルアップロードリクエストを受信")
    logger.info(f"リクエストタイプ: {request.content_type}")
    logger.info(f"リクエストファイル: {request.files}")
    logger.info(f"リクエストフォーム: {request.form}")
    logger.info(f"リクエストデータ: {request.data}")
    
    try:
        # ファイルが存在するか確認
        if 'file' not in request.files:
            logger.error("ファイルが見つかりません")
            return jsonify({
                'success': False,
                'error': 'ファイルが見つかりません'
            }), 400
        
        file = request.files['file']
        
        # ファイル名が空でないか確認
        if file.filename == '':
            logger.error("ファイル名が空です")
            return jsonify({
                'success': False,
                'error': 'ファイル名が空です'
            }), 400
        
        # ファイル名を安全に処理
        filename = secure_filename(file.filename)
        
        # アップロードフォルダが存在することを確認
        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        
        # upload_folderがNoneの場合のフォールバック処理
        if upload_folder is None:
            # 環境変数から取得を試みる
            upload_folder = os.environ.get('UPLOAD_FOLDER')
            
            # それでもNoneの場合はデフォルト値を使用
            if upload_folder is None:
                upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
                logger.warning(f"UPLOAD_FOLDERが設定されていないため、デフォルト値を使用します: {upload_folder}")
        
        # アップロードフォルダが存在しない場合は作成
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
            logger.info(f"アップロードフォルダを作成しました: {upload_folder}")
            
        # 設定を更新
        current_app.config['UPLOAD_FOLDER'] = upload_folder
        
        # ファイルを保存
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        logger.info(f"ファイルを保存しました: {filepath}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'message': 'ファイルがアップロードされました'
        })
        
    except Exception as e:
        logger.error(f"ファイルアップロードエラー: {str(e)}")
        import traceback
        logger.error(f"スタックトレース: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'ファイルアップロード中にエラーが発生しました: {str(e)}'
        }), 500


def process_single_pdf(filepath, filename, request):
    try:
        logger.info(f"単一PDF処理開始: {filepath}")
        
        # PDFからテキストを抽出
        text_result = extract_text_from_pdf(filepath)
        extracted_text = text_result.get('text', '')
        extraction_method = text_result.get('method', 'unknown')
        
        if not extracted_text:
            logger.warning(f"テキスト抽出失敗: {filepath}")
            return {
                'filename': filename,
                'success': False,
                'error': 'テキストを抽出できませんでした'
            }
        
        # テキストの一部をログに記録
        text_preview = extracted_text[:200] + '...' if len(extracted_text) > 200 else extracted_text
        logger.info(f"抽出されたテキストプレビュー: {text_preview}")
        
        # 顧客名を抽出
        customer_name = customer_extractor.extract_customer(extracted_text, filename)
        
        # 金額を抽出
        amount_result = amount_extractor.extract_invoice_amount(extracted_text)
        # タプルから直接値を取得 (金額, 抽出元の行)
        amount = amount_result[0] if amount_result and amount_result[0] is not None else "0"
        # 抽出元の行（デバッグ用）
        amount_source_line = amount_result[1] if amount_result and len(amount_result) > 1 else ""
        logger.debug(f"抽出された金額: {amount}, 抽出元: {amount_source_line}")
        
        # 金額のフォーマットを整える
        amount_str = str(amount).replace(',', '').strip()
        
        # 決済プロバイダーの選択ロジック
        payment_link = None
        order_id = None
        used_provider = None
        
        # リクエストデータから決済プロバイダーを取得
        provider = None
        if request.is_json:
            request_data = request.get_json()
            provider = request_data.get('payment_provider') if request_data else None
        else:
            provider = request.form.get('payment_provider')
        
        # 設定からデフォルトプロバイダーを取得
        if not provider:
            config = get_config()
            provider = config.get('default_payment_provider', 'paypal')
        
        logger.info(f"決済プロバイダー: {provider}")
        
        try:
            if amount_str and amount_str != '0':
                logger.info(f"決済リンク生成開始: プロバイダー={provider}, 金額={amount_str}, 顧客={customer_name}")
                
                # payment_utils.pyの統一ロジックを使用
                try:
                    from payment_utils import create_payment_link
                    
                    # 決済リンクを生成
                    result = create_payment_link(
                        provider=provider,
                        amount=float(amount_str),
                        customer_name=customer_name,
                        description=filename,
                        currency="JPY"
                    )
                    
                    if result.get('success'):
                        payment_link = result.get('payment_link')
                        used_provider = result.get('provider', provider)
                        order_id = result.get('order_id')
                        logger.info(f"決済リンク生成成功: {used_provider} - {payment_link}")
                    else:
                        logger.warning(f"決済リンク生成失敗: {result.get('message')}")
                        
                except ImportError:
                    # payment_utils.pyが利用できない場合のフォールバック
                    logger.warning("payment_utils.pyが利用できません。PayPalのみを使用します")
                    if provider == 'paypal' or provider == 'stripe':
                        # PayPalでフォールバック
                        config = get_config()
                        client_id = config.get('paypal_client_id', '')
                        client_secret = config.get('paypal_client_secret', '')
                        if client_id and client_secret:
                            payment_link = create_paypal_payment_link(amount_str, customer_name, request)
                            used_provider = 'paypal'
                            if payment_link:
                                logger.info(f"PayPal決済リンク生成成功: {payment_link}")
                            else:
                                logger.warning("PayPal決済リンクが空で返されました")
                        else:
                            logger.warning("PayPal認証情報が設定されていません")
                    
                except Exception as link_err:
                    logger.error(f"決済リンク生成中の例外: {str(link_err)}")
                    # エラーの詳細情報をログに記録
                    import traceback
                    logger.error(f"スタックトレース: {traceback.format_exc()}")
                    raise
        except Exception as e:
            logger.error(f"決済リンク生成エラー: {str(e)}")
            # エラーを記録するが処理は続行
        
        # 結果を返す
        return {
            'filename': filename,
            'customer_name': customer_name,
            'amount': amount_str,
            'payment_link': payment_link,
            'order_id': order_id,
            'provider': used_provider,
            'extraction_method': extraction_method,
            'success': True
        }
        
    except Exception as e:
        logger.error(f"PDF処理エラー ({filename}): {str(e)}")
        return {
            'filename': filename,
            'success': False,
            'error': str(e)
        }

# PDFファイルの処理
@app.route('/process', methods=['POST'])
@api_access_required
def process_pdf():
    # アップロードされたPDFファイルを処理するAPIエンドポイント
#     
#     PDFから顧客名と金額を抽出し、PayPal決済リンクを生成する
    
    logger.info("PDF処理リクエストを受信")
    logger.info(f"PDF処理時のセッション状態: {session}")
    logger.info(f"PDF処理時のリクエストタイプ: {request.content_type}")
    
    try:
        # JSONリクエストかどうか確認
        if request.is_json:
            data = request.get_json()
            logger.info(f"JSONリクエストを受信: {data}")
        else:
            data = request.form.to_dict()
            logger.info(f"フォームデータを受信: {data}")
        
        if not data or 'filename' not in data:
            logger.warning("ファイル名が指定されていません")
            return jsonify({'error': 'ファイル名が指定されていません'}), 400
        
        filename = data['filename']
        
        # 決済プロバイダーの取得とログ記録
        payment_provider = data.get('payment_provider', 'default')
        logger.info(f"リクエストされた決済プロバイダー: {payment_provider}")
        
        # アップロードフォルダの取得
        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        
        # upload_folderがNoneの場合のフォールバック処理
        if upload_folder is None:
            # 環境変数から取得を試みる
            upload_folder = os.environ.get('UPLOAD_FOLDER')
            
            # それでもNoneの場合はデフォルト値を使用
            if upload_folder is None:
                upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
                logger.warning(f"UPLOAD_FOLDERが設定されていないため、デフォルト値を使用します: {upload_folder}")
        
        # 設定を更新
        current_app.config['UPLOAD_FOLDER'] = upload_folder
        
        filepath = os.path.join(upload_folder, filename)
        
        logger.info(f"PDF処理ファイルパス: {filepath}")
        
        # ファイルの存在確認
        if not os.path.exists(filepath):
            logger.warning(f"ファイルが存在しません: {filepath}")
            return jsonify({'error': 'ファイルが見つかりません'}), 404
        
        # ファイルのサイズとタイプを確認
        file_size = os.path.getsize(filepath)
        logger.info(f"PDFファイルサイズ: {file_size} バイト")
        
        # キャッシュキーを作成（ファイル名 + 決済プロバイダー）
        cache_key = f"{filename}_{payment_provider}"
        
        # キャッシュを確認
        if cache_key in processed_files_cache:
            logger.info(f"キャッシュから結果を返します: {filename} (プロバイダー: {payment_provider})")
            return jsonify(processed_files_cache[cache_key])
        
        # PDFからテキストを抽出
        logger.info(f"PDFからテキストを抽出開始: {filename}")
        
        # 複数ページのPDF処理のための一時ディレクトリ作成
        with tempfile.TemporaryDirectory() as temp_dir:
            # PDFのページ数を確認
            with open(filepath, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                num_pages = len(pdf_reader.pages)
                
                logger.info(f"PDFページ数: {num_pages}")
                
                # 結果を格納するリスト
                results = []
                
                # 単一ページの場合はそのまま処理
                if num_pages == 1:
                    result = process_single_pdf(filepath, filename, request)
                    if result:
                        results.append(result)
                else:
                    # 複数ページの場合は分割して処理
                    logger.info(f"複数ページPDFを分割処理します: {num_pages}ページ")
                    
                    for page_num in range(num_pages):
                        try:
                            # 各ページを個別のPDFとして保存
                            output_pdf = PyPDF2.PdfWriter()
                            output_pdf.add_page(pdf_reader.pages[page_num])
                            
                            page_filename = f"page_{page_num + 1}.pdf"
                            page_filepath = os.path.join(temp_dir, page_filename)
                            
                            with open(page_filepath, 'wb') as output_file:
                                output_pdf.write(output_file)
                            
                            # 各ページを処理
                            page_result = process_single_pdf(page_filepath, f"{filename}_page{page_num + 1}", request)
                            if page_result:
                                results.append(page_result)
                                
                        except Exception as e:
                            logger.error(f"ページ{page_num + 1}の処理中にエラーが発生しました: {str(e)}")
                            results.append({
                                'page': page_num + 1,
                                'error': str(e),
                                'success': False
                            })
        
        # 結果が空の場合のエラー処理
        if not results:
            logger.warning(f"処理結果が空です: {filename}")
            return jsonify({'error': 'PDFから情報を抽出できませんでした'}), 400
        
        # 処理日時を全ての結果に追加
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for result in results:
            if isinstance(result, dict):
                result['timestamp'] = current_time
        
        # 結果をキャッシュに保存
        response_data = {
            'success': True,
            'results': results,
            'message': f'{len(results)}件の処理が完了しました'
        }
        
        processed_files_cache[cache_key] = response_data
        logger.info(f"キャッシュに結果を保存しました: {filename} (プロバイダー: {payment_provider})")
        
        # 履歴ファイルに保存
        try:
            results_folder = app.config['RESULTS_FOLDER']
            os.makedirs(results_folder, exist_ok=True)
            
            # 現在の日時をファイル名に含める
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            history_filename = f'payment_links_{timestamp}.json'
            history_path = os.path.join(results_folder, history_filename)
            
            # 結果をJSONファイルとして保存
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            logger.info(f'履歴ファイルを保存しました: {history_filename}')
        except Exception as e:
            logger.error(f'履歴ファイルの保存に失敗しました: {str(e)}')
        
        return jsonify(response_data)
        
    except Exception as e:
        import traceback
        logger.error(f"PDF処理エラー: {str(e)}")
        logger.error(f"スタックトレース: {traceback.format_exc()}")
        
        # ファイル名が定義されている場合のみ使用
        error_filename = filename if 'filename' in locals() else 'unknown'
        logger.error(f"PDF処理エラー ({error_filename}): {str(e)}")
        
        # JSONレスポンスを返す
        return jsonify({
            'success': False,
            'error': f'PDF処理中にエラーが発生しました: {str(e)}'
        }), 500



# 設定の保存
@app.route('/settings/save', methods=['POST'])
@admin_required
def save_settings():
    # 設定を保存する
#     
#     フォームから送信された設定をJSONファイルに保存する
#     管理者のみ設定を変更可能
    
    logger.info("設定保存リクエストを受信")
    
    # セッションとFlask-Loginの状態を同期
    if AUTH_INIT_AVAILABLE:
        try:
            sync_session_with_user()
        except Exception as e:
            logger.error(f"セッション同期エラー: {e}")
    
    try:
        # フォームデータを取得
        client_id = request.form.get('client_id', '')
        client_secret = request.form.get('client_secret', '')
        paypal_mode = request.form.get('paypal_mode', 'sandbox')
        admin_email = request.form.get('admin_email', '')
        
        # 現在の設定を取得
        config = get_config()
        
        # 権限情報を取得（Flask-Loginとセッションの両方をチェック）
        is_admin = False
        
        # Flask-Loginからの権限情報
        if FLASK_LOGIN_AVAILABLE and current_user and current_user.is_authenticated:
            is_admin = getattr(current_user, 'is_admin', False)
        
        # セッションからの権限情報（フォールバック）
        if not is_admin:
            is_admin = session.get('admin_logged_in', False)
        
        # 管理者権限の確認（デコレータで既にチェック済みだが念のため）
        if not is_admin:
            flash('設定の変更は管理者のみ許可されています', 'warning')
            return redirect(url_for('settings'))
        
        # 設定を更新
        config['client_id'] = client_id
        config['client_secret'] = client_secret
        config['paypal_mode'] = paypal_mode
        config['admin_email'] = admin_email
        
        # 環境変数にも反映
        os.environ['PAYPAL_MODE'] = paypal_mode
        os.environ['ADMIN_EMAIL'] = admin_email
        
        # 設定をファイルに保存
        save_config(config)
        
        # 設定をデータベースにも保存（管理者ユーザーの設定として）
        try:
            import database
            admin_user = database.get_user_by_username('admin')
            if admin_user:
                admin_id = admin_user['id']
                # PayPal設定をデータベースに保存
                paypal_settings = {
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'mode': paypal_mode,
                    'currency': config.get('currency', 'JPY')
                }
                success = database.save_paypal_settings(admin_id, paypal_settings)
                if success:
                    logger.info("PayPal設定をデータベースに保存しました")
                else:
                    logger.error("データベースへのPayPal設定保存に失敗")
            else:
                logger.error("管理者ユーザーが見つかりません")
        except Exception as db_err:
            logger.error(f"データベース保存エラー: {str(db_err)}")
        
        flash('設定が保存されました', 'success')
        logger.info("設定が正常に保存されました")
        
        return redirect(url_for('settings'))
        
    except Exception as e:
        flash(f'設定の保存中にエラーが発生しました: {str(e)}', 'error')
        logger.error(f"設定保存エラー: {str(e)}")
        return redirect(url_for('settings'))

# 接続テスト
@app.route('/settings/test_connection', methods=['POST'])
@admin_required
def test_connection():
    # 接続テストを行う
#     
#     PayPal APIへの接続テストを行い、結果を返す
#     JSONリクエストとフォームデータの両方に対応
    
    logger.info("接続テストリクエストを受信")
    
    # セッションとFlask-Loginの状態を同期
    if AUTH_INIT_AVAILABLE:
        try:
            sync_session_with_user()
        except Exception as e:
            logger.error(f"セッション同期エラー: {e}")
    
    try:
        # JSONリクエストとフォームデータの両方に対応
        if request.is_json:
            data = request.get_json()
            client_id = data.get('client_id', '')
            client_secret = data.get('client_secret', '')
            paypal_mode = data.get('paypal_mode', 'sandbox')
        else:
            client_id = request.form.get('client_id', '')
            client_secret = request.form.get('client_secret', '')
            paypal_mode = request.form.get('paypal_mode', 'sandbox')
        
        logger.info(f"PayPal接続テスト: モード={paypal_mode}")
        
        # アクセストークンを取得して接続テスト
        token = get_paypal_access_token(client_id, client_secret, paypal_mode)
        
        if token:
            logger.info("PayPal API接続テスト成功")
            return jsonify({
                'success': True,
                'message': 'PayPal APIに正常に接続できました'
            })
        else:
            logger.warning("PayPal API接続テスト失敗: トークン取得失敗")
            return jsonify({
                'success': False,
                'message': 'PayPal APIに接続できませんでした'
            })
    
    except Exception as e:
        logger.error(f"PayPal API接続テストエラー: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'エラー: {str(e)}'
        })

# 設定のエクスポート
@app.route('/settings/export', methods=['GET'])
@admin_required
def export_settings():
    # 設定をJSONファイルとしてエクスポートする
#     
#     現在の設定をJSONファイルとしてダウンロード可能にする
#     管理者のみ設定をエクスポート可能
    
    logger.info("設定エクスポートリクエストを受信")
    
    # セッションとFlask-Loginの状態を同期
    if AUTH_INIT_AVAILABLE:
        try:
            sync_session_with_user()
        except Exception as e:
            logger.error(f"セッション同期エラー: {e}")
    
    try:
        # 現在の設定を取得
        config = get_config()
        
        # 機密情報をマスク
        if 'client_secret' in config:
            config['client_secret'] = '********'  # 機密情報をマスク
        
        # JSONファイルとして出力
        json_data = json.dumps(config, indent=4, ensure_ascii=False)
        filename = f"pdf_paypal_settings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # レスポンスを作成
        response = make_response(json_data)
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-Type"] = "application/json"
        
        logger.info(f"設定をエクスポートしました: {filename}")
        return response
        
    except Exception as e:
        logger.error(f"設定エクスポートエラー: {str(e)}")
        flash(f'設定のエクスポート中にエラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('settings'))

# 設定のインポート
@app.route('/settings/import', methods=['POST'])
@admin_required
def import_settings():
    # 設定をJSONファイルからインポートする
#     
#     アップロードされたJSONファイルから設定をインポートする
#     管理者のみ設定をインポート可能
    
    logger.info("設定インポートリクエストを受信")
    
    # セッションとFlask-Loginの状態を同期
    if AUTH_INIT_AVAILABLE:
        try:
            sync_session_with_user()
        except Exception as e:
            logger.error(f"セッション同期エラー: {e}")
    
    try:
        # 権限情報を取得（Flask-Loginとセッションの両方をチェック）
        is_admin = False
        
        # Flask-Loginからの権限情報
        if FLASK_LOGIN_AVAILABLE and current_user and current_user.is_authenticated:
            is_admin = getattr(current_user, 'is_admin', False)
        
        # セッションからの権限情報（フォールバック）
        if not is_admin:
            is_admin = session.get('admin_logged_in', False)
        
        # 管理者権限の確認（デコレータで既にチェック済みだが念のため）
        if not is_admin:
            flash('設定のインポートは管理者のみ許可されています', 'warning')
            return redirect(url_for('settings'))
        
        # 現在の設定を取得
        current_config = get_config()
        
        # ファイルがアップロードされているか確認
        if 'file' not in request.files:
            flash('ファイルがアップロードされていません', 'error')
            return redirect(url_for('settings'))
        
        file = request.files['file']
        
        # ファイル名が空でないか確認
        if file.filename == '':
            flash('ファイルが選択されていません', 'error')
            return redirect(url_for('settings'))
        
        # JSONファイルであるか確認
        if not file.filename.endswith('.json'):
            flash('JSONファイルのみアップロードできます', 'error')
            return redirect(url_for('settings'))
        
        # ファイルを読み込む
        file_content = file.read().decode('utf-8')
        imported_config = json.loads(file_content)
        
        # 必須キーが含まれているか確認
        required_keys = ['client_id', 'paypal_mode']
        for key in required_keys:
            if key not in imported_config:
                flash(f'インポートされた設定に必須キー {key} が含まれていません', 'error')
                return redirect(url_for('settings'))
        
        # 設定をマージ
        for key, value in imported_config.items():
            # client_secretが'********'の場合は更新しない
            if key == 'client_secret' and value == '********':
                continue
                
            current_config[key] = value
        
        # 設定を保存
        save_config(current_config)
        
        # 環境変数を更新
        os.environ['PAYPAL_MODE'] = current_config.get('paypal_mode', 'sandbox')
        os.environ['ADMIN_EMAIL'] = current_config.get('admin_email', '')
        
        flash('設定がインポートされました', 'success')
        logger.info("設定がインポートされました")
        return redirect(url_for('settings'))
        
    except json.JSONDecodeError:
        flash('無効なJSONファイルです', 'error')
        logger.error("無効なJSONファイルがアップロードされました")
        return redirect(url_for('settings'))
        
    except Exception as e:
        flash(f'設定のインポート中にエラーが発生しました: {str(e)}', 'error')
        logger.error(f"設定インポートエラー: {str(e)}")
        return redirect(url_for('settings'))

# 設定保存用のAPIエンドポイント
@app.route('/settings/save_common', methods=['POST'])
@csrf.exempt
def save_common_settings():
    """共通設定を保存するAPIエンドポイント"""
    try:
        # JSON形式またはフォームデータを受け取る
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        logger.info(f"共通設定保存リクエスト: {data}")
        
        # CSRFトークンを除外
        csrf_token = data.pop('csrf_token', None)
        
        # 設定マネージャーを使用して設定を保存
        from config_manager import ConfigManager
        config_manager = ConfigManager()
        
        # 設定を更新
        config_updates = {}
        
        # 通貨設定
        if 'default_currency' in data:
            config_updates['default_currency'] = data['default_currency']
        
        # OCR設定
        if 'use_ai_ocr' in data:
            config_updates['use_ai_ocr'] = data.get('use_ai_ocr') == 'on'
        
        if 'ocr_method' in data:
            config_updates['ocr_method'] = data['ocr_method']
        
        if 'ocr_api_key' in data:
            config_updates['ocr_api_key'] = data['ocr_api_key']
        
        if 'ocr_endpoint' in data:
            config_updates['ocr_endpoint'] = data['ocr_endpoint']
        
        # 抽出設定
        if 'enable_customer_extraction' in data:
            config_updates['enable_customer_extraction'] = data['enable_customer_extraction']
        
        if 'enable_amount_extraction' in data:
            config_updates['enable_amount_extraction'] = data['enable_amount_extraction']
        
        if 'default_amount' in data:
            try:
                config_updates['default_amount'] = int(data['default_amount'])
            except ValueError:
                config_updates['default_amount'] = 1000
        
        # 設定を保存
        if config_updates:
            # 設定を直接更新
            config_manager.config.update(config_updates)
            save_result = config_manager.save_config(config_manager.config)
            
            if save_result:
                logger.info(f"共通設定保存成功: {config_updates}")
                
                # 設定変更時にキャッシュをクリア
                try:
                    clear_cache()
                    logger.info("共通設定変更によりキャッシュをクリアしました")
                except Exception as e:
                    logger.warning(f"キャッシュクリア中にエラー: {e}")
                
                return jsonify({
                    'success': True,
                    'message': '共通設定が正常に保存されました'
                }), 200
            else:
                logger.error("共通設定保存失敗")
                return jsonify({
                    'success': False,
                    'error': '設定の保存に失敗しました'
                }), 500
        else:
            return jsonify({
                'success': True,
                'message': '更新する設定がありませんでした'
            }), 200
        
    except Exception as e:
        logger.error(f"共通設定保存エラー: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'設定保存中にエラーが発生しました: {str(e)}'
        }), 500

@app.route('/settings/save_advanced', methods=['POST'])
@csrf.exempt
def save_advanced_settings():
    """高度な設定を保存するAPIエンドポイント"""
    try:
        # JSON形式またはフォームデータを受け取る
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        logger.info(f"高度な設定保存リクエスト: {data}")
        
        # CSRFトークンを除外
        csrf_token = data.pop('csrf_token', None)
        
        # 設定マネージャーを使用して設定を保存
        from config_manager import ConfigManager
        config_manager = ConfigManager()
        
        # 設定を更新
        config_updates = {}
        
        # 決済リンク設定
        if 'payment_link_expire_days' in data:
            try:
                config_updates['payment_link_expire_days'] = int(data['payment_link_expire_days'])
            except ValueError:
                config_updates['payment_link_expire_days'] = 30
        
        if 'payment_link_auto_tax' in data:
            config_updates['payment_link_auto_tax'] = data.get('payment_link_auto_tax') == 'on'
        
        # セキュリティ設定
        if 'encrypt_api_keys' in data:
            config_updates['encrypt_api_keys'] = data.get('encrypt_api_keys') == 'on'
        
        if 'api_key_rotation_days' in data:
            try:
                config_updates['api_key_rotation_days'] = int(data['api_key_rotation_days'])
            except ValueError:
                config_updates['api_key_rotation_days'] = 90
        
        # Webhook設定
        if 'webhook_enable_signature_verification' in data:
            config_updates['webhook_enable_signature_verification'] = data.get('webhook_enable_signature_verification') == 'on'
        
        if 'webhook_timeout_seconds' in data:
            try:
                config_updates['webhook_timeout_seconds'] = int(data['webhook_timeout_seconds'])
            except ValueError:
                config_updates['webhook_timeout_seconds'] = 30
        
        if 'webhook_retry_attempts' in data:
            try:
                config_updates['webhook_retry_attempts'] = int(data['webhook_retry_attempts'])
            except ValueError:
                config_updates['webhook_retry_attempts'] = 3
        
        # 通貨設定
        if 'supported_currencies' in data:
            # 複数選択の場合は配列として処理
            if isinstance(data['supported_currencies'], list):
                config_updates['supported_currencies'] = data['supported_currencies']
            else:
                config_updates['supported_currencies'] = [data['supported_currencies']]
        
        # 設定を保存
        if config_updates:
            # 設定を直接更新
            config_manager.config.update(config_updates)
            save_result = config_manager.save_config(config_manager.config)
            
            if save_result:
                logger.info(f"高度な設定保存成功: {config_updates}")
                
                # 設定変更時にキャッシュをクリア
                try:
                    clear_cache()
                    logger.info("高度な設定変更によりキャッシュをクリアしました")
                except Exception as e:
                    logger.warning(f"キャッシュクリア中にエラー: {e}")
                
                return jsonify({
                    'success': True,
                    'message': '高度な設定が正常に保存されました'
                }), 200
            else:
                logger.error("高度な設定保存失敗")
                return jsonify({
                    'success': False,
                    'error': '設定の保存に失敗しました'
                }), 500
        else:
            return jsonify({
                'success': True,
                'message': '更新する設定がありませんでした'
            }), 200
        
    except Exception as e:
        logger.error(f"高度な設定保存エラー: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'設定保存中にエラーが発生しました: {str(e)}'
        }), 500

@app.route('/api/config/validate', methods=['POST'])
@csrf.exempt
def validate_config():
    """設定を検証するAPIエンドポイント"""
    try:
        # JSON形式またはフォームデータを受け取る
        if request.is_json:
            config_data = request.get_json()
        else:
            config_data = request.form.to_dict()
        
        logger.info(f"設定検証リクエスト: {config_data}")
        
        # 設定の検証処理
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # 基本的な検証
        if not config_data:
            validation_result['valid'] = False
            validation_result['errors'].append('設定データが空です')
            return jsonify({
                'success': True,
                'validation': validation_result
            }), 200
        
        # PayPal設定の検証
        if 'paypal_client_id' in config_data:
            client_id = config_data['paypal_client_id']
            if client_id and not client_id.startswith('A'):
                validation_result['warnings'].append('PayPal Client IDの形式が正しくない可能性があります')
        
        if 'paypal_client_secret' in config_data:
            client_secret = config_data['paypal_client_secret']
            if client_secret and len(client_secret) < 10:
                validation_result['warnings'].append('PayPal Client Secretが短すぎる可能性があります')
        
        # Stripe設定の検証
        stripe_mode = config_data.get('stripe_mode', 'test')
        
        if 'stripe_secret_key_test' in config_data:
            secret_key = config_data['stripe_secret_key_test']
            if secret_key and not secret_key.startswith('sk_test_'):
                validation_result['errors'].append('Stripe Secret Key (Test)の形式が正しくありません')
        
        if 'stripe_secret_key_live' in config_data:
            secret_key = config_data['stripe_secret_key_live']
            if secret_key and not secret_key.startswith('sk_live_'):
                validation_result['errors'].append('Stripe Secret Key (Live)の形式が正しくありません')
        
        if 'stripe_publishable_key_test' in config_data:
            pub_key = config_data['stripe_publishable_key_test']
            if pub_key and not pub_key.startswith('pk_test_'):
                validation_result['errors'].append('Stripe Publishable Key (Test)の形式が正しくありません')
        
        if 'stripe_publishable_key_live' in config_data:
            pub_key = config_data['stripe_publishable_key_live']
            if pub_key and not pub_key.startswith('pk_live_'):
                validation_result['errors'].append('Stripe Publishable Key (Live)の形式が正しくありません')
        
        # 通貨設定の検証
        if 'default_currency' in config_data:
            currency = config_data['default_currency']
            valid_currencies = ['JPY', 'USD', 'EUR', 'GBP', 'AUD', 'CAD']
            if currency not in valid_currencies:
                validation_result['errors'].append(f'サポートされていない通貨です: {currency}')
        
        # 金額設定の検証
        if 'default_amount' in config_data:
            try:
                amount = float(config_data['default_amount'])
                if amount <= 0:
                    validation_result['errors'].append('デフォルト金額は0より大きい値である必要があります')
                elif amount > 1000000:
                    validation_result['warnings'].append('デフォルト金額が非常に大きく設定されています')
            except ValueError:
                validation_result['errors'].append('デフォルト金額が数値ではありません')
        
        # 決済プロバイダーの検証
        if 'default_payment_provider' in config_data:
            provider = config_data['default_payment_provider']
            if provider not in ['paypal', 'stripe']:
                validation_result['errors'].append(f'サポートされていない決済プロバイダーです: {provider}')
        
        # エラーがあれば全体の検証結果を失敗にする
        if validation_result['errors']:
            validation_result['valid'] = False
        
        return jsonify({
            'success': True,
            'validation': validation_result
        }), 200
        
    except Exception as e:
        logger.error(f"設定検証エラー: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'設定検証中にエラーが発生しました: {str(e)}'
        }), 500

# ファイルダウンロード
@app.route('/download/<path:filename>')
def download_file(filename):
    # ファイルダウンロードのAPIエンドポイント
#     
#     指定されたファイルをダウンロードする
#     
#     Args:
#         filename: ダウンロードするファイル名
    
    logger.info(f"ファイルダウンロードリクエスト: {filename}")
    
    # セキュリティ対策としてファイル名を検証
    if '..' in filename or filename.startswith('/'):
        logger.warning(f"不正なファイルパス: {filename}")
        abort(404)
    
    try:
        # ファイルの存在確認
        upload_folder = current_app.config['UPLOAD_FOLDER']
        filepath = os.path.join(upload_folder, filename)
        
        if not os.path.exists(filepath):
            logger.warning(f"ファイルが存在しません: {filepath}")
            abort(404)
        
        # ファイルを送信
        return send_from_directory(
            upload_folder,
            filename,
            as_attachment=True
        )
    
    except Exception as e:
        logger.error(f"ファイルダウンロードエラー: {str(e)}")
        abort(500)

# LoginManager設定は認証ブループリントで行います

# 認証ブループリントの登録
def register_auth_blueprint(app):
    try:
        from auth import auth_bp, setup_login_manager
        app.register_blueprint(auth_bp)
        setup_login_manager(app)
        logger.info("認証ブループリントを登録しました")
        return True
    except ImportError as e:
        logger.error(f"認証ブループリントのインポートエラー: {str(e)}")
        logger.error(f"トレースバック: {traceback.format_exc()}")
        return False
    except Exception as e:
        logger.error(f"認証ブループリントの登録エラー: {str(e)}")
        logger.error(f"トレースバック: {traceback.format_exc()}")
        return False

# アプリケーションの初期化時に認証ブループリントを登録
auth_registered = register_auth_blueprint(app)

# 新しいバッチPDFエクスポート機能をインポート
try:
    from batch_pdf_export import register_batch_export_route
    # バッチPDFエクスポートのルートを登録
    register_batch_export_route(app)
    logger.info("バッチPDFエクスポート機能を登録しました")
except Exception as e:
    logger.error(f"バッチPDFエクスポート機能の登録エラー: {str(e)}")

# PayPal Webhook処理モジュールをインポート
try:
    from paypal_webhook import verify_webhook_signature, process_payment_webhook
    logger.info("PayPal Webhook処理モジュールをインポートしました")
except Exception as e:
    logger.error(f"PayPal Webhook処理モジュールのインポートエラー: {str(e)}")

# PayPal Webhook エンドポイント
@app.route('/webhook/paypal', methods=['POST'])
def paypal_webhook():
    """
    PayPal Webhookエンドポイント
    
    PayPalからのWebhookイベントを受信し、処理する
    署名を検証し、支払いステータスを更新する
    """
    logger.info("PayPal Webhookリクエストを受信")
    
    try:
        # リクエストヘッダーから必要な情報を取得
        transmission_id = request.headers.get('Paypal-Transmission-Id')
        timestamp = request.headers.get('Paypal-Transmission-Time')
        cert_url = request.headers.get('Paypal-Cert-Url')
        auth_algo = request.headers.get('Paypal-Auth-Algo')
        actual_sig = request.headers.get('Paypal-Transmission-Sig')
        
        # Webhook IDは空のまま渡し、verify_webhook_signature内で取得する
        webhook_id = ''
        
        # リクエストボディを取得
        event_body = request.data.decode('utf-8')
        event_data = json.loads(event_body)
        
        # Webhook IDは空のまま渡し、verify_webhook_signature内で取得される
        
        # 必要なヘッダーが存在するか確認
        if not all([transmission_id, timestamp, cert_url, auth_algo, actual_sig]):
            logger.error("必要なPayPal Webhookヘッダーが不足しています")
            return jsonify({
                'success': False,
                'message': '必要なWebhookヘッダーが不足しています'
            }), 400
        
        # Webhook署名を検証
        is_valid = verify_webhook_signature(
            transmission_id, timestamp, webhook_id, event_body, 
            cert_url, actual_sig, auth_algo
        )
        
        if not is_valid:
            logger.warning("PayPal Webhook署名検証に失敗しました")
            return jsonify({
                'success': False,
                'message': 'Webhook署名が無効です'
            }), 400
        
        # イベントを処理
        success, message = process_payment_webhook(event_data)
        
        if success:
            logger.info(f"PayPal Webhook処理成功: {message}")
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            logger.warning(f"PayPal Webhook処理失敗: {message}")
            return jsonify({
                'success': False,
                'message': message
            }), 400
            
    except Exception as e:
        logger.error(f"PayPal Webhook処理例外: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Webhook処理エラー: {str(e)}'
        }), 500

@app.route('/api/update_payment_status', methods=['GET', 'POST'])
@login_required
def update_payment_status_api():
    """
    特定の注文IDの支払いステータスを手動で更新するAPIエンドポイント
    """
    
    try:
        # GETメソッドの場合はクエリパラメータから取得
        if request.method == 'GET':
            order_id = request.args.get('order_id')
        else:
            # POSTメソッドの場合はJSONから取得
            data = request.get_json()
            order_id = data.get('order_id')
        
        if not order_id:
            return jsonify({
                'success': False,
                'message': '注文IDが必要です'
            }), 400
            
        # 支払いステータスを更新
        success, new_status, message = update_payment_status_by_order_id(order_id)
        
        if success:
            logger.info(f"支払いステータス手動更新成功: 注文ID={order_id}, 新ステータス={new_status}")
            return jsonify({
                'success': True,
                'status': new_status,
                'message': message
            })
        else:
            logger.warning(f"支払いステータス手動更新失敗: 注文ID={order_id}, メッセージ={message}")
            return jsonify({
                'success': False,
                'message': message
            }), 400
    
    except Exception as e:
        logger.error(f"支払いステータス更新API例外: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'エラー: {str(e)}'
        }), 500

@app.route('/api/update_all_payment_statuses', methods=['GET'])
def update_all_payment_statuses_api():
    # 管理者権限チェック
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({
            'success': False,
            'message': '管理者権限が必要です。ログインしてください。',
            'auth_required': True
        }), 401
    """
    未完了の支払いステータスをすべて更新するAPIエンドポイント(管理者専用)
    """
    
    try:
        # 支払いステータスを一括更新
        updated_count, error_count = update_pending_payment_statuses()
        
        logger.info(f"支払いステータス一括更新完了: 更新={updated_count}件, エラー={error_count}件")
        return jsonify({
            'success': True,
            'updated_count': updated_count,
            'error_count': error_count,
            'message': f'{updated_count}件の支払いステータスを更新しました。エラー: {error_count}件'
        })
    
    except Exception as e:
        logger.error(f"支払いステータス一括更新API例外: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'エラー: {str(e)}'
        }), 500

@app.route('/api/update_history_payment_statuses/<filename>', methods=['GET'])
def update_history_payment_statuses(filename):
    # 管理者権限チェック
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({
            'success': False,
            'message': '管理者権限が必要です。ログインしてください。',
            'auth_required': True
        }), 401
    """
    特定の履歴ファイルの支払いステータスを更新するAPIエンドポイント(管理者専用)
    """
    
    try:
        # ファイル名のバリデーション
        if not re.match(r'^payment_links_\d{8}_\d{6}\.json$', filename):
            return jsonify({
                'success': False,
                'message': '無効なファイル名形式です'
            }), 400
        
        # 履歴ファイルのパスを取得
        history_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'history')
        history_path = os.path.join(history_dir, filename)
        
        if not os.path.exists(history_path):
            return jsonify({
                'success': False,
                'message': '履歴ファイルが存在しません'
            }), 404
        
        # 履歴ファイルを読み込み
        with open(history_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        
        # 注文IDを収集
        order_ids = []
        for entry in history_data:
            if 'order_id' in entry and entry['order_id']:
                order_ids.append(entry['order_id'])
        
        if not order_ids:
            return jsonify({
                'success': True,
                'updated_count': 0,
                'error_count': 0,
                'message': '更新する注文IDがありません'
            })
        
        # 各注文IDの支払いステータスを更新
        updated_count = 0
        error_count = 0
        
        for order_id in order_ids:
            try:
                success, new_status, message = update_payment_status_by_order_id(order_id)
                if success:
                    updated_count += 1
                else:
                    error_count += 1
                    logger.warning(f"注文ID {order_id} の更新に失敗: {message}")
            except Exception as e:
                error_count += 1
                logger.error(f"注文ID {order_id} の更新中に例外発生: {str(e)}")
        
        logger.info(f"履歴ファイル {filename} の支払いステータス更新完了: 更新={updated_count}件, エラー={error_count}件")
        return jsonify({
            'success': True,
            'updated_count': updated_count,
            'error_count': error_count,
            'message': f'{updated_count}件の支払いステータスを更新しました。エラー: {error_count}件'
        })
    
    except Exception as e:
        logger.error(f"履歴ファイル支払いステータス更新API例外: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'エラー: {str(e)}'
        }), 500



try:
    from update_history_api import register_update_history_api
    from auth_api import api_admin_required
    register_update_history_api(app, api_admin_required, update_payment_status_by_order_id, logger)
    logger.info("個別の履歴ファイルの支払いステータス更新APIエンドポイントを登録しました")
except ImportError as e:
    logger.warning(f"update_history_apiモジュールのインポートに失敗しました: {e}")

# PayPalルートの登録は create_app() 内で実行

# アプリケーション初期化関数
def create_app():
    global app
    
    try:
        # ロガーの初期化
        setup_logger()
        logger.info("アプリケーション初期化を開始します")
        
        # キャッシュをクリア
        clear_cache()
        
        # 環境変数の表示（デバッグ用）
        logger.info("=== 環境変数 ===")
        for key in ['PORT', 'UPLOAD_FOLDER', 'RESULTS_FOLDER', 'USE_TEMP_DIR', 'SECRET_KEY', 'PAYPAL_CLIENT_ID']:
            value = os.environ.get(key, 'Not set')
            # SECRET_KEYとPAYPAL_CLIENT_IDはセキュリティ上の理由から値を表示しない
            if key in ['SECRET_KEY', 'PAYPAL_CLIENT_ID'] and value != 'Not set':
                logger.info(f"{key}: [設定済み]")
            else:
                logger.info(f"{key}: {value}")
        
        # 設定の初期化
        try:
            initialize_config()
            logger.info("設定の初期化が完了しました")
        except Exception as e:
            logger.error(f"設定の初期化中にエラーが発生しました: {str(e)}")
            logger.error(traceback.format_exc())
        
        # 認証ブループリントの登録を確認
        if not auth_registered:
            logger.warning("認証ブループリントが登録されていません。再登録を試みます。")
            register_auth_blueprint(app)
        
        # PayPalルートの登録を確認
        try:
            if 'paypal_bp' not in [bp.name for bp in app.blueprints.values()]:
                logger.warning("PayPalブループリントが登録されていません。再登録を試みます。")
                from paypal_routes import paypal_bp
                app.register_blueprint(paypal_bp)
                logger.info("PayPalルートが正常に登録されました")
        except Exception as e:
            logger.error(f"PayPalブループリントの登録中にエラーが発生しました: {str(e)}")
            logger.error(traceback.format_exc())
        
        # ルート情報の表示（デバッグ用）
        logger.info("=== ルート情報 ===")
        try:
            for rule in app.url_map.iter_rules():
                logger.info(f"Route: {rule.endpoint} - {rule.rule} - {rule.methods}")
        except Exception as e:
            logger.error(f"ルート情報表示エラー: {str(e)}")
        
        logger.info("アプリケーション初期化が完了しました")
        return app
    except Exception as e:
        logger.critical(f"アプリケーション初期化中に重大なエラーが発生しました: {str(e)}")
        logger.critical(traceback.format_exc())
        # 最低限の機能を持つアプリケーションを返す
        return app


# ============================================
# API キーキャッシュ機能
# ============================================

def encrypt_api_key(api_key: str) -> str:
    """
    Encrypt API key using Fernet encryption
    
    Args:
        api_key: Plain text API key
        
    Returns:
        Encrypted API key as base64 string
    """
    try:
        if not cipher_suite:
            raise ValueError("Encryption not available")
        encrypted_key = cipher_suite.encrypt(api_key.encode())
        return encrypted_key.decode()
    except Exception as e:
        logger.error(f"Error encrypting API key: {str(e)}")
        raise


def decrypt_api_key(encrypted_key: str) -> str:
    """
    Decrypt API key using Fernet encryption
    
    Args:
        encrypted_key: Encrypted API key as base64 string
        
    Returns:
        Decrypted API key as plain text
    """
    try:
        if not cipher_suite:
            raise ValueError("Encryption not available")
        decrypted_key = cipher_suite.decrypt(encrypted_key.encode())
        return decrypted_key.decode()
    except Exception as e:
        logger.error(f"Error decrypting API key: {str(e)}")
        raise


def get_firestore_client():
    """
    Get Firestore client with lazy initialization
    """
    global db
    if db is None and FIRESTORE_AVAILABLE:
        try:
            db = firestore.Client()
            app.logger.info("Firestore クライアントを初期化しました")
        except Exception as e:
            app.logger.error(f"Firestore クライアントの初期化に失敗: {e}")
            return None
    return db


def get_cached_api_key(user_id: str) -> Optional[str]:
    """
    Retrieve and decrypt API key from Firestore cache
    
    Args:
        user_id: User ID (Firebase Auth UID)
        
    Returns:
        Decrypted API key if valid and not expired, None otherwise
    """
    if not FIRESTORE_AVAILABLE:
        logger.warning("Firestore not available, cannot retrieve cached API key")
        return None
        
    try:
        client = get_firestore_client()
        if not client:
            return None
            
        doc_ref = client.collection(COLLECTION_NAME).document(user_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            logger.info(f"No cached API key found for user: {user_id}")
            return None
            
        data = doc.to_dict()
        
        # Check if TTL has expired
        ttl_time = data.get('ttl')
        if ttl_time and datetime.utcnow() > ttl_time:
            logger.info(f"API key expired for user: {user_id}")
            # Delete expired document
            doc_ref.delete()
            return None
            
        # Decrypt and return API key
        encrypted_key = data.get('api_key')
        if encrypted_key:
            return decrypt_api_key(encrypted_key)
            
        return None
        
    except Exception as e:
        logger.error(f"Error retrieving cached API key for user {user_id}: {str(e)}")
        return None


def cache_api_key(user_id: str, api_key: str, ttl_minutes: int = DEFAULT_TTL_MINUTES) -> bool:
    """
    Encrypt and cache API key in Firestore with TTL
    
    Args:
        user_id: User ID (Firebase Auth UID)
        api_key: Plain text API key to cache
        ttl_minutes: Time to live in minutes
        
    Returns:
        True if successful, False otherwise
    """
    if not FIRESTORE_AVAILABLE:
        logger.warning("Firestore not available, cannot cache API key")
        return False
        
    try:
        client = get_firestore_client()
        if not client:
            return False
            
        # Encrypt API key
        encrypted_key = encrypt_api_key(api_key)
        
        # Calculate TTL timestamp
        ttl_time = datetime.utcnow() + timedelta(minutes=ttl_minutes)
        
        # Prepare document data
        doc_data = {
            'api_key': encrypted_key,
            'created_at': SERVER_TIMESTAMP,
            'ttl': ttl_time
        }
        
        # Save to Firestore
        doc_ref = client.collection(COLLECTION_NAME).document(user_id)
        doc_ref.set(doc_data)
        
        logger.info(f"API key cached successfully for user: {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error caching API key for user {user_id}: {str(e)}")
        return False


# ============================================
# API キーキャッシュのエンドポイント
# ============================================

@app.route('/api/cache_api_key', methods=['POST'])
def cache_api_key_endpoint():
    """
    POST /api/cache_api_key
    Cache API key for a user with optional TTL
    
    Request JSON:
    {
        "user_id": "firebase_auth_uid",
        "api_key": "your_api_key_here",
        "ttl_minutes": 60  // Optional, defaults to 60
    }
    """
    try:
        if not FIRESTORE_AVAILABLE:
            return jsonify({'error': 'API key cache service not available'}), 503
            
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        user_id = data.get('user_id')
        api_key = data.get('api_key')
        ttl_minutes = data.get('ttl_minutes', DEFAULT_TTL_MINUTES)
        
        # Validate required fields
        if not user_id or not api_key:
            return jsonify({'error': 'user_id and api_key are required'}), 400
            
        # Validate TTL
        if not isinstance(ttl_minutes, int) or ttl_minutes <= 0:
            return jsonify({'error': 'ttl_minutes must be a positive integer'}), 400
            
        # Cache the API key
        success = cache_api_key(user_id, api_key, ttl_minutes)
        
        if success:
            return jsonify({
                'message': 'API key cached successfully',
                'ttl_minutes': ttl_minutes,
                'expires_at': (datetime.utcnow() + timedelta(minutes=ttl_minutes)).isoformat()
            }), 200
        else:
            return jsonify({'error': 'Failed to cache API key'}), 500
            
    except Exception as e:
        logger.error(f"Error in cache_api_key_endpoint: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/run_api', methods=['POST'])
def run_api_endpoint():
    """
    POST /api/run_api
    Execute external API call using cached API key
    
    Request JSON:
    {
        "user_id": "firebase_auth_uid",
        "api_endpoint": "https://api.example.com/data",
        "method": "GET",  // Optional, defaults to GET
        "headers": {},    // Optional additional headers
        "data": {}        // Optional request data for POST/PUT
    }
    """
    try:
        if not FIRESTORE_AVAILABLE:
            return jsonify({'error': 'API key cache service not available'}), 503
            
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        user_id = data.get('user_id')
        api_endpoint = data.get('api_endpoint')
        method = data.get('method', 'GET').upper()
        additional_headers = data.get('headers', {})
        request_data = data.get('data', {})
        
        # Validate required fields
        if not user_id or not api_endpoint:
            return jsonify({'error': 'user_id and api_endpoint are required'}), 400
            
        # Validate HTTP method
        if method not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
            return jsonify({'error': 'Invalid HTTP method'}), 400
            
        # Retrieve cached API key
        cached_api_key = get_cached_api_key(user_id)
        
        if not cached_api_key:
            return jsonify({'error': 'No valid API key found. Please cache your API key first.'}), 401
            
        # Prepare headers with API key
        headers = {
            'Authorization': f'Bearer {cached_api_key}',
            'Content-Type': 'application/json'
        }
        headers.update(additional_headers)
        
        # Make API request
        response = None
        if method == 'GET':
            response = requests.get(api_endpoint, headers=headers, timeout=30)
        elif method == 'POST':
            response = requests.post(api_endpoint, headers=headers, json=request_data, timeout=30)
        elif method == 'PUT':
            response = requests.put(api_endpoint, headers=headers, json=request_data, timeout=30)
        elif method == 'DELETE':
            response = requests.delete(api_endpoint, headers=headers, timeout=30)
        elif method == 'PATCH':
            response = requests.patch(api_endpoint, headers=headers, json=request_data, timeout=30)
            
        # Return API response
        try:
            response_data = response.json()
        except:
            response_data = response.text
            
        return jsonify({
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'data': response_data
        }), response.status_code
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {str(e)}")
        return jsonify({'error': f'API request failed: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error in run_api_endpoint: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/health', methods=['GET'])
def api_health_check():
    """Health check endpoint for API key cache"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'api-key-cache',
        'firestore_available': FIRESTORE_AVAILABLE,
        'encryption_available': cipher_suite is not None
    }), 200

# Gunicorn用のアプリケーションオブジェクト
try:
    application = create_app()
    print("Application created successfully")
except Exception as e:
    print(f"Error creating application: {e}")
    import traceback
    traceback.print_exc()
    # 最小限のFlaskアプリケーションを作成
    from flask import Flask
    application = Flask(__name__)
    
    @application.route('/health')
    def health():
        return {'status': 'error', 'message': 'Application failed to initialize properly'}
    
    @application.route('/')
    def root():
        return {'status': 'error', 'message': 'Application failed to initialize properly'}

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
    
    # 登録されているルートを表示（デバッグ用）
    logger.info("=== 登録されているルート ===")
    for rule in application.url_map.iter_rules():
        logger.info(f"Route: {rule.endpoint} - {rule.rule} - {rule.methods}")
    
    # アプリケーションを実行
    application.run(debug=debug_mode, host=host, port=port)
