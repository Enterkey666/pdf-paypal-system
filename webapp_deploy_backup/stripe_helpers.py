#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe連携機能用のヘルパーモジュール
エラー耐性を高めた補助関数群
"""

import os
import logging
from typing import Dict, Any, Optional, Union, Tuple

# ロガー設定
logger = logging.getLogger(__name__)

# 既存のStripe連携モジュールをインポート
import stripe
import database

def get_stripe_credentials(user_id: int = None) -> Tuple[str, str, str]:
    """
    Stripe認証情報を取得（ユーザー固有設定優先、環境変数・システム設定で後方互換性）
    
    Args:
        user_id (int, optional): ユーザーID。指定がない場合はセッションから取得
        
    Returns:
        Tuple[str, str, str]: publishable_key, secret_key, mode
    """
    try:
        # ユーザーIDの決定（セッションから取得）
        if user_id is None:
            try:
                from flask import session
                user_id = session.get('user_id')
            except:
                user_id = None
        
        # ユーザー固有の設定を優先して取得
        if user_id:
            try:
                user_credentials = database.get_user_stripe_credentials(user_id)
                
                if user_credentials:
                    mode = user_credentials.get('mode', 'test')
                    
                    if mode == 'test':
                        publishable_key = user_credentials.get('publishable_key_test', '')
                        secret_key = user_credentials.get('secret_key_test', '')
                    else:  # live mode
                        publishable_key = user_credentials.get('publishable_key_live', '')
                        secret_key = user_credentials.get('secret_key_live', '')
                    
                    # ユーザー固有の設定が完全にある場合はそれを返す
                    if publishable_key and secret_key:
                        logger.info(f"ユーザーID {user_id} のStripe設定を使用: {mode}モード")
                        return str(publishable_key), str(secret_key), str(mode)
                    else:
                        logger.info(f"ユーザーID {user_id} のStripe設定が不完全なため、システム設定にフォールバック")
                        
            except Exception as e:
                logger.warning(f"ユーザーStripe設定取得エラー: {e}")
        
        # システム全体の設定にフォールバック
        logger.info("システム全体のStripe設定を使用")
        return get_system_stripe_credentials()
        
    except Exception as e:
        logger.error(f"Stripe認証情報取得エラー: {e}")
        return '', '', 'test'

def get_system_stripe_credentials() -> Tuple[str, str, str]:
    """
    システム全体のStripe認証情報を取得
    
    Returns:
        Tuple[str, str, str]: publishable_key, secret_key, mode
    """
    try:
        # 環境変数から認証情報を取得
        stripe_mode = os.environ.get('STRIPE_MODE', 'test')
        
        if stripe_mode == 'test':
            publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY_TEST', '')
            secret_key = os.environ.get('STRIPE_SECRET_KEY_TEST', '')
        else:  # live mode
            publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY_LIVE', '')
            secret_key = os.environ.get('STRIPE_SECRET_KEY_LIVE', '')
        
        # 後方互換性のため
        if not publishable_key:
            publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
        if not secret_key:
            secret_key = os.environ.get('STRIPE_SECRET_KEY', '')
        
        # 環境変数に設定がない場合はデータベースから取得
        if not publishable_key or not secret_key:
            try:
                # デフォルトユーザー設定を取得
                from config_manager import get_config
                config = get_config()
                
                stripe_mode = config.get('stripe_mode', 'test')
                
                if stripe_mode == 'test':
                    publishable_key = config.get('stripe_publishable_key_test', '')
                    secret_key = config.get('stripe_secret_key_test', '')
                else:  # live mode
                    publishable_key = config.get('stripe_publishable_key_live', '')
                    secret_key = config.get('stripe_secret_key_live', '')
                
                # 後方互換性のため
                if not publishable_key:
                    publishable_key = config.get('stripe_publishable_key', '')
                if not secret_key:
                    secret_key = config.get('stripe_secret_key', '')
                    
            except Exception as db_err:
                logger.warning(f"データベースからStripe設定取得エラー: {str(db_err)}")
        
        logger.info(f"システムStripe設定: {stripe_mode}モード")
        # 常に文字列型を返す
        return str(publishable_key), str(secret_key), str(stripe_mode)
        
    except Exception as e:
        logger.error(f"システムStripe認証情報取得エラー: {e}")
        # エラー時はデフォルト値を返す
        return '', '', 'test'
