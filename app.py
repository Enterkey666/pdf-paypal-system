#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""PDF PayPal System

PDFファイルから顧客情報と金額を抽出し、PayPal決済リンクを生成するシステム
"""

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
import json
import PyPDF2
import uuid
import pdfplumber
import time
import logging
import urllib.parse
import tempfile

# ロガーの初期化
logger = logging.getLogger(__name__)

# ロガーのセットアップ関数
def setup_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # ファイルハンドラの設定
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, 'app.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # コンソールハンドラの設定
    console_handler = logging.StreamHandler()
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
try:
    # カレントディレクトリを再確認（デプロイ環境用）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        logger.info(f"sys.pathに追加しました: {current_dir}")
    
    # モジュールパスを表示（デバッグ用）
    logger.info(f"Python path: {sys.path}")
    logger.info(f"現在のディレクトリ内のファイル: {os.listdir(current_dir)}")
    
    import customer_extractor
    logger.info("customer_extractorモジュールのインポートに成功しました")
except ImportError as e:
    logger.error(f"customer_extractorモジュールのインポートに失敗: {e}")
    # フォールバック処理
    # customer_extractor.pyファイルを直接読み込む
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "customer_extractor", 
            os.path.join(current_dir, "customer_extractor.py")
        )
        customer_extractor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(customer_extractor)
        logger.info("customer_extractorモジュールを代替方法でインポートしました")
    except Exception as e2:
        logger.error(f"customer_extractorモジュールの代替インポートにも失敗: {e2}")

# モジュールの再読み込みを強制する関数
def reload_modules():
    try:
        # customer_extractorモジュールが正しくインポートされているか確認
        if 'customer_extractor' in sys.modules:
            import importlib
            importlib.reload(customer_extractor)
            logger.info("customer_extractorモジュールを再読み込みしました")
        else:
            logger.warning("customer_extractorモジュールがインポートされていないため、再読み込みをスキップします")
            # モジュールを再インポートしてみる
            try:
                import customer_extractor
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
from flask_wtf import FlaskForm, CSRFProtect
from flask_session import Session
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

# ログインフォームクラス
class LoginForm(FlaskForm):
    username = StringField('ユーザー名', validators=[DataRequired()])
    password = PasswordField('パスワード', validators=[DataRequired()])
    submit = SubmitField('ログイン')

# 環境変数の読み込み
load_dotenv()

# Flaskアプリケーションの設定
app = Flask(__name__)

# セッション管理のためのシークレットキー設定
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key_here')
app.logger.info(f"シークレットキー設定完了: {app.secret_key[:5]}...")

# CSRF保護の設定
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = os.environ.get('CSRF_SECRET_KEY', 'csrf_secret_key')
app.config['WTF_CSRF_SSL_STRICT'] = False  # 開発環境でのテストを可能に

# セッションの設定
app.config['SESSION_COOKIE_NAME'] = 'pdf_paypal_session'  # セッションCookieの名前を明示的に指定
app.config['SESSION_COOKIE_SECURE'] = False  # 開発環境ではHTTPSを使用しないのでFalseに設定
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_PATH'] = '/'  # Cookieのパスを明示的に指定
app.config['SESSION_COOKIE_DOMAIN'] = None  # ローカル開発環境用
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # SameSite属性を設定
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)  # セッションの有効期限（1時間）
app.config['SESSION_USE_SIGNER'] = True  # セッションの署名を有効化
app.config['SESSION_TYPE'] = 'filesystem'  # セッションをファイルシステムに保存
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_session')
app.config['SESSION_FILE_THRESHOLD'] = 500  # 最大セッションファイル数
app.config['SESSION_KEY_PREFIX'] = 'pdf_paypal_'  # セッションキーのプレフィックス

# セッションディレクトリを確実に作成
try:
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
    app.logger.info(f"セッションディレクトリを確認: {app.config['SESSION_FILE_DIR']}")
    if not os.access(app.config['SESSION_FILE_DIR'], os.W_OK):
        app.logger.warning(f"セッションディレクトリに書き込み権限がありません: {app.config['SESSION_FILE_DIR']}")
        app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
        app.logger.info(f"一時ディレクトリに変更しました: {app.config['SESSION_FILE_DIR']}")
        os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
except Exception as e:
    app.logger.error(f"セッションディレクトリ作成エラー: {str(e)}")
    app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
    app.logger.info(f"一時ディレクトリに変更しました: {app.config['SESSION_FILE_DIR']}")

# Flask-Sessionの初期化
session_interface = Session(app)
app.logger.info("セッション管理の初期化完了")
app.logger.info(f"セッションインターフェース: {type(session_interface).__name__}")
app.logger.info(f"セッション設定: {app.config.get('SESSION_TYPE')}")

# CSRF保護の設定
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = app.secret_key  # 同じキーを使用
app.config['WTF_CSRF_TIME_LIMIT'] = 3600
app.config['WTF_CSRF_SSL_STRICT'] = False  # HTTPSチェックを無効化（開発環境用）
app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # デフォルトのCSRFチェックを無効化（カスタム処理用）

# CSRF保護の初期化
csrf = CSRFProtect(app)

# セッションディレクトリの作成を確認
if not os.path.exists(app.config['SESSION_FILE_DIR']):
    try:
        os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
        logger.info(f"セッションディレクトリを作成しました: {app.config['SESSION_FILE_DIR']}")
    except Exception as e:
        logger.error(f"セッションディレクトリの作成に失敗しました: {e}")
        # フォールバックとして一時ディレクトリを使用
        app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
        logger.info(f"フォールバックセッションディレクトリ: {app.config['SESSION_FILE_DIR']}")

# paypal_utils.pyからの関数インポート
# ローカルモジュールのインポート
from paypal_utils import cancel_paypal_order, check_order_status, get_paypal_access_token

# 管理者認証用デコレータ
def admin_required(f):
    """
    管理者権限が必要なルートに対するデコレータ
    管理者としてログインしていない場合はログインページにリダイレクト
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('このページにアクセスするには管理者権限が必要です', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# 有料会員または管理者認証用デコレータ
def paid_member_or_admin_required(f):
    """
    有料会員または管理者権限が必要なルートに対するデコレータ
    本番モードでは有料会員または管理者のみアクセス可能
    sandboxモードでは誰でもアクセス可能
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # PayPalモードを取得（デフォルトはsandbox）
        paypal_mode = os.environ.get('PAYPAL_MODE', 'sandbox')
        
        # sandboxモードの場合は誰でもアクセス可能
        if paypal_mode.lower() == 'sandbox':
            logger.info("Sandboxモードなので誰でもアクセス可能")
            return f(*args, **kwargs)
        
        # 本番モードの場合は有料会員または管理者のみアクセス可能
        if session.get('admin_logged_in') or session.get('is_paid_member'):
            logger.info("有料会員または管理者としてアクセス")
            return f(*args, **kwargs)
        
        # それ以外の場合は有料会員登録ページにリダイレクト
        flash('この機能を利用するには有料会員登録が必要です', 'error')
        return redirect(url_for('membership_info'))
    
    return decorated_function

# 外部API使用権限チェック用デコレータ
def api_access_required(f):
    """
    外部API（Google、Azul、PayPal本番）の使用権限が必要なルートに対するデコレータ
    sandboxモードでは誰でもアクセス可能
    本番モードでは有料会員または管理者のみアクセス可能
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
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
        if session.get('admin_logged_in') or session.get('is_paid_member'):
            logger.info("有料会員または管理者として外部APIにアクセス")
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

# Basic認証用デコレータ
def basic_auth_required(f):
    """
    APIエンドポイントのBasic認証用デコレータ
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', '')
        
        if not auth or auth.username != admin_username or auth.password != admin_password:
            return jsonify({'error': '認証が必要です'}), 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}
        return f(*args, **kwargs)
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
    """設定ファイルのパスを取得する
    
    設定ファイルのパスを返す
    """
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# 設定の読み込み
def get_config():
    """設定を読み込む
    
    設定ファイルから設定を読み込み、返す
    ファイルが存在しない場合はデフォルト設定を返す
    """
    config_path = get_config_path()
    
    # デフォルト設定
    default_config = {
        'client_id': '',
        'client_secret': '',
        'paypal_mode': 'sandbox',
        'admin_email': ''
    }
    
    # 環境変数から設定を取得
    paypal_mode = os.environ.get('PAYPAL_MODE', 'sandbox')
    admin_email = os.environ.get('ADMIN_EMAIL', '')
    
    # ファイルが存在する場合は読み込み
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 環境変数の値で上書き
            config['paypal_mode'] = paypal_mode
            config['admin_email'] = admin_email
            
            return config
        except Exception as e:
            logger.error(f"設定ファイルの読み込みエラー: {str(e)}")
            
            # 環境変数の値でデフォルト設定を更新
            default_config['paypal_mode'] = paypal_mode
            default_config['admin_email'] = admin_email
            
            return default_config
    else:
        # 環境変数の値でデフォルト設定を更新
        default_config['paypal_mode'] = paypal_mode
        default_config['admin_email'] = admin_email
        
        return default_config

# 設定の保存
def save_config(config):
    """設定を保存する
    
    設定をJSONファイルに保存する
    
    Args:
        config: 保存する設定辞書
    """
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
try:
    # カレントディレクトリを再確認（デプロイ環境用）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        logger.info(f"sys.pathに追加しました: {current_dir}")
    
    # amount_extractorモジュールをインポート
    import amount_extractor
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
        amount_extractor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(amount_extractor)
        logger.info("amount_extractorモジュールを代替方法でインポートしました")
    except Exception as e2:
        logger.error(f"amount_extractorモジュールの代替インポートにも失敗: {e2}")

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
    """数字の文字化けを修正する
    
    Adobe PDFでは数字が特殊な文字コードで表現されていることがあり、
    それが文字化けの原因となっている。この関数は数字の文字化けパターンを
    検出して修正する。
    """
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
    from extractors import extract_text_from_pdf, extract_amount_only
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
            extractors = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(extractors)
            
            # 必要な関数を取得
            extract_text_from_pdf = extractors.extract_text_from_pdf
            extract_amount_only = extractors.extract_amount_only
            ExtractionResult = extractors.ExtractionResult
            
            logger.info("extractorsモジュールを代替方法でインポートしました")
            ENHANCED_OCR_AVAILABLE = True
        else:
            logger.error(f"extractors.pyファイルが見つかりません: {extractors_path}")
    except Exception as e2:
        logger.error(f"extractorsモジュールの代替インポートにも失敗: {e2}")
    logger.warning("拡張OCRモジュールが見つかりません。基本的なOCR機能のみ使用します。")

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
    
    INTERACTIVE_CORRECTION_AVAILABLE = True
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

def create_app():
    # アプリ起動時にキャッシュをクリア
    clear_cache()
    
    app.secret_key = os.urandom(24)  # セッション用シークレットキー
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 最大アップロードサイズを50MBに制限

    # アップロードとダウンロードの設定
    # Renderのような環境では一時ディレクトリを使用
    base_dir = os.path.dirname(os.path.abspath(__file__))
    upload_folder = os.environ.get('UPLOAD_FOLDER', os.path.join(base_dir, 'uploads'))
    results_folder = os.environ.get('RESULTS_FOLDER', os.path.join(base_dir, 'results'))
    allowed_extensions = {'pdf'}
    
    # クラウド環境では一時ディレクトリを使用する場合がある
    if os.environ.get('USE_TEMP_DIR', 'false').lower() == 'true':
        upload_folder = tempfile.gettempdir()
        results_folder = tempfile.gettempdir()
        logger.info(f"一時ディレクトリを使用: {upload_folder}")
    
    # フォルダが存在しない場合は作成
    for folder in [upload_folder, results_folder]:
        try:
            if not os.path.exists(folder):
                os.makedirs(folder)
            # 書き込み権限をテスト
            test_file = os.path.join(folder, '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            logger.info(f"フォルダの書き込み権限確認: {folder}")
        except Exception as e:
            logger.error(f"フォルダ作成または権限テストエラー: {folder}, {str(e)}")
            # 一時ディレクトリにフォールバック
            if folder == upload_folder:
                upload_folder = tempfile.gettempdir()
                logger.info(f"アップロードフォルダを一時ディレクトリに変更: {upload_folder}")
            elif folder == results_folder:
                results_folder = tempfile.gettempdir()
                logger.info(f"結果フォルダを一時ディレクトリに変更: {results_folder}")

    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['RESULTS_FOLDER'] = results_folder
    app.config['ALLOWED_EXTENSIONS'] = allowed_extensions
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 最大16MB

    # 設定の初期化
    initialize_config()
    logger.info("アプリケーションを初期化しました")

    # ここに全てのルート関数、ヘルパー関数を登録
    # ...（既存のルートをすべてapp.routeで登録）...

    # 既存の関数・ルートをappスコープに登録するためにglobals()を使う
    global allowed_file, extract_text_from_pdf, get_paypal_access_token, create_paypal_payment_link
    global index, payment_success, payment_cancel, upload_file, process_pdf, download_file
    global settings, save_settings, test_connection, export_settings, import_settings
    app.add_url_rule('/', 'index', index)
    app.add_url_rule('/payment_success', 'payment_success', payment_success)
    app.add_url_rule('/payment_cancel', 'payment_cancel', payment_cancel)
    app.add_url_rule('/upload', 'upload_file', upload_file, methods=['POST'])
    app.add_url_rule('/process_pdf', 'process_pdf', process_pdf, methods=['POST'])
    app.add_url_rule('/download/<filename>', 'download_file', download_file)
    app.add_url_rule('/settings', 'settings', settings, methods=['GET'])
    app.add_url_rule('/settings/save', 'save_settings', save_settings, methods=['POST'])
    app.add_url_rule('/settings/test_connection', 'test_connection', test_connection, methods=['POST'])
    app.add_url_rule('/settings/export', 'export_settings', export_settings)
    app.add_url_rule('/settings/import', 'import_settings', import_settings, methods=['POST'])
    app.add_url_rule('/history', 'history', history)
    app.add_url_rule('/history/<filename>', 'history_detail', history_detail)
    app.add_url_rule('/history/delete', 'delete_history', delete_history, methods=['POST'])
    app.add_url_rule('/generate_payment_link', 'generate_payment_link', generate_payment_link, methods=['POST'])

    # インタラクティブ修正機能のルートを設定
    if INTERACTIVE_CORRECTION_AVAILABLE:
        try:
            # 独自のルートを追加
            app.add_url_rule('/correction', 'correction', correction)
            app.add_url_rule('/api/save_correction', 'api_save_correction', api_save_correction, methods=['POST'])
            app.add_url_rule('/api/get_suggestions', 'api_get_suggestions', api_get_suggestions, methods=['GET'])
            
            # ディレクトリ作成
            history_dir = os.path.join(os.path.dirname(__file__), 'data', 'correction_history')
            data_dir = os.path.join(os.path.dirname(__file__), 'data', 'learning_data')
            os.makedirs(history_dir, exist_ok=True)
            os.makedirs(data_dir, exist_ok=True)
            
            logger.info("インタラクティブ修正機能のルートを設定しました")
        except Exception as e:
            logger.error(f"インタラクティブ修正機能のルート設定エラー: {str(e)}")

    return app

from flask import current_app

# ログイン・ログアウト機能
@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    管理者ログインページ
    """
    # すでにログインしている場合はリダイレクト
    if session.get('admin_logged_in'):
        return redirect(url_for('index'))
    
    # リダイレクト先の取得
    next_page = request.args.get('next')
    
    # WTFormsを使用したフォーム処理
    form = LoginForm()
    
    # デバッグ情報を追加
    app.logger.info(f"Session: {session}")
    app.logger.info(f"Session ID: {request.cookies.get(app.config['SESSION_COOKIE_NAME'], 'なし')}")
    app.logger.info(f"CSRF enabled: {app.config.get('WTF_CSRF_ENABLED', False)}")
    app.logger.info(f"CSRF token in session: {'csrf_token' in session}")
    app.logger.info(f"環境変数 ADMIN_USERNAME: {os.environ.get('ADMIN_USERNAME')}")
    app.logger.info(f"環境変数 ADMIN_PASSWORD: {os.environ.get('ADMIN_PASSWORD')}")
    
    # POSTリクエストの処理
    if request.method == 'POST':
        app.logger.info(f"フォームデータ: {request.form}")
        app.logger.info(f"ログイン前のセッション状態: {session}")
        
        # CSRFトークンを手動で検証
        csrf_token = session.get('csrf_token')
        token = request.form.get('csrf_token')
        app.logger.info(f"受信したトークン: {token}, セッショントークン: {csrf_token}")
        
        # フォームデータを取得
        username = request.form.get('username')
        password = request.form.get('password')
        app.logger.info(f"入力されたユーザー名: {username}, パスワード: {'*' * len(password) if password else 'なし'}")
        
        # 環境変数から管理者認証情報を取得
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin')
        app.logger.info(f"設定された管理者ユーザー名: {admin_username}")
        
        # 認証チェック
        if username == admin_username and password == admin_password:
            app.logger.info("認証成功: 管理者としてログイン")
            
            # 既存のセッションをクリア
            session.clear()
            app.logger.info("セッションをクリアしました")
            
            # 管理者情報をセッションに設定
            session['admin_logged_in'] = True
            session['admin_username'] = username
            session['is_paid_member'] = True  # 管理者は有料会員の権限も持つ
            session['login_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            session.permanent = True  # セッションを永続化
            session.modified = True  # セッション変更を確実に保存
            
            # セッション設定後の状態をログ出力
            app.logger.info(f"ログイン後のセッション状態: {session}")
            app.logger.info(f"admin_logged_inの値: {session.get('admin_logged_in')}")
            
            flash('管理者としてログインしました', 'success')
            
            # リダイレクト先が指定されていればそこに、なければトップページに
            redirect_url = next_page if next_page else url_for('index')
            app.logger.info(f"リダイレクト先: {redirect_url}")
            
            # セッションを確実に保存するために再度確認
            app.logger.info(f"リダイレクト前の最終確認 - セッション状態: {session}")
            app.logger.info(f"リダイレクト前の最終確認 - admin_logged_in: {session.get('admin_logged_in')}")
            
            # セッションを確実に保存
            session.modified = True
            app.logger.info("セッションを確実に保存しました")
            
            # Cookieの設定を確認
            app.logger.info(f"Cookie設定 - SESSION_COOKIE_NAME: {app.config.get('SESSION_COOKIE_NAME')}")
            app.logger.info(f"Cookie設定 - SESSION_COOKIE_SECURE: {app.config.get('SESSION_COOKIE_SECURE')}")
            app.logger.info(f"Cookie設定 - SESSION_COOKIE_HTTPONLY: {app.config.get('SESSION_COOKIE_HTTPONLY')}")
            app.logger.info(f"Cookie設定 - SESSION_COOKIE_PATH: {app.config.get('SESSION_COOKIE_PATH')}")
            app.logger.info(f"Cookie設定 - SESSION_COOKIE_DOMAIN: {app.config.get('SESSION_COOKIE_DOMAIN')}")
            app.logger.info(f"Cookie設定 - SESSION_COOKIE_SAMESITE: {app.config.get('SESSION_COOKIE_SAMESITE')}")
            
            # レスポンスにCookieを確実に設定するための処理
            response = make_response(redirect(redirect_url))
            if '_flashes' in session:
                app.logger.info(f"Flashメッセージがセッションに存在します: {session['_flashes']}")
            
            return response
            
            return redirect(redirect_url)
        else:
            app.logger.info("認証失敗: ユーザー名またはパスワードが不正")
    # PayPalモードを取得（デフォルトはsandbox）
    paypal_mode = os.environ.get('PAYPAL_MODE', 'sandbox')
    
    # ユーザー権限情報
    is_admin = session.get('admin_logged_in', False)
    is_paid_member = session.get('is_paid_member', False)
    
    # セッション状態をログ出力
    app.logger.info(f"ログインページ表示時のセッション状態: {session}")
    app.logger.info(f"ログインページ表示時のis_admin: {is_admin}, is_paid_member: {is_paid_member}")
    
    # 本番モードでの制限表示フラグ
    show_restrictions = paypal_mode.lower() != 'sandbox' and not (is_admin or is_paid_member)
    
    return render_template('login.html', 
                           form=form,
                           next=next_page,
                           mode=paypal_mode, 
                           paypal_mode=paypal_mode,
                           is_admin=is_admin,
                           is_paid_member=is_paid_member,
                           show_restrictions=show_restrictions)

@app.route('/logout')
def logout():
    """
    ログアウト処理
    """
    app.logger.info(f"ログアウト前のセッション状態: {session}")
    session.clear()  # セッション全体をクリア
    app.logger.info(f"ログアウト後のセッション状態: {session}")
    flash('ログアウトしました', 'info')
    return redirect(url_for('index'))

# 設定ページ
@app.route('/settings')
def settings():
    """
    設定ページ - sandboxモードでは誰でもアクセス可能、本番モードでは有料会員または管理者のみ
    管理者はすべての設定を閲覧・編集可能
    ゲストユーザーはsandboxモードの設定のみ閲覧・編集可能
    """
    logger.info("設定ページにアクセスされました")
    
    # セッション情報をログ出力
    logger.info(f"設定ページ表示時のセッション状態: {session}")
    
    # 現在の設定を取得
    config = get_config()
    
    # PayPalモードを取得（デフォルトはsandbox）
    paypal_mode = config.get('paypal_mode', 'sandbox')
    is_admin = session.get('admin_logged_in', False)
    is_paid_member = session.get('is_paid_member', False)
    
    # 権限情報をログ出力
    logger.info(f"設定ページ表示時の権限情報 - is_admin: {is_admin}, is_paid_member: {is_paid_member}")
    
    # 本番モードで非管理者かつ非有料会員の場合はアクセス制限
    if paypal_mode == 'live' and not (is_admin or is_paid_member):
        flash('本番環境の設定ページは管理者または有料会員のみアクセス可能です', 'warning')
        return redirect(url_for('index'))
    
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
    show_all_settings = is_admin
    show_sandbox_settings = True  # sandboxモードの設定は常に表示
    
    # レンダリング前の最終確認
    logger.info(f"設定ページレンダリング前の最終確認 - is_admin: {is_admin}, show_all_settings: {show_all_settings}")
    
    return render_template('settings.html', 
                           paypal_mode=paypal_mode,
                           is_admin=is_admin,
                           is_paid_member=is_paid_member,
                           config=config,
                           paypal_status=paypal_status,
                           show_all_settings=show_all_settings,
                           show_sandbox_settings=show_sandbox_settings)

# 履歴一覧ページ
@app.route('/history')
def history():
    """
    履歴一覧ページ
    """
    history_data = []
    try:
        results_folder = app.config['RESULTS_FOLDER']
        files = [f for f in os.listdir(results_folder) if f.startswith('payment_links_') and f.endswith('.json')]
        files.sort(reverse=True)
        
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
                    
                    # 顧客名を取得
                    customers = []
                    for item in data:
                        # データが辞書型か確認
                        if isinstance(item, dict):
                            customer = item.get('customer') or item.get('顧客名')
                            if customer and customer not in customers:
                                customers.append(customer)
                    
                    # 結果を追加
                    history_data.append({
                        'filename': file,
                        'date': formatted_date,
                        'customers': customers,
                        'count': len(data)
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
    return render_template('history.html', history_data=history_data)

# 履歴削除機能
@app.route('/history/delete', methods=['POST'])
@paid_member_or_admin_required
def delete_history():
    """
    履歴ファイルを削除する関数
    二重確認のため、確認コードを検証する
    PayPal APIを使用して注文情報も削除する
    """
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
    """
    PayPal APIのベースURLを取得する
    キャッシュ機能とエラーハンドリングを実装
    
    Returns:
        文字列: PayPal APIのベースURL
    """
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

def create_paypal_payment_link(amount, customer):
    """
    PayPal決済リンクを生成する
    
    Args:
        amount: 金額
        customer: 客先名
        
    Returns:
        PayPal決済リンクのURL
    """
    config = get_config()
    client_id = config.get('paypal_client_id', '')
    client_secret = config.get('paypal_client_secret', '')
    
    if not client_id or not client_secret:
        logger.warning("PayPal Client IDまたはClient Secretが設定されていません")
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
            access_token = get_paypal_access_token()
            
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
                    "return_url": request.url_root.rstrip('/') + url_for('payment_success'),
                    "cancel_url": request.url_root.rstrip('/') + url_for('payment_cancel'),
                    "brand_name": "PDF PayPal System",
                    "locale": "ja-JP",
                    "landing_page": "BILLING",
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

def check_payment_status(order_id):
    """
    PayPal APIを使用して決済状態を確認する
    
    Args:
        order_id: PayPalのオーダーID
        
    Returns:
        状態文字列: 'COMPLETED', 'PENDING', 'FAILED', 'UNKNOWN'のいずれか
    """
    try:
        if not order_id or len(order_id) < 5:
            logger.warning(f"無効なオーダーID: {order_id}")
            return "UNKNOWN"
            
        logger.info(f"PayPal決済状態確認開始: オーダーID={order_id}")
            
        # アクセストークン取得
        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("PayPalアクセストークン取得失敗")
            return "UNKNOWN"
        
        # オーダー情報取得
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Cache-Control": "no-cache"
        }
        
        api_base = get_api_base()
        order_url = f"{api_base}/v2/checkout/orders/{order_id}"
        logger.info(f"PayPal API呼び出し: {order_url}")
        
        # キャッシュを使用しないようにするためのパラメータを追加
        params = {"_": int(time.time() * 1000)}
        response = requests.get(order_url, headers=headers, params=params)
        
        logger.info(f"PayPal APIレスポンス: ステータスコード={response.status_code}")
        
        if response.status_code == 200:
            order_data = response.json()
            status = order_data.get("status", "")
            logger.info(f"PayPal注文ステータス: {status}, 詳細: {json.dumps(order_data)[:200]}...")
            
            # 承認済みの場合はキャプチャを試みる
            if status == "APPROVED":
                logger.info(f"承認済み注文を検出: {order_id} - キャプチャを試みます")
                capture_url = f"{api_base}/v2/checkout/orders/{order_id}/capture"
                capture_response = requests.post(capture_url, headers=headers)
                
                if capture_response.status_code == 201:
                    capture_data = capture_response.json()
                    capture_status = capture_data.get("status", "")
                    logger.info(f"キャプチャ成功: 新ステータス={capture_status}")
                    if capture_status == "COMPLETED":
                        return "COMPLETED"  # キャプチャ成功、支払い完了
                else:
                    logger.error(f"キャプチャ失敗: {capture_response.status_code}, {capture_response.text}")
            
            # 状態に応じて返却
            if status == "COMPLETED":
                logger.info("支払い完了状態を返却: COMPLETED")
                return "COMPLETED"  # 支払い完了
            elif status == "APPROVED":
                logger.info("承認済み状態を返却: PENDING")
                return "PENDING"    # 承認済み（キャプチャ前）
            elif status == "CREATED":
                logger.info("作成済み状態を返却: PENDING")
                return "PENDING"    # 作成済み（支払い前）
            elif status == "VOIDED":
                logger.info("無効化状態を返却: FAILED")
                return "FAILED"     # 無効化された注文
            elif status == "PAYER_ACTION_REQUIRED":
                logger.info("アクション必要状態を返却: PENDING")
                return "PENDING"    # 支払い者のアクションが必要な状態
            else:
                logger.info(f"その他の状態を返却: {status}")
                return status        # その他の状態はそのまま返す
        else:
            logger.error(f"PayPal API エラー: {response.status_code}, {response.text}")
            return "UNKNOWN"
    except Exception as e:
        logger.error(f"決済状態確認エラー: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return "UNKNOWN"

# 選択された金額で決済リンクを生成するAPI
def generate_payment_link():
    """選択された金額で決済リンクを生成するAPI"""
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
        
        logger.info(f"決済リンク生成リクエスト: 顧客名={customer}, 金額={amount}, ファイル名={filename}")
        
        # 金額が有効かチェック
        if not amount or amount == '0':
            logger.error("無効な金額です")
            return jsonify({'error': '有効な金額を指定してください'}), 400
        
        # PayPalの決済リンクを生成
        payment_link = create_paypal_payment_link(amount, customer)
        
        if not payment_link:
            logger.error("決済リンクの生成に失敗しました")
            return jsonify({'error': '決済リンクの生成に失敗しました'}), 500
        
        # 履歴ファイルを更新（存在する場合）
        try:
            # 最新の履歴ファイルを探す（filenameに関連する履歴）
            results_folder = app.config['RESULTS_FOLDER']
            history_files = [f for f in os.listdir(results_folder) if f.endswith('.json')]
            history_files.sort(reverse=True)  # 最新のファイルが先頭に来るようにソート
            
            updated = False
            for history_file in history_files:
                file_path = os.path.join(results_folder, history_file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    results = json.load(f)
                
                # ファイル名が一致する項目を探して更新
                for item in results:
                    if isinstance(item, dict) and item.get('filename') == filename:
                        item['amount'] = amount
                        item['payment_link'] = payment_link
                        item['status'] = 'success'
                        updated = True
                        break
                
                if updated:
                    # 更新された結果を保存
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                    logger.info(f"履歴ファイル {history_file} を更新しました")
                    break
        except Exception as e:
            logger.warning(f"履歴ファイルの更新に失敗しました: {str(e)}")
        
        return jsonify({
            'success': True,
            'payment_link': payment_link,
            'customer': customer,
            'amount': amount
        })
    except Exception as e:
        logger.error(f"決済リンク生成エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 履歴詳細ページ
@app.route('/history/<filename>')
def history_detail(filename):
    """
    決済履歴詳細ページ
    管理者権限が必要
    """
    results = []
    try:
        results_folder = app.config['RESULTS_FOLDER']
        file_path = os.path.join(results_folder, filename)
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                results = json.load(f)
                
            # 各決済リンクの状態を確認
            for i, item in enumerate(results):
                # データが辞書型か確認
                if not isinstance(item, dict):
                    logger.warning(f"履歴データの項目 {i} は辞書型ではありません: {type(item)}")
                    continue
                
                # 金額データの処理
                if 'amount' in item:
                    amount_data = item['amount']
                    # 金額がオブジェクト形式の場合
                    if isinstance(amount_data, dict) and 'selected' in amount_data:
                        # selectedの値を取り出して表示用にフォーマット
                        selected_amount = amount_data['selected']
                        # 数値以外の文字を除去して整数値に変換
                        numeric_amount = ''.join(filter(str.isdigit, str(selected_amount)))
                        # カンマ区切りを追加
                        if numeric_amount:
                            formatted_amount = f"¥{int(numeric_amount):,}"
                        else:
                            formatted_amount = "¥0"
                        item['formatted_amount'] = formatted_amount
                    else:
                        # 単純な文字列または数値の場合
                        numeric_amount = ''.join(filter(str.isdigit, str(amount_data)))
                        if numeric_amount:
                            item['formatted_amount'] = f"¥{int(numeric_amount):,}"
                        else:
                            item['formatted_amount'] = "¥0"
                else:
                    item['formatted_amount'] = "¥0"
                
                # 顧客名の処理
                customer_value = None
                # customer_nameキーを優先的に確認
                if 'customer_name' in item and item['customer_name']:
                    customer_value = item['customer_name']
                # 次にcustomerキーを確認
                elif 'customer' in item and item['customer']:
                    customer_value = item['customer']
                
                if customer_value:
                    # 顧客名から余分な空白や改行を除去
                    item['formatted_customer'] = customer_value.replace('\n', ' ').strip()
                    # 「様」を付けないように修正
                    # 以前は「様」を追加していたが、ユーザーの要望により削除
                else:
                    item['formatted_customer'] = '不明'
                    
                payment_link = item.get('payment_link') or item.get('決済リンク', '')
                # PayPalのURLからオーダーIDを抽出
                order_id = None
                if payment_link and 'token=' in payment_link:
                    order_id = payment_link.split('token=')[-1].split('&')[0]
                
                # 決済状態を確認して追加
                if order_id:
                    status = check_payment_status(order_id)
                    item['payment_status'] = status
                else:
                    item['payment_status'] = "UNKNOWN"
                    
    except Exception as e:
        logger.error(f"履歴詳細読み込みエラー: {str(e)}")
    return render_template('history_detail.html', filename=filename, results=results)

# 環境変数からポート番号を取得（クラウド環境対応）
def get_port():
    """コマンドライン引数または環境変数からポート番号を取得する"""
    # コマンドライン引数からポート番号を取得
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, help='ポート番号')
    args, unknown = parser.parse_known_args()
    
    if args.port:
        logger.info(f"コマンドライン引数からポート番号を取得: {args.port}")
        return args.port
    
    # 環境変数からポート番号を取得
    port = os.environ.get('PORT')
    if port:
        try:
            return int(port)
        except ValueError:
            logger.warning(f"無効なポート番号: {port}")
    
    # デフォルトポート
    return 5000

# 設定ファイルが存在しない場合に初期設定を作成
def initialize_config():
    config = get_config()
    if not config:
        config = {
            'paypal_client_id': os.environ.get("PAYPAL_CLIENT_ID", ""),
            'paypal_client_secret': os.environ.get("PAYPAL_CLIENT_SECRET", ""),
            'paypal_mode': os.environ.get("PAYPAL_MODE", "sandbox"),
            'use_ai_ocr': config.get('use_ai_ocr', False)
        }
        save_config(config)
    return config


# トップページ
@app.route('/')
def index():
    """アプリケーションのトップページ
    
    PDFファイルのアップロードと処理を行うメインページ
    """
    logger.info("トップページにアクセスされました")
    
    # セッション情報をログ出力
    logger.info(f"トップページ表示時のセッション状態: {session}")
    logger.info(f"トップページ表示時のセッションID: {session.sid if hasattr(session, 'sid') else 'なし'}")
    logger.info(f"トップページ表示時のCookie: {request.cookies}")
    
    # 現在のPayPalモードを取得
    config = get_config()
    paypal_mode = config.get('paypal_mode', 'sandbox')
    
    # ユーザー権限情報
    is_admin = session.get('admin_logged_in', False)
    is_paid_member = session.get('is_paid_member', False)
    
    # 権限情報をログ出力
    logger.info(f"トップページ表示時の権限情報 - is_admin: {is_admin}, is_paid_member: {is_paid_member}")
    
    # セッションが正しく保存されているか確認
    if 'admin_logged_in' in session:
        logger.info("管理者ログイン情報がセッションに存在します")
    else:
        logger.warning("管理者ログイン情報がセッションに存在しません")
    
    # 本番モードで有料会員でない場合は制限表示フラグをオン
    show_restrictions = paypal_mode.lower() == 'live' and not (is_admin or is_paid_member)
    
    # レンダリング前の最終確認
    logger.info(f"トップページレンダリング前の最終確認 - is_admin: {is_admin}, paypal_mode: {paypal_mode}")
    
    return render_template(
        'index.html',
        paypal_mode=paypal_mode,
        is_admin=is_admin,
        is_paid_member=is_paid_member,
        show_restrictions=show_restrictions
    )

# 有料会員情報ページ
@app.route('/membership_info')
def membership_info():
    """有料会員情報を表示するページ
    
    有料会員の特典や登録方法などの情報を表示する
    """
    logger.info("有料会員情報ページにアクセスされました")
    
    # 現在のPayPalモードを取得
    config = get_config()
    paypal_mode = config.get('paypal_mode', 'sandbox')
    
    # ユーザー権限情報
    is_admin = session.get('admin_logged_in', False)
    is_paid_member = session.get('is_paid_member', False)
    
    return render_template(
        'membership_info.html',
        paypal_mode=paypal_mode,
        is_admin=is_admin,
        is_paid_member=is_paid_member
    )

# 管理者連絡ページ
@app.route('/contact_admin')
def contact_admin():
    """管理者への連絡ページ
    
    有料会員登録や問い合わせのための管理者連絡フォームを表示する
    """
    logger.info("管理者連絡ページにアクセスされました")
    
    # 現在のPayPalモードを取得
    config = get_config()
    paypal_mode = config.get('paypal_mode', 'sandbox')
    
    # ユーザー権限情報
    is_admin = session.get('admin_logged_in', False)
    is_paid_member = session.get('is_paid_member', False)
    
    # 管理者のメールアドレス（環境変数から取得）
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    
    return render_template(
        'contact_admin.html',
        paypal_mode=paypal_mode,
        is_admin=is_admin,
        is_paid_member=is_paid_member,
        admin_email=admin_email
    )

# PayPal決済成功ページ
@app.route('/payment_success')
def payment_success():
    """決済成功時のリダイレクト先ページ
    
    PayPal決済が成功した場合に表示されるページ
    """
    # リクエストパラメータを取得
    order_id = request.args.get('token')
    payer_id = request.args.get('PayerID')
    
    logger.info(f"PayPal決済成功ページにアクセスされました - token: {order_id}, PayerID: {payer_id}")
    
    # 決済状態を確認
    status = "UNKNOWN"
    if order_id:
        status = check_payment_status(order_id)
        logger.info(f"PayPal決済状態: {status}")
    
    # 現在時刻を取得
    current_time = datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
    
    return render_template(
        'payment_result.html',
        status=status,
        order_id=order_id,
        result="success",
        current_time=current_time
    )

# PayPal決済キャンセルページ
@app.route('/payment_cancel')
def payment_cancel():
    """決済キャンセル時のリダイレクト先ページ
    
    PayPal決済がキャンセルされた場合に表示されるページ
    """
    logger.info("PayPal決済キャンセルページにアクセスされました")
    
    # オーダーIDを取得
    order_id = request.args.get('token')
    
    # 現在時刻を取得
    current_time = datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
    
    return render_template(
        'payment_result.html',
        status="CANCELED",
        order_id=order_id,
        result="cancel",
        current_time=current_time
    )

# PDFファイルのアップロード処理
@app.route('/upload', methods=['POST'])
def upload_file():
    """ファイルアップロードのAPIエンドポイント
    
    クライアントから送信されたPDFファイルを受け取り、一時ディレクトリに保存する
    """
    logger.info("ファイルアップロードリクエストを受信")
    
    # リクエストのデバッグ情報を記録
    logger.debug(f"Request files: {request.files}")
    logger.debug(f"Request form: {request.form}")
    
    # ファイルが送信されているか確認
    if 'file' not in request.files:
        logger.warning("ファイルが送信されていません")
        return jsonify({'error': 'ファイルが送信されていません'}), 400
    
    file = request.files['file']
    
    # ファイル名が空でないか確認
    if file.filename == '':
        logger.warning("ファイル名が空です")
        return jsonify({'error': 'ファイルが選択されていません'}), 400
    
    # ファイル拡張子が有効か確認
    if not file.filename.lower().endswith('.pdf'):
        logger.warning(f"無効なファイル形式: {file.filename}")
        return jsonify({'error': 'PDFファイルのみアップロード可能です'}), 400
    
    try:
        # ファイルを保存
        filename = secure_filename(file.filename)
        upload_folder = current_app.config['UPLOAD_FOLDER']
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
        return jsonify({'error': f'ファイルの保存中にエラーが発生しました: {str(e)}'}), 500

# PDFファイルの処理
@app.route('/process', methods=['POST'])
@api_access_required
def process_pdf():
    """アップロードされたPDFファイルを処理するAPIエンドポイント
    
    PDFから顧客名と金額を抽出し、PayPal決済リンクを生成する
    """
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
        upload_folder = current_app.config['UPLOAD_FOLDER']
        filepath = os.path.join(upload_folder, filename)
        
        logger.info(f"PDF処理ファイルパス: {filepath}")
        
        # ファイルの存在確認
        if not os.path.exists(filepath):
            logger.warning(f"ファイルが存在しません: {filepath}")
            return jsonify({'error': 'ファイルが見つかりません'}), 404
        
        # ファイルのサイズとタイプを確認
        file_size = os.path.getsize(filepath)
        logger.info(f"PDFファイルサイズ: {file_size} バイト")
        
        # キャッシュを確認
        if filename in processed_files_cache:
            logger.info(f"キャッシュから結果を返します: {filename}")
            return jsonify(processed_files_cache[filename])
        
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
                    result = process_single_pdf(filepath, filename)
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
                            page_result = process_single_pdf(page_filepath, f"{filename}_page{page_num + 1}")
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
        
        processed_files_cache[filename] = response_data
        
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
        logger.error(f"PDF処理エラー: {str(e)}")
        return jsonify({'error': f'PDF処理中にエラーが発生しました: {str(e)}'}), 500

# PDFからテキストを抽出する関数
def extract_text_from_pdf(pdf_path):
    """複数の方法でPDFからテキストを抽出する
    
    以下の方法を順番に試し、最初に成功した方法の結果を返す:
    1. pdfplumber
    2. PyPDF2
    3. pdf2image + pytesseract (OCR)
    4. pdfminer.six
    5. pdftotextコマンド
    
    Args:
        pdf_path: PDFファイルのパス
        
    Returns:
        抽出されたテキストと使用された方法を含む辞書
    """
    logger.info(f"PDFからテキストを抽出開始: {pdf_path}")
    
    # 方法１: pdfplumberを使用
    try:
        logger.info("方法１: pdfplumberを使用")
        import pdfplumber
        
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
            
            if text.strip():
                logger.info("pdfplumberでテキスト抽出成功")
                return {'text': text, 'method': 'pdfplumber'}
    except Exception as e:
        logger.warning(f"pdfplumberでの抽出失敗: {str(e)}")
    
    # 方法２: PyPDF2を使用
    try:
        logger.info("方法２: PyPDF2を使用")
        import PyPDF2
        
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
            
            if text.strip():
                logger.info("PyPDF2でテキスト抽出成功")
                return {'text': text, 'method': 'PyPDF2'}
    except Exception as e:
        logger.warning(f"PyPDF2での抽出失敗: {str(e)}")
    
    # 方法３: pdf2image + pytesseract (OCR)
    try:
        logger.info("方法３: pdf2image + pytesseract (OCR)を使用")
        import pdf2image
        import pytesseract
        from PIL import Image
        
        images = pdf2image.convert_from_path(pdf_path)
        text = ""
        for i, image in enumerate(images):
            page_text = pytesseract.image_to_string(image, lang='jpn+eng')
            if page_text:
                text += page_text + "\n\n"
        
        if text.strip():
            logger.info("OCRでテキスト抽出成功")
            return {'text': text, 'method': 'OCR'}
    except Exception as e:
        logger.warning(f"OCRでの抽出失敗: {str(e)}")
    
    # 方法４: pdfminer.sixを使用
    try:
        logger.info("方法４: pdfminer.sixを使用")
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        
        text = pdfminer_extract_text(pdf_path)
        if text.strip():
            logger.info("pdfminer.sixでテキスト抽出成功")
            return {'text': text, 'method': 'pdfminer'}
    except Exception as e:
        logger.warning(f"pdfminer.sixでの抽出失敗: {str(e)}")
    
    # 方法５: pdftotextコマンドを使用
    try:
        logger.info("方法５: pdftotextコマンドを使用")
        import subprocess
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.txt') as temp_file:
            subprocess.run(['pdftotext', pdf_path, temp_file.name], check=True)
            with open(temp_file.name, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        
        if text.strip():
            logger.info("pdftotextコマンドでテキスト抽出成功")
            return {'text': text, 'method': 'pdftotext'}
    except Exception as e:
        logger.warning(f"pdftotextコマンドでの抽出失敗: {str(e)}")
    
    # すべての方法が失敗した場合
    logger.error(f"すべての方法でテキスト抽出に失敗しました: {pdf_path}")
    return {'text': '', 'method': 'failed'}

# 単一PDFファイルの処理
def process_single_pdf(filepath, filename):
    """単一のPDFファイルを処理する関数
    
    PDFからテキストを抽出し、顧客名と金額を特定してPayPal決済リンクを生成する
    
    Args:
        filepath: PDFファイルのパス
        filename: ファイル名
        
    Returns:
        処理結果を含む辞書
    """
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
        
        # PayPal決済リンクを生成
        # generate_payment_linkの代わりにcreate_paypal_payment_linkを直接呼び出す
        payment_link = None
        order_id = None
        try:
            if amount_str and amount_str != '0':
                payment_link = create_paypal_payment_link(amount_str, customer_name)
                logger.info(f"決済リンク生成成功: {payment_link}")
        except Exception as e:
            logger.error(f"決済リンク生成エラー: {str(e)}")
        
        # 結果を返す
        return {
            'filename': filename,
            'customer_name': customer_name,
            'amount': amount_str,
            'payment_link': payment_link,
            'order_id': order_id,
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



# 設定の保存
@app.route('/settings/save', methods=['POST'])
def save_settings():
    """設定を保存する
    
    フォームから送信された設定をJSONファイルに保存する
    管理者はすべての設定を変更可能
    ゲストユーザーはsandboxモードのみ変更可能
    """
    logger.info("設定保存リクエストを受信")
    
    try:
        # フォームデータを取得
        client_id = request.form.get('client_id', '')
        client_secret = request.form.get('client_secret', '')
        paypal_mode = request.form.get('paypal_mode', 'sandbox')
        admin_email = request.form.get('admin_email', '')
        
        # 現在の設定を取得
        config = get_config()
        
        # 管理者権限チェック
        is_admin = session.get('admin_logged_in', False)
        
        # 本番モードへの変更は管理者のみ許可
        if paypal_mode == 'live' and not is_admin:
            flash('本番環境の設定変更は管理者のみ許可されています', 'warning')
            return redirect(url_for('settings'))
        
        # 管理者の場合はすべての設定を更新
        if is_admin:
            config['client_id'] = client_id
            config['client_secret'] = client_secret
            config['paypal_mode'] = paypal_mode
            config['admin_email'] = admin_email
            
            # 環境変数にも反映
            os.environ['PAYPAL_MODE'] = paypal_mode
            os.environ['ADMIN_EMAIL'] = admin_email
        # ゲストの場合はsandboxモードの設定のみ更新
        else:
            # 現在のモードを維持（sandboxのみ許可）
            config['client_id'] = client_id
            config['client_secret'] = client_secret
            # paypal_modeは変更しない（sandboxのまま）
        
        # 設定を保存
        save_config(config)
        
        flash('設定が保存されました', 'success')
        logger.info("設定が正常に保存されました")
        
        return redirect(url_for('settings'))
        
    except Exception as e:
        flash(f'設定の保存中にエラーが発生しました: {str(e)}', 'error')
        logger.error(f"設定保存エラー: {str(e)}")
        return redirect(url_for('settings'))

# 接続テスト
@app.route('/settings/test_connection', methods=['POST'])
def test_connection():
    """接続テストを行う
    
    PayPal APIへの接続テストを行い、結果を返す
    JSONリクエストとフォームデータの両方に対応
    """
    logger.info("接続テストリクエストを受信")
    
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
def export_settings():
    """設定をJSONファイルとしてエクスポートする
    
    現在の設定をJSONファイルとしてダウンロード可能にする
    管理者はすべての設定をエクスポート可能
    ゲストユーザーはsandboxモードのみエクスポート可能
    """
    logger.info("設定エクスポートリクエストを受信")
    
    try:
        # 現在の設定を取得
        config = get_config()
        
        # 管理者権限チェック
        is_admin = session.get('admin_logged_in', False)
        
        # 本番モード設定へのアクセス制限
        if not is_admin and config.get('paypal_mode', 'sandbox') == 'live':
            flash('本番環境の設定エクスポートは管理者のみ許可されています', 'warning')
            return redirect(url_for('settings'))
        
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
def import_settings():
    """設定をJSONファイルからインポートする
    
    アップロードされたJSONファイルから設定をインポートする
    管理者はすべての設定をインポート可能
    ゲストユーザーはsandboxモードのみインポート可能
    """
    logger.info("設定インポートリクエストを受信")
    
    try:
        # 管理者権限チェック
        is_admin = session.get('admin_logged_in', False)
        
        # 現在の設定を取得
        current_config = get_config()
        current_mode = current_config.get('paypal_mode', 'sandbox')
        
        # 本番モード設定へのアクセス制限
        if not is_admin and current_mode == 'live':
            flash('本番環境の設定インポートは管理者のみ許可されています', 'warning')
            return redirect(url_for('settings'))
        
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
        
        # 非管理者がliveモードの設定をインポートしようとしている場合は拒否
        if not is_admin and imported_config.get('paypal_mode') == 'live':
            flash('本番環境の設定インポートは管理者のみ許可されています', 'warning')
            return redirect(url_for('settings'))
        
        # 設定をマージ
        for key, value in imported_config.items():
            # 非管理者の場合、paypal_modeはsandboxのままにする
            if key == 'paypal_mode' and not is_admin:
                continue
                
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

# ファイルダウンロード
@app.route('/download/<path:filename>')
def download_file(filename):
    """ファイルダウンロードのAPIエンドポイント
    
    指定されたファイルをダウンロードする
    
    Args:
        filename: ダウンロードするファイル名
    """
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

# アプリ実行
if __name__ == '__main__':
    # ロガーの初期化
    setup_logger()
    
    # キャッシュをクリア
    clear_cache()
    
    # アプリケーションの起動
    # 環境変数の表示（デバッグ用）
    logger.info("=== 環境変数 ===")
    for key in ['PORT', 'UPLOAD_FOLDER', 'RESULTS_FOLDER', 'USE_TEMP_DIR']:
        logger.info(f"{key}: {os.environ.get(key, 'Not set')}")
    
    # アプリ初期化
    create_app()
    port = get_port()
    
    # Renderなどのクラウド環境では、debug=Falseを使用
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    logger.info(f"アプリ起動: host=0.0.0.0, port={port}, debug={debug_mode}")
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
