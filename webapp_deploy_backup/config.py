import os
import tempfile
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def get_config():
    """アプリケーション設定を取得"""
    
    # dotenvを使って環境変数を確実に読み込み
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info(f"Config: Loading environment variables from {env_path}")
    else:
        logger.warning(f"Config: .env file not found at {env_path}")
        
    config = {
        'SECRET_KEY': os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production'),
        'CSRF_SECRET_KEY': os.environ.get('CSRF_SECRET_KEY', 'dev-csrf-key-change-in-production'),
        'SESSION_TYPE': os.environ.get('SESSION_TYPE', 'filesystem'),
        'SESSION_PERMANENT': os.environ.get('SESSION_PERMANENT', 'true').lower() == 'true',
        'SESSION_USE_SIGNER': os.environ.get('SESSION_USE_SIGNER', 'true').lower() == 'true',
        'SESSION_FILE_THRESHOLD': int(os.environ.get('SESSION_FILE_THRESHOLD', 100)),
        'SESSION_FILE_DIR': os.environ.get('SESSION_FILE_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_session')),
        'SESSION_COOKIE_DOMAIN': None,
        'SESSION_COOKIE_PATH': '/',
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SECURE': False,  # HTTPSでない場合はFalse
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'PERMANENT_SESSION_LIFETIME': 86400,  # 24時間
        
        # ファイルアップロード設定
        'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,  # 16MB
        'UPLOAD_EXTENSIONS': ['.pdf'],
        
        # PayPal API設定
        'paypal_mode': os.environ.get('PAYPAL_MODE', 'sandbox'),
        'client_id': os.environ.get('PAYPAL_CLIENT_ID', ''),
        'client_secret': os.environ.get('PAYPAL_CLIENT_SECRET', ''),
        
        # Stripe API設定
        'stripe_publishable_key': os.environ.get('STRIPE_PUBLISHABLE_KEY', ''),
        'stripe_secret_key': os.environ.get('STRIPE_SECRET_KEY', ''),
        'stripe_mode': os.environ.get('STRIPE_MODE', 'test'),  # test/live
        
        # 決済プロバイダー選択
        'default_payment_provider': os.environ.get('DEFAULT_PAYMENT_PROVIDER', 'paypal'),  # paypal/stripe
    }
    
    # PayPal認証情報のログ出力（セキュリティに配慮）
    logger.info(f"Config: PayPal mode: {config['paypal_mode']}")
    logger.info(f"Config: PayPal client_id: {'設定あり' if config['client_id'] else '未設定'}")
    logger.info(f"Config: PayPal client_secret: {'設定あり' if config['client_secret'] else '未設定'}")
    
    # Stripe認証情報のログ出力（セキュリティに配慮）
    logger.info(f"Config: Stripe mode: {config['stripe_mode']}")
    logger.info(f"Config: Stripe publishable_key: {'設定あり' if config['stripe_publishable_key'] else '未設定'}")
    logger.info(f"Config: Stripe secret_key: {'設定あり' if config['stripe_secret_key'] else '未設定'}")
    logger.info(f"Config: Default payment provider: {config['default_payment_provider']}")
    
    # 設定に問題がある場合は警告
    if not config['client_id'] or not config['client_secret']:
        logger.warning("Config: PayPal認証情報が不足しています。APIの動作に影響する可能性があります.")
    
    if not config['stripe_publishable_key'] or not config['stripe_secret_key']:
        logger.warning("Config: Stripe認証情報が不足しています。APIの動作に影響する可能性があります.")
    
    # セッションファイルディレクトリの設定
    session_dir = os.environ.get('SESSION_FILE_DIR')
    if not session_dir:
        # Cloud Runやコンテナ環境では/tmpを使用
        if os.path.exists('/tmp'):
            session_dir = '/tmp/flask_sessions'
        else:
            # Windowsやローカル環境では一時ディレクトリを使用
            session_dir = os.path.join(tempfile.gettempdir(), 'flask_sessions')
    
    # ディレクトリを作成
    os.makedirs(session_dir, exist_ok=True)
    config['SESSION_FILE_DIR'] = session_dir
    
    # アップロードフォルダの設定
    upload_folder = os.environ.get('UPLOAD_FOLDER')
    if not upload_folder:
        if os.environ.get('USE_TEMP_DIR') == 'true':
            upload_folder = os.path.join(tempfile.gettempdir(), 'uploads')
        else:
            upload_folder = os.path.join(os.path.dirname(__file__), 'uploads')
    
    os.makedirs(upload_folder, exist_ok=True)
    config['UPLOAD_FOLDER'] = upload_folder
    
    # 結果フォルダの設定
    results_folder = os.environ.get('RESULTS_FOLDER')
    if not results_folder:
        if os.environ.get('USE_TEMP_DIR') == 'true':
            results_folder = os.path.join(tempfile.gettempdir(), 'results')
        else:
            results_folder = os.path.join(os.path.dirname(__file__), 'results')
    
    os.makedirs(results_folder, exist_ok=True)
    config['RESULTS_FOLDER'] = results_folder
    
    # 重要な設定値をログ出力
    logger.info(f"Config: UPLOAD_FOLDER: {upload_folder}")
    logger.info(f"Config: RESULTS_FOLDER: {results_folder}")
    logger.info(f"Config: SESSION_FILE_DIR: {session_dir}")
    
    # 接続テスト用に設定値を確認
    try:
        if config['client_id'] and config['client_secret']:
            from paypal_helpers import safe_test_paypal_connection
            logger.info("Config: テスト用PayPal接続を実行中...")
            result = safe_test_paypal_connection(
                config['client_id'], 
                config['client_secret'], 
                config['paypal_mode']
            )
            if result['success']:
                logger.info(f"Config: PayPal接続テスト成功: {result['message']}")
            else:
                logger.warning(f"Config: PayPal接続テスト失敗: {result['message']}")
    except Exception as e:
        logger.error(f"Config: PayPal接続テスト中にエラー発生: {str(e)}")
    
    # Stripe接続テスト
    try:
        if config['stripe_secret_key']:
            from stripe_utils import test_stripe_connection
            logger.info("Config: テスト用Stripe接続を実行中...")
            result = test_stripe_connection(config['stripe_secret_key'])
            if result['success']:
                logger.info(f"Config: Stripe接続テスト成功: {result['message']}")
            else:
                logger.warning(f"Config: Stripe接続テスト失敗: {result['message']}")
    except Exception as e:
        logger.error(f"Config: Stripe接続テスト中にエラー発生: {str(e)}")
    
    logger.info(f"Config: PAYPAL_MODE: {config['paypal_mode']}")
    logger.info(f"Config: STRIPE_MODE: {config['stripe_mode']}")
    
    return config
