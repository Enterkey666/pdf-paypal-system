#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
設定管理モジュール - PDF処理 & PayPal決済リンク発行システム

ユーザー設定の保存、読み込み、エクスポート、インポートを担当します。
"""

import os
import json
import logging
import paypalrestsdk
import secrets
import base64
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# .envファイルから環境変数を読み込む
load_dotenv()

# ロガー設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# デフォルト設定
DEFAULT_CONFIG = {
    # PayPal設定
    "paypal_mode": "sandbox",
    "paypal_client_id": "",
    "paypal_client_secret": "",
    
    # Stripe設定
    "stripe_mode": "test",
    "stripe_secret_key_test": "",
    "stripe_secret_key_live": "",
    "stripe_publishable_key_test": "",
    "stripe_publishable_key_live": "",
    "stripe_webhook_secret": "",
    
    # 決済プロバイダー設定
    "default_payment_provider": "paypal",  # paypal, stripe
    "enabled_payment_providers": ["paypal"],  # 有効な決済プロバイダーのリスト
    
    # 通貨・金額設定
    "default_currency": "JPY",
    "supported_currencies": ["JPY", "USD", "EUR"],
    "default_amount": 1000,
    
    # 決済リンク設定
    "payment_link_expire_days": 30,  # 決済リンク有効期限（日数）
    "payment_link_auto_tax": False,  # 自動税金計算
    "payment_link_allow_quantity_adjustment": False,  # 数量調整許可
    
    # OCR設定
    "enable_customer_extraction": "1",
    "enable_amount_extraction": "1",
    "use_ai_ocr": False,
    "ocr_method": "tesseract",
    "ocr_endpoint": "",
    
    # Webhook設定
    "webhook_enable_signature_verification": True,
    "webhook_timeout_seconds": 30,
    "webhook_retry_attempts": 3,
    
    # セキュリティ設定
    "encrypt_api_keys": True,
    "api_key_rotation_days": 90
}

class ConfigManager:
    """
    設定管理クラス
    設定の読み込み、保存、検証を行う
    """
    
    def __init__(self, config_path: str = "config.json"):
        """
        初期化
        
        Args:
            config_path: 設定ファイルのパス（デフォルト: config.json）
        """
        self.config_path = config_path
        self.config = self.load_config()
        
        # 環境変数から設定を更新（環境変数が優先）
        self.update_from_env()
    
    def load_config(self) -> Dict[str, Any]:
        """
        設定ファイルを読み込む
        
        Returns:
            設定辞書
        """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logger.info(f"設定ファイル読み込み成功: {self.config_path}")
                
                # 古い設定やmissingキーにデフォルト値を適用
                for key, default_value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = default_value
                
                return config
            except Exception as e:
                logger.error(f"設定ファイル読み込みエラー: {str(e)}")
                return DEFAULT_CONFIG.copy()
        else:
            logger.info(f"設定ファイルが存在しないため、デフォルト設定を使用: {self.config_path}")
            return DEFAULT_CONFIG.copy()
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        設定ファイルを保存する
        
        Args:
            config: 保存する設定辞書
        
        Returns:
            保存が成功したかどうか
        """
        try:
            # 渡されたキーで設定を更新（新規キーも受け入れる）
            self.config.update(config)
            
            # ファイルに保存
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"設定ファイル保存成功: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"設定ファイル保存エラー: {str(e)}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """
        現在の設定を取得する
        
        Returns:
            設定辞書
        """
        return self.config
    
    def validate_paypal_config(self) -> bool:
        """
        PayPal設定が有効かどうかを検証する
        
        Returns:
            有効な場合はTrue、無効な場合はFalse
        """
        required_keys = ['paypal_client_id', 'paypal_client_secret', 'paypal_mode']
        return all(self.config.get(key) for key in required_keys)
    
    def export_config(self, export_path: Optional[str] = None) -> str:
        """
        設定をエクスポート用のJSONファイルに保存する
        
        Args:
            export_path: エクスポート先のパス（指定しない場合は自動生成）
        
        Returns:
            エクスポートしたファイルのパス
        """
        if export_path is None:
            export_dir = os.path.dirname(self.config_path)
            export_path = os.path.join(export_dir, "settings_export.json")
        
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info(f"設定エクスポート成功: {export_path}")
            return export_path
        except Exception as e:
            logger.error(f"設定エクスポートエラー: {str(e)}")
            return ""
    
    def import_config(self, import_path: str) -> bool:
        """
        設定ファイルをインポートする
        
        Args:
            import_path: インポート元のパス
        
        Returns:
            インポートが成功したかどうか
        """
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            
            # 基本的な検証
            if not isinstance(imported_config, dict):
                logger.error("無効な設定ファイル形式")
                return False
            
            # 安全な更新（必要なキーのみ）
            safe_config = {}
            for key in DEFAULT_CONFIG.keys():
                if key in imported_config:
                    safe_config[key] = imported_config[key]
            
            # 設定の更新と保存
            return self.save_config(safe_config)
        except Exception as e:
            logger.error(f"設定インポートエラー: {str(e)}")
            return False
    
    def update_from_env(self) -> None:
        """
        環境変数から設定を更新する
        環境変数は設定ファイルよりも優先される
        """
        # PayPal API認証情報とアプリ設定のマッピング
        env_mapping = {
            # PayPal API認証情報
            "PAYPAL_CLIENT_ID": "paypal_client_id",
            "PAYPAL_CLIENT_SECRET": "paypal_client_secret",
            "PAYPAL_MODE": "paypal_mode",
            # Stripe API認証情報
            "STRIPE_SECRET_KEY": "stripe_secret_key_test",  # デフォルトはテスト用
            "STRIPE_SECRET_KEY_TEST": "stripe_secret_key_test",
            "STRIPE_SECRET_KEY_LIVE": "stripe_secret_key_live",
            "STRIPE_PUBLISHABLE_KEY": "stripe_publishable_key_test",  # デフォルトはテスト用
            "STRIPE_PUBLISHABLE_KEY_TEST": "stripe_publishable_key_test",
            "STRIPE_PUBLISHABLE_KEY_LIVE": "stripe_publishable_key_live",
            "STRIPE_WEBHOOK_SECRET": "stripe_webhook_secret",
            "STRIPE_MODE": "stripe_mode",
            # 決済プロバイダー設定
            "DEFAULT_PAYMENT_PROVIDER": "default_payment_provider",
            # アプリ設定
            "DEFAULT_CURRENCY": "default_currency",
            "DEFAULT_AMOUNT": "default_amount",
            "ENABLE_CUSTOMER_EXTRACTION": "enable_customer_extraction",
            "ENABLE_AMOUNT_EXTRACTION": "enable_amount_extraction",
            "USE_AI_OCR": "use_ai_ocr",
            "OCR_METHOD": "ocr_method",
            "OCR_ENDPOINT": "ocr_endpoint",
            # セキュリティ設定
            "ENCRYPT_API_KEYS": "encrypt_api_keys",
            # 決済リンク設定
            "PAYMENT_LINK_EXPIRE_DAYS": "payment_link_expire_days"
        }
        
        updated = False
        for env_key, config_key in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                # 型変換処理
                if config_key in ["default_amount", "payment_link_expire_days"]:
                    try:
                        env_value = int(env_value)
                    except ValueError:
                        logger.warning(f"環境変数{env_key}の値を整数に変換できませんでした: {env_value}")
                        continue
                elif config_key in ["use_ai_ocr", "encrypt_api_keys"]:
                    env_value = env_value.lower() in ["true", "1", "yes"]
                elif config_key in ["enabled_payment_providers"] and isinstance(env_value, str):
                    # カンマ区切りの文字列をリストに変換
                    env_value = [provider.strip() for provider in env_value.split(",")]
                
                # 設定を更新
                if env_value != self.config.get(config_key):
                    self.config[config_key] = env_value
                    updated = True
                    logger.debug(f"環境変数から設定を更新: {config_key} = {env_value}")
        
        # セキュリティ関連の設定を追加
        self.config["admin_username"] = os.getenv("ADMIN_USERNAME", "admin")
        self.config["admin_password"] = os.getenv("ADMIN_PASSWORD", "")
        self.config["secret_key"] = os.getenv("SECRET_KEY", secrets.token_hex(16))
        self.config["enable_https"] = os.getenv("ENABLE_HTTPS", "").lower() in ["true", "1", "yes"]
        
        if updated:
            # 設定ファイルには認証情報を含めないようにする
            safe_config = self.config.copy()
            if "admin_username" in safe_config: del safe_config["admin_username"]
            if "admin_password" in safe_config: del safe_config["admin_password"]
            if "secret_key" in safe_config: del safe_config["secret_key"]
            
            self.save_config(safe_config)
            logger.info("環境変数から設定を更新しました")
            
    def test_paypal_connection(self, client_id: Optional[str] = None, client_secret: Optional[str] = None, mode: Optional[str] = None) -> Tuple[bool, str]:
        """
        PayPal APIへの接続をテストする
        
        Returns:
            接続が成功したかどうか
        """
        # Use provided credentials if available, otherwise use stored config
        test_client_id = client_id if client_id is not None else self.config.get('paypal_client_id')
        test_client_secret = client_secret if client_secret is not None else self.config.get('paypal_client_secret')
        test_mode = mode if mode is not None else self.config.get('paypal_mode', 'sandbox')

        if not test_client_id or not test_client_secret:
            msg = "PayPal Client ID または Client Secret が設定されていません。"
            logger.error(msg)
            return False, msg

        try:
            paypalrestsdk.configure({
                "mode": test_mode,
                "client_id": test_client_id,
                "client_secret": test_client_secret
            })
            
            # Perform a simple API call to test the connection with timeout
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            # PayPalRestSDKのHTTPクライアントを設定
            session = requests.Session()
            retry_strategy = Retry(
                total=2,  # 最大2回リトライ
                backoff_factor=1,  # リトライ間の待機時間係数
                status_forcelist=[429, 500, 502, 503, 504]  # リトライするHTTPステータスコード
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            # タイムアウト設定を追加してAPI呼び出し
            paypalrestsdk.api.default_api_client.session = session
            payments = paypalrestsdk.Payment.all({'count': 1}, {'timeout': (5, 10)})  # 接続タイムアウト5秒、読み取りタイムアウト10秒
            
            # If the above call doesn't raise an exception, the connection is successful
            msg = "PayPal APIへの接続に成功しました。"
            logger.info(msg)
            return True, msg
        except paypalrestsdk.exceptions.PayPalError as e:
            # Handle PayPal specific errors (e.g., authentication failure)
            error_message = str(e)
            if hasattr(e, 'message') and isinstance(e.message, dict) and 'message' in e.message: # type: ignore
                error_message = e.message['message'] # type: ignore
            elif hasattr(e, 'response') and hasattr(e.response, 'text'): # type: ignore
                 try:
                    error_details = json.loads(e.response.text) # type: ignore
                    if 'error_description' in error_details:
                        error_message = error_details['error_description']
                    elif 'message' in error_details:
                        error_message = error_details['message']
                 except json.JSONDecodeError:
                    error_message = e.response.text # type: ignore

            full_msg = f"PayPal API接続テストエラー: {error_message}"
            logger.error(full_msg)
            return False, full_msg
        except Exception as e:
            # Handle other exceptions (e.g., network issues)
            full_msg = f"PayPal API接続テスト中に予期せぬエラーが発生しました: {str(e)}"
            logger.error(full_msg)
            return False, full_msg
    
    def validate_stripe_config(self) -> Dict[str, Any]:
        """
        Stripe設定が有効かどうかを検証する
        
        Returns:
            検証結果を含む辞書
        """
        result = {
            'valid': False,
            'errors': [],
            'warnings': [],
            'details': {}
        }
        
        stripe_mode = self.config.get('stripe_mode', 'test')
        
        # 必要なキーをモードに応じて設定
        if stripe_mode == 'test':
            secret_key = self.config.get('stripe_secret_key_test', '')
            publishable_key = self.config.get('stripe_publishable_key_test', '')
            key_prefix_secret = 'sk_test_'
            key_prefix_publishable = 'pk_test_'
        else:  # live mode
            secret_key = self.config.get('stripe_secret_key_live', '')
            publishable_key = self.config.get('stripe_publishable_key_live', '')
            key_prefix_secret = 'sk_live_'
            key_prefix_publishable = 'pk_live_'
        
        # Secret Key の検証
        if not secret_key:
            result['errors'].append(f'Stripe Secret Key ({stripe_mode}モード用) が設定されていません')
        elif not secret_key.startswith(key_prefix_secret):
            result['errors'].append(f'Stripe Secret Key の形式が {stripe_mode} モードに適していません')
        else:
            result['details']['secret_key_valid'] = True
        
        # Publishable Key の検証
        if not publishable_key:
            result['errors'].append(f'Stripe Publishable Key ({stripe_mode}モード用) が設定されていません')
        elif not publishable_key.startswith(key_prefix_publishable):
            result['errors'].append(f'Stripe Publishable Key の形式が {stripe_mode} モードに適していません')
        else:
            result['details']['publishable_key_valid'] = True
        
        # Webhook Secret の検証（オプション）
        webhook_secret = self.config.get('stripe_webhook_secret', '')
        if webhook_secret and not webhook_secret.startswith('whsec_'):
            result['warnings'].append('Stripe Webhook Secret の形式が正しくない可能性があります')
        elif webhook_secret:
            result['details']['webhook_secret_valid'] = True
        
        # 決済プロバイダー設定の検証
        default_provider = self.config.get('default_payment_provider', 'paypal')
        enabled_providers = self.config.get('enabled_payment_providers', ['paypal'])
        
        if default_provider not in enabled_providers:
            result['warnings'].append(f'デフォルト決済プロバイダー "{default_provider}" が有効なプロバイダーリストにありません')
        
        # 通貨設定の検証
        supported_currencies = self.config.get('supported_currencies', ['JPY'])
        default_currency = self.config.get('default_currency', 'JPY')
        
        if default_currency not in supported_currencies:
            result['warnings'].append(f'デフォルト通貨 "{default_currency}" がサポート通貨リストにありません')
        
        # 全体的な有効性判定
        result['valid'] = len(result['errors']) == 0
        result['details']['stripe_mode'] = stripe_mode
        result['details']['enabled_providers'] = enabled_providers
        result['details']['default_provider'] = default_provider
        
        return result
    
    def test_stripe_connection(self, secret_key: Optional[str] = None, mode: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Stripe APIへの接続をテストする
        
        Args:
            secret_key: テスト用のSecret Key（指定しない場合は設定から取得）
            mode: テスト用のモード（指定しない場合は設定から取得）
        
        Returns:
            接続が成功したかどうか、メッセージ、詳細情報
        """
        try:
            import stripe
        except ImportError:
            return False, "Stripe ライブラリがインストールされていません", {}
        
        test_mode = mode if mode is not None else self.config.get('stripe_mode', 'test')
        
        if secret_key is None:
            if test_mode == 'test':
                test_secret_key = self.config.get('stripe_secret_key_test', '')
            else:
                test_secret_key = self.config.get('stripe_secret_key_live', '')
        else:
            test_secret_key = secret_key
        
        if not test_secret_key:
            return False, f"Stripe Secret Key ({test_mode}モード用) が設定されていません", {}
        
        # 復号化処理（暗号化されている場合）
        decrypted_key = self._decrypt_api_key(test_secret_key)
        if decrypted_key:
            test_secret_key = decrypted_key
        
        try:
            # Stripe APIキーを設定
            stripe.api_key = test_secret_key
            
            # アカウント情報を取得してテスト
            account = stripe.Account.retrieve()
            
            # テスト環境の場合は決済機能を有効と判定
            is_test_mode = test_mode == 'test'
            effective_charges_enabled = account.charges_enabled or is_test_mode
            
            details = {
                'account_id': account.id,
                'business_profile': account.business_profile.name if account.business_profile else None,
                'country': account.country,
                'default_currency': account.default_currency,
                'charges_enabled': effective_charges_enabled,
                'payouts_enabled': account.payouts_enabled,
                'details_submitted': account.details_submitted,
                'mode': test_mode,
                'is_test_mode': is_test_mode,
                'raw_charges_enabled': account.charges_enabled
            }
            
            msg = f"Stripe API ({test_mode}モード) への接続に成功しました"
            logger.info(msg)
            return True, msg, details
            
        except stripe.error.AuthenticationError as e:
            msg = f"Stripe API認証エラー: {str(e)}"
            logger.error(msg)
            return False, msg, {}
        except stripe.error.APIConnectionError as e:
            msg = f"Stripe API接続エラー: {str(e)}"
            logger.error(msg)
            return False, msg, {}
        except Exception as e:
            msg = f"Stripe API接続テスト中に予期せぬエラーが発生しました: {str(e)}"
            logger.error(msg)
            return False, msg, {}
    
    def get_encryption_key(self) -> bytes:
        """
        暗号化キーを取得または生成する
        
        Returns:
            暗号化キー
        """
        key_file = os.path.join(os.path.dirname(self.config_path), '.encryption_key')
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # 新しいキーを生成
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            
            # ファイルのパーミッションを制限
            os.chmod(key_file, 0o600)
            logger.info("新しい暗号化キーを生成しました")
            return key
    
    def _encrypt_api_key(self, api_key: str) -> str:
        """
        APIキーを暗号化する
        
        Args:
            api_key: 暗号化するAPIキー
        
        Returns:
            暗号化されたAPIキー（Base64エンコード）
        """
        if not self.config.get('encrypt_api_keys', True):
            return api_key
        
        if not api_key:
            return api_key
        
        try:
            key = self.get_encryption_key()
            f = Fernet(key)
            encrypted = f.encrypt(api_key.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"APIキー暗号化エラー: {str(e)}")
            return api_key
    
    def _decrypt_api_key(self, encrypted_api_key: str) -> Optional[str]:
        """
        APIキーを復号化する
        
        Args:
            encrypted_api_key: 暗号化されたAPIキー
        
        Returns:
            復号化されたAPIキー（失敗時はNone）
        """
        if not self.config.get('encrypt_api_keys', True):
            return None
        
        if not encrypted_api_key:
            return None
        
        try:
            key = self.get_encryption_key()
            f = Fernet(key)
            encrypted_bytes = base64.b64decode(encrypted_api_key.encode())
            decrypted = f.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.debug(f"APIキー復号化スキップ（平文の可能性）: {str(e)}")
            return None
    
    def save_stripe_config(self, stripe_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stripe設定を安全に保存する（暗号化対応）
        
        Args:
            stripe_config: Stripe設定辞書
        
        Returns:
            保存結果
        """
        result = {
            'success': False,
            'message': '',
            'encrypted_fields': []
        }
        
        try:
            # 機密情報を暗号化
            sensitive_fields = [
                'stripe_secret_key_test',
                'stripe_secret_key_live',
                'stripe_webhook_secret'
            ]
            
            config_to_save = stripe_config.copy()
            
            if self.config.get('encrypt_api_keys', True):
                for field in sensitive_fields:
                    if field in config_to_save and config_to_save[field]:
                        encrypted_value = self._encrypt_api_key(config_to_save[field])
                        config_to_save[field] = encrypted_value
                        result['encrypted_fields'].append(field)
            
            # 設定を保存
            success = self.save_config(config_to_save)
            
            if success:
                result['success'] = True
                result['message'] = 'Stripe設定が正常に保存されました'
                if result['encrypted_fields']:
                    result['message'] += f' (暗号化フィールド: {", ".join(result["encrypted_fields"])})'
            else:
                result['message'] = '設定保存に失敗しました'
            
            return result
            
        except Exception as e:
            result['message'] = f'Stripe設定保存エラー: {str(e)}'
            logger.error(result['message'])
            return result
    
    def get_payment_providers_status(self) -> Dict[str, Any]:
        """
        利用可能な決済プロバイダーのステータスを取得する
        
        Returns:
            プロバイダーステータス辞書
        """
        status = {
            'providers': {},
            'default_provider': self.config.get('default_payment_provider', 'paypal'),
            'enabled_providers': self.config.get('enabled_payment_providers', ['paypal'])
        }
        
        # PayPal ステータス
        paypal_valid = self.validate_paypal_config()
        paypal_connection = False
        
        if paypal_valid:
            try:
                paypal_connection, _ = self.test_paypal_connection()
            except:
                paypal_connection = False
        
        status['providers']['paypal'] = {
            'name': 'PayPal',
            'configured': paypal_valid,
            'connected': paypal_connection,
            'mode': self.config.get('paypal_mode', 'sandbox')
        }
        
        # Stripe ステータス
        stripe_validation = self.validate_stripe_config()
        stripe_connection = False
        stripe_details = {}
        
        if stripe_validation['valid']:
            try:
                stripe_connection, _, stripe_details = self.test_stripe_connection()
            except:
                stripe_connection = False
        
        status['providers']['stripe'] = {
            'name': 'Stripe',
            'configured': stripe_validation['valid'],
            'connected': stripe_connection,
            'mode': self.config.get('stripe_mode', 'test'),
            'details': stripe_details
        }
        
        return status
    
    def validate_config_schema(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        設定スキーマの包括的な検証
        
        Args:
            config: 検証する設定辞書
        
        Returns:
            検証結果
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'sections': {}
        }
        
        # PayPal設定の検証
        paypal_section = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        if 'paypal_client_id' in config or 'paypal_client_secret' in config:
            if not config.get('paypal_client_id'):
                paypal_section['errors'].append('PayPal Client ID が設定されていません')
            if not config.get('paypal_client_secret'):
                paypal_section['errors'].append('PayPal Client Secret が設定されていません')
            
            paypal_mode = config.get('paypal_mode', 'sandbox')
            if paypal_mode not in ['sandbox', 'live']:
                paypal_section['errors'].append(f'PayPal モードが無効です: {paypal_mode}')
        
        paypal_section['valid'] = len(paypal_section['errors']) == 0
        result['sections']['paypal'] = paypal_section
        
        # Stripe設定の検証
        stripe_validation = self.validate_stripe_config()
        result['sections']['stripe'] = {
            'valid': stripe_validation['valid'],
            'errors': stripe_validation['errors'],
            'warnings': stripe_validation['warnings']
        }
        
        # 通貨設定の検証
        currency_section = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        valid_currencies = ['JPY', 'USD', 'EUR', 'GBP', 'AUD', 'CAD', 'CHF', 'SEK', 'NOK', 'DKK']
        default_currency = config.get('default_currency', 'JPY')
        supported_currencies = config.get('supported_currencies', ['JPY'])
        
        if default_currency not in valid_currencies:
            currency_section['warnings'].append(f'デフォルト通貨 "{default_currency}" は一般的ではありません')
        
        for currency in supported_currencies:
            if currency not in valid_currencies:
                currency_section['warnings'].append(f'サポート通貨 "{currency}" は一般的ではありません')
        
        result['sections']['currency'] = currency_section
        
        # 決済プロバイダー設定の検証
        provider_section = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        valid_providers = ['paypal', 'stripe']
        default_provider = config.get('default_payment_provider', 'paypal')
        enabled_providers = config.get('enabled_payment_providers', ['paypal'])
        
        if default_provider not in valid_providers:
            provider_section['errors'].append(f'無効なデフォルト決済プロバイダー: {default_provider}')
        
        for provider in enabled_providers:
            if provider not in valid_providers:
                provider_section['errors'].append(f'無効な決済プロバイダー: {provider}')
        
        if default_provider not in enabled_providers:
            provider_section['warnings'].append('デフォルト決済プロバイダーが有効プロバイダーリストにありません')
        
        provider_section['valid'] = len(provider_section['errors']) == 0
        result['sections']['payment_providers'] = provider_section
        
        # 全体の有効性判定
        result['valid'] = all(section['valid'] for section in result['sections'].values())
        
        # 全エラー・警告の統合
        for section in result['sections'].values():
            result['errors'].extend(section['errors'])
            result['warnings'].extend(section['warnings'])
        
        return result
    
    def export_config_with_encryption(self, export_path: Optional[str] = None, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        暗号化対応の設定エクスポート
        
        Args:
            export_path: エクスポート先のパス
            include_sensitive: 機密情報を含めるかどうか
        
        Returns:
            エクスポート結果
        """
        result = {
            'success': False,
            'message': '',
            'export_path': '',
            'excluded_fields': []
        }
        
        try:
            if export_path is None:
                export_dir = os.path.dirname(self.config_path)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                export_path = os.path.join(export_dir, f"settings_export_{timestamp}.json")
            
            # エクスポート用の設定を準備
            export_config = self.config.copy()
            
            # 機密情報の除外
            sensitive_fields = [
                'paypal_client_secret',
                'stripe_secret_key_test',
                'stripe_secret_key_live',
                'stripe_webhook_secret',
                'admin_password',
                'secret_key'
            ]
            
            if not include_sensitive:
                for field in sensitive_fields:
                    if field in export_config:
                        del export_config[field]
                        result['excluded_fields'].append(field)
            
            # メタデータを追加
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'export_version': '1.0',
                'include_sensitive': include_sensitive,
                'config': export_config
            }
            
            # ファイルに保存
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            result['success'] = True
            result['message'] = '設定エクスポートが完了しました'
            result['export_path'] = export_path
            
            if result['excluded_fields']:
                result['message'] += f' (除外フィールド: {", ".join(result["excluded_fields"])})'
            
            logger.info(f"設定エクスポート成功: {export_path}")
            return result
            
        except Exception as e:
            result['message'] = f'設定エクスポートエラー: {str(e)}'
            logger.error(result['message'])
            return result
    
    def import_config_with_validation(self, import_path: str, validate_before_save: bool = True) -> Dict[str, Any]:
        """
        バリデーション機能付きの設定インポート
        
        Args:
            import_path: インポート元のパス
            validate_before_save: 保存前にバリデーションを行うかどうか
        
        Returns:
            インポート結果
        """
        result = {
            'success': False,
            'message': '',
            'validation_result': {},
            'imported_fields': []
        }
        
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # 基本的な形式チェック
            if not isinstance(import_data, dict):
                result['message'] = '無効な設定ファイル形式です'
                return result
            
            # バージョン別のインポート処理
            if 'config' in import_data:
                # 新形式（メタデータ付き）
                imported_config = import_data['config']
                import_version = import_data.get('export_version', '1.0')
                logger.info(f"設定インポート: バージョン {import_version}")
            else:
                # 旧形式（設定のみ）
                imported_config = import_data
            
            # バリデーション実行
            if validate_before_save:
                validation_result = self.validate_config_schema(imported_config)
                result['validation_result'] = validation_result
                
                if not validation_result['valid']:
                    result['message'] = f"設定バリデーションエラー: {', '.join(validation_result['errors'])}"
                    return result
            
            # 安全な更新（既知のキーのみ）
            safe_config = {}
            for key in DEFAULT_CONFIG.keys():
                if key in imported_config:
                    safe_config[key] = imported_config[key]
                    result['imported_fields'].append(key)
            
            # 追加の安全なキー（動的に追加される可能性のあるキー）
            additional_safe_keys = [
                'admin_username',
                'admin_password',
                'secret_key'
            ]
            
            for key in additional_safe_keys:
                if key in imported_config:
                    safe_config[key] = imported_config[key]
                    result['imported_fields'].append(key)
            
            # 設定の更新と保存
            success = self.save_config(safe_config)
            
            if success:
                result['success'] = True
                result['message'] = f'設定インポートが完了しました ({len(result["imported_fields"])} 項目)'
            else:
                result['message'] = '設定保存に失敗しました'
            
            return result
            
        except FileNotFoundError:
            result['message'] = 'インポートファイルが見つかりません'
            return result
        except json.JSONDecodeError as e:
            result['message'] = f'JSON解析エラー: {str(e)}'
            return result
        except Exception as e:
            result['message'] = f'設定インポートエラー: {str(e)}'
            logger.error(result['message'])
            return result


# シングルトンインスタンス
config_manager = ConfigManager()


def get_config() -> Dict[str, Any]:
    """
    現在の設定を取得する（ヘルパー関数）
    
    Returns:
        設定辞書
    """
    return config_manager.get_config()


def save_config(config: Dict[str, Any]) -> bool:
    """
    設定を保存する（ヘルパー関数）
    
    Args:
        config: 保存する設定
        
    Returns:
        保存が成功したかどうか
    """
    return config_manager.save_config(config)
