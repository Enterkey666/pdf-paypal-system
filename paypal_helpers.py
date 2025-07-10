"""
PayPal連携機能用のヘルパーモジュール
エラー耐性を高めた補助関数群
"""

import os
import logging
import time
from typing import Dict, Any, Optional, Union, Tuple

# ロガー設定
logger = logging.getLogger(__name__)

# 既存のPayPal連携モジュールをインポート
from paypal_utils import get_paypal_access_token
import database

def safe_test_paypal_connection(client_id: str = None, client_secret: str = None, 
                               paypal_mode: Any = None, user_id: str = None) -> Dict[str, Any]:
    """
    エラー耐性を高めたPayPal接続テスト関数
    
    Args:
        client_id (str, optional): PayPal Client ID
        client_secret (str, optional): PayPal Client Secret
        paypal_mode (Any, optional): PayPalモード（sandbox/live）
        user_id (str, optional): ユーザーID
        
    Returns:
        Dict[str, Any]: 接続テスト結果
            - success (bool): 接続成功したかどうか
            - message (str): 結果メッセージ
            - details (Dict): 詳細情報
    """
    try:
        logger.info(f"PayPal接続テスト開始: user_id={user_id}")
        
        # 入力引数の型と値を検証してログ出力
        logger.info(f"入力パラメータ検証: client_id型={type(client_id).__name__}, " 
                    f"client_secret型={type(client_secret).__name__}, "
                    f"paypal_mode型={type(paypal_mode).__name__}, 値={paypal_mode}")
        
        # 必ず文字列型に変換
        paypal_mode_str = str(paypal_mode) if paypal_mode is not None else "sandbox"
        
        # 詳細ログ
        logger.info(f"PayPal接続テスト: モード文字列化済み={paypal_mode_str}")
        
        # アクセストークンを取得
        try:
            token = get_paypal_access_token(client_id, client_secret, paypal_mode_str, user_id)
        except Exception as token_err:
            logger.error(f"PayPalアクセストークン取得エラー: {str(token_err)}")
            return {
                'success': False, 
                'message': f'PayPalアクセストークン取得中にエラーが発生: {str(token_err)}',
                'details': {'error_type': type(token_err).__name__}
            }
        
        # トークン取得結果を検証
        if token:
            logger.info("PayPal接続テスト成功")
            return {
                'success': True,
                'message': 'PayPal APIに正常に接続できました',
                'details': {'mode': paypal_mode_str}
            }
        else:
            logger.warning("PayPal接続テスト失敗: トークンが取得できませんでした")
            return {
                'success': False,
                'message': 'PayPal APIに接続できませんでした',
                'details': {'mode': paypal_mode_str}
            }
            
    except Exception as e:
        logger.error(f"PayPal接続テスト中の予期せぬエラー: {str(e)}")
        return {
            'success': False,
            'message': f'エラーが発生しました: {str(e)}',
            'details': {'error_type': type(e).__name__}
        }
        
def get_paypal_settings(user_id: str = None) -> Tuple[str, str, str]:
    """
    ユーザーIDからPayPal設定を取得し、常に文字列型で返す
    
    Args:
        user_id (str, optional): ユーザーID
        
    Returns:
        Tuple[str, str, str]: client_id, client_secret, paypal_mode
    """
    client_id = ''
    client_secret = ''
    paypal_mode = 'sandbox'  # デフォルト値
    
    try:
        # データベースからユーザー設定を取得
        if user_id:
            settings = database.get_paypal_settings(user_id)
            if settings:
                client_id = settings.get('client_id', '')
                client_secret = settings.get('client_secret', '')
                paypal_mode = settings.get('mode', 'sandbox')
                logger.info(f"ユーザーID {user_id} の設定を使用")
                
        # データベースから取得できなかった場合は環境変数から取得
        if not client_id or not client_secret:
            # 両方の設定モジュールから取得を試みる
            try:
                from config_manager import get_config
                config = get_config()
                if not client_id:
                    client_id = config.get('client_id', '')
                if not client_id:
                    client_id = config.get('paypal_client_id', '')
                if not client_secret:
                    client_secret = config.get('client_secret', '')
                if not client_secret:
                    client_secret = config.get('paypal_client_secret', '')
                if not paypal_mode:
                    paypal_mode = config.get('paypal_mode', '')
            except Exception as config_err:
                logger.warning(f"config_manager取得エラー: {str(config_err)}")
                
            try:
                from config import get_config as get_app_config
                app_config = get_app_config()
                if not client_id:
                    client_id = app_config.get('PAYPAL_CLIENT_ID', app_config.get('paypal_client_id', ''))
                if not client_secret:
                    client_secret = app_config.get('PAYPAL_CLIENT_SECRET', app_config.get('paypal_client_secret', ''))
                if not paypal_mode:
                    paypal_mode = app_config.get('PAYPAL_MODE', app_config.get('paypal_mode', 'sandbox'))
            except Exception as app_config_err:
                logger.warning(f"app_config取得エラー: {str(app_config_err)}")
                
            # 環境変数から直接取得（最終手段）
            if not client_id:
                client_id = os.environ.get('PAYPAL_CLIENT_ID', '')
            if not client_secret:
                client_secret = os.environ.get('PAYPAL_CLIENT_SECRET', '')
            if not paypal_mode:
                paypal_mode = os.environ.get('PAYPAL_MODE', 'sandbox')
        
        # 必ず文字列型で返す
        return str(client_id), str(client_secret), str(paypal_mode)
        
    except Exception as e:
        logger.error(f"PayPal設定取得エラー: {str(e)}")
        return '', '', 'sandbox'


def generate_payment_link(customer_name: str, amount: Any, filename: str = None, user_id: str = None) -> Dict[str, Any]:
    """
    PDFプロセッサーやアプリケーションから呼び出される決済リンク生成のための統一インターフェース
    
    Args:
        customer_name (str): 顧客名
        amount (Any): 金額（数値または文字列）
        filename (str, optional): 元のファイル名
        user_id (str, optional): ユーザーID
        
    Returns:
        Dict[str, Any]: 決済リンク情報
    """
    logger.info(f"決済リンク作成開始: 顧客={customer_name}, 金額={amount}, ファイル={filename}")
    
    try:
        # 数値形式の正規化
        if isinstance(amount, str):
            # カンマ、¥記号、全角¥記号、円記号を削除
            amount_str = amount.replace(',', '').replace('¥', '').replace('￥', '').replace('円', '').strip()
            try:
                amount_value = float(amount_str)
            except ValueError:
                logger.error(f"金額の数値変換に失敗: {amount}")
                return {
                    'success': False,
                    'error': f'金額の形式が無効です: {amount}',
                    'payment_link': None
                }
        else:
            amount_value = float(amount)
            
        # 金額の妥当性チェック
        if amount_value <= 0:
            logger.error(f"金額が0以下です: {amount_value}")
            return {
                'success': False,
                'error': '金額は0より大きい値である必要があります',
                'payment_link': None
            }
        
        # ゲスト決済リンクを優先的に使用（より制約が少ない）
        try:
            result = create_guest_payment_link(customer_name, amount_value, user_id)
            logger.info(f"ゲスト決済リンク生成結果: {result}")
            
            if result.get('success'):
                # 成功した場合は結果をそのまま返す
                if filename:
                    # 処理履歴に保存を試みる
                    try:
                        database.save_processing_history(
                            user_id or 'system', 
                            filename, 
                            customer_name, 
                            amount_value, 
                            result.get('payment_link', ''), 
                            result
                        )
                    except Exception as db_err:
                        logger.warning(f"処理履歴保存エラー: {str(db_err)}")
                        
                return result
            else:
                # ゲスト決済が失敗した場合は通常の決済リンクを試みる
                logger.warning(f"ゲスト決済リンク生成失敗: {result.get('error')}、通常の決済リンクを試みます")
                result = create_payment_link(customer_name, amount_value, user_id)
                
                if result.get('success'):
                    if filename:
                        # 処理履歴に保存を試みる
                        try:
                            database.save_processing_history(
                                user_id or 'system', 
                                filename, 
                                customer_name, 
                                amount_value, 
                                result.get('payment_link', ''), 
                                result
                            )
                        except Exception as db_err:
                            logger.warning(f"処理履歴保存エラー: {str(db_err)}")
                    
                    return result
                else:
                    logger.error(f"通常の決済リンク生成も失敗: {result.get('error')}")
                    return result
                    
        except Exception as e:
            logger.error(f"決済リンク生成中の例外: {str(e)}")
            return {
                'success': False,
                'error': f'決済リンク生成エラー: {str(e)}',
                'payment_link': None
            }
    
    except Exception as outer_e:
        logger.error(f"決済リンク生成の外部エラー: {str(outer_e)}")
        return {
            'success': False,
            'error': f'処理エラー: {str(outer_e)}',
            'payment_link': None
        }
