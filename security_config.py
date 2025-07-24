#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
セキュリティ設定とログ設定管理モジュール
API キーの暗号化、ログのマスキング、セキュリティヘッダーの設定
"""

import os
import logging
import logging.handlers
import re
from cryptography.fernet import Fernet
from functools import wraps
from flask import request, g, current_app
import hashlib
import hmac
import time

class SecurityConfig:
    """セキュリティ設定管理クラス"""
    
    def __init__(self):
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
        self.sensitive_patterns = [
            r'sk_test_[a-zA-Z0-9]+',      # Stripe Secret Key (Test)
            r'sk_live_[a-zA-Z0-9]+',      # Stripe Secret Key (Live)
            r'pk_test_[a-zA-Z0-9]+',      # Stripe Publishable Key (Test)
            r'pk_live_[a-zA-Z0-9]+',      # Stripe Publishable Key (Live)
            r'whsec_[a-zA-Z0-9]+',        # Stripe Webhook Secret
            r'password\s*[:=]\s*[^\s]+',  # Password fields
            r'secret\s*[:=]\s*[^\s]+',    # Secret fields
        ]
    
    def _get_or_create_encryption_key(self):
        """暗号化キーの取得または生成"""
        key_file = 'encryption.key'
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        
        # 新しいキーを生成
        key = Fernet.generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
        
        # ファイル権限を600に設定（オーナーのみ読み書き可能）
        os.chmod(key_file, 0o600)
        
        return key
    
    def encrypt_api_key(self, api_key):
        """API キーの暗号化"""
        try:
            encrypted_key = self.cipher_suite.encrypt(api_key.encode())
            return encrypted_key.decode()
        except Exception as e:
            logging.error(f"API キー暗号化エラー: {e}")
            return None
    
    def decrypt_api_key(self, encrypted_key):
        """API キーの復号化"""
        try:
            decrypted_key = self.cipher_suite.decrypt(encrypted_key.encode())
            return decrypted_key.decode()
        except Exception as e:
            logging.error(f"API キー復号化エラー: {e}")
            return None
    
    def mask_sensitive_data(self, text):
        """機密データのマスキング"""
        if not text:
            return text
        
        masked_text = text
        for pattern in self.sensitive_patterns:
            masked_text = re.sub(pattern, lambda m: m.group()[:8] + '*' * (len(m.group()) - 8), masked_text, flags=re.IGNORECASE)
        
        return masked_text
    
    def validate_api_key_format(self, api_key, key_type='stripe'):
        """API キー形式の検証"""
        if key_type == 'stripe':
            patterns = {
                'secret_test': r'^sk_test_[a-zA-Z0-9]{24,}$',
                'secret_live': r'^sk_live_[a-zA-Z0-9]{24,}$',
                'publishable_test': r'^pk_test_[a-zA-Z0-9]{24,}$',
                'publishable_live': r'^pk_live_[a-zA-Z0-9]{24,}$',
                'webhook': r'^whsec_[a-zA-Z0-9]{32,}$'
            }
            
            for pattern_type, pattern in patterns.items():
                if re.match(pattern, api_key):
                    return pattern_type
        
        return None


class SecureLogger:
    """セキュアログ管理クラス"""
    
    def __init__(self, app=None):
        self.app = app
        self.security_config = SecurityConfig()
        self.logger = None
        self.error_logger = None
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Flaskアプリケーションの初期化"""
        self.app = app
        self._setup_loggers()
        self._setup_security_headers()
    
    def _setup_loggers(self):
        """ログ設定のセットアップ"""
        # ログディレクトリの作成
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        
        # ログレベルの設定
        log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper())
        
        # フォーマッターの設定
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # セキュアフォーマッター（機密データをマスキング）
        secure_formatter = SecureFormatter(self.security_config)
        
        # アプリケーションログ
        app_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'app.log'),
            maxBytes=int(os.getenv('LOG_MAX_BYTES', 10485760)),  # 10MB
            backupCount=int(os.getenv('LOG_BACKUP_COUNT', 5))
        )
        app_handler.setFormatter(secure_formatter)
        app_handler.setLevel(log_level)
        
        # エラーログ
        error_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'error.log'),
            maxBytes=int(os.getenv('LOG_MAX_BYTES', 10485760)),
            backupCount=int(os.getenv('LOG_BACKUP_COUNT', 5))
        )
        error_handler.setFormatter(secure_formatter)
        error_handler.setLevel(logging.ERROR)
        
        # コンソールログ（開発環境のみ）
        if os.getenv('FLASK_ENV') == 'development':
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(log_level)
            
            self.app.logger.addHandler(console_handler)
        
        # Flaskアプリケーションにハンドラーを追加
        self.app.logger.addHandler(app_handler)
        self.app.logger.addHandler(error_handler)
        self.app.logger.setLevel(log_level)
        
        # ログ権限の設定
        for handler in [app_handler, error_handler]:
            if hasattr(handler, 'baseFilename'):
                os.chmod(handler.baseFilename, 0o640)
    
    def _setup_security_headers(self):
        """セキュリティヘッダーの設定"""
        @self.app.after_request
        def add_security_headers(response):
            # HTTPS強制（本番環境）
            if os.getenv('FLASK_ENV') == 'production':
                response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            
            # XSS保護
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            
            # CSP設定
            csp = "default-src 'self'; script-src 'self' 'unsafe-inline' https://js.stripe.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://api.stripe.com"
            response.headers['Content-Security-Policy'] = csp
            
            return response
        
        # リクエストログ
        @self.app.before_request
        def log_request_info():
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            self.app.logger.info(f"Request: {request.method} {request.url} from {client_ip}")
    
    def log_api_call(self, provider, endpoint, response_status, duration):
        """API呼び出しログ"""
        masked_endpoint = self.security_config.mask_sensitive_data(endpoint)
        self.app.logger.info(f"API Call: {provider} - {masked_endpoint} - Status: {response_status} - Duration: {duration:.3f}s")
    
    def log_security_event(self, event_type, details):
        """セキュリティイベントログ"""
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr) if request else 'system'
        masked_details = self.security_config.mask_sensitive_data(str(details))
        self.app.logger.warning(f"Security Event: {event_type} - IP: {client_ip} - Details: {masked_details}")


class SecureFormatter(logging.Formatter):
    """機密データをマスキングするログフォーマッター"""
    
    def __init__(self, security_config):
        super().__init__('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.security_config = security_config
    
    def format(self, record):
        # 元のメッセージをフォーマット
        formatted = super().format(record)
        
        # 機密データのマスキング
        if os.getenv('MASK_SENSITIVE_DATA', 'True').lower() == 'true':
            formatted = self.security_config.mask_sensitive_data(formatted)
        
        return formatted


def rate_limit(max_requests=60, window=60):
    """レート制限デコレータ"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not os.getenv('RATE_LIMIT_ENABLED', 'True').lower() == 'true':
                return f(*args, **kwargs)
            
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            key = f"rate_limit:{client_ip}:{request.endpoint}"
            
            # 簡易レート制限実装（Redisがある場合はRedisを使用）
            current_time = int(time.time())
            window_start = current_time - window
            
            # セッションベースの簡易実装
            if not hasattr(g, 'rate_limit_cache'):
                g.rate_limit_cache = {}
            
            if key not in g.rate_limit_cache:
                g.rate_limit_cache[key] = []
            
            # 古いリクエストを削除
            g.rate_limit_cache[key] = [req_time for req_time in g.rate_limit_cache[key] if req_time > window_start]
            
            # 現在のリクエストを追加
            g.rate_limit_cache[key].append(current_time)
            
            # レート制限チェック
            if len(g.rate_limit_cache[key]) > max_requests:
                current_app.logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                return {"error": "Rate limit exceeded"}, 429
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def verify_webhook_signature(payload, signature, secret):
    """Webhook署名検証"""
    try:
        expected_signature = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        logging.error(f"Webhook署名検証エラー: {e}")
        return False


# 使用例とユーティリティ関数
def initialize_security(app):
    """セキュリティ設定の初期化"""
    secure_logger = SecureLogger(app)
    return secure_logger


def get_secure_config():
    """セキュリティ設定インスタンスの取得"""
    return SecurityConfig()


if __name__ == '__main__':
    # テスト実行
    config = SecurityConfig()
    
    # API キー暗号化テスト
    test_key = "sk_test_4eC39HqLyjWDarjtT1zdp7dc"
    encrypted = config.encrypt_api_key(test_key)
    decrypted = config.decrypt_api_key(encrypted)
    
    print(f"Original: {test_key}")
    print(f"Encrypted: {encrypted}")
    print(f"Decrypted: {decrypted}")
    print(f"Match: {test_key == decrypted}")
    
    # マスキングテスト
    sensitive_text = "API Key: sk_test_4eC39HqLyjWDarjtT1zdp7dc and password: secret123"
    masked = config.mask_sensitive_data(sensitive_text)
    print(f"Original: {sensitive_text}")
    print(f"Masked: {masked}")