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
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# ロガー設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# デフォルト設定
DEFAULT_CONFIG = {
    "paypal_mode": "sandbox",
    "paypal_client_id": "",
    "paypal_client_secret": "",
    "default_currency": "JPY",
    "enable_customer_extraction": "1",
    "enable_amount_extraction": "1",
    "use_ai_ocr": False,
    "default_amount": 1000
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
            # アプリ設定
            "DEFAULT_CURRENCY": "default_currency",
            "DEFAULT_AMOUNT": "default_amount",
            "ENABLE_CUSTOMER_EXTRACTION": "enable_customer_extraction",
            "ENABLE_AMOUNT_EXTRACTION": "enable_amount_extraction",
            "USE_AI_OCR": "use_ai_ocr",
            "OCR_METHOD": "ocr_method",
            "OCR_ENDPOINT": "ocr_endpoint"
        }
        
        updated = False
        for env_key, config_key in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                # 型変換処理
                if config_key in ["default_amount"]:
                    try:
                        env_value = int(env_value)
                    except ValueError:
                        logger.warning(f"環境変数{env_key}の値を整数に変換できませんでした: {env_value}")
                        continue
                elif config_key in ["use_ai_ocr"]:
                    env_value = env_value.lower() in ["true", "1", "yes"]
                
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
