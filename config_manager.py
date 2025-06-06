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
from typing import Dict, Any, Optional, Tuple

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
            # 既存のキーを更新
            for key, value in config.items():
                if key in self.config:
                    self.config[key] = value
            
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
        環境変数から設定を更新する（.envファイルとの互換性用）
        """
        env_mapping = {
            "PAYPAL_CLIENT_ID": "paypal_client_id",
            "PAYPAL_CLIENT_SECRET": "paypal_client_secret",
            "PAYPAL_MODE": "paypal_mode"
        }
        
        updated = False
        for env_key, config_key in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value and env_value != self.config.get(config_key):
                self.config[config_key] = env_value
                updated = True
        
        if updated:
            self.save_config(self.config)
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
            
            # Perform a simple API call to test the connection
            payments = paypalrestsdk.Payment.all({'count': 1}) # type: ignore
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
