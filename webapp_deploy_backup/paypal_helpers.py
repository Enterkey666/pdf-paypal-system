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
import os

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
            token = get_paypal_access_token(client_id, client_secret, paypal_mode_str)
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


def get_paypal_credentials(user_id: int = None) -> Tuple[str, str, str]:
    """
    PayPal認証情報を取得（ユーザー固有設定優先、環境変数・システム設定で後方互換性）
    
    Args:
        user_id (int, optional): ユーザーID。指定がない場合はセッションから取得
        
    Returns:
        Tuple[str, str, str]: client_id, client_secret, paypal_mode
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
                user_credentials = database.get_user_paypal_credentials(user_id)
                
                if user_credentials:
                    client_id = user_credentials.get('client_id', '')
                    client_secret = user_credentials.get('client_secret', '')
                    mode = user_credentials.get('mode', 'sandbox')
                    
                    # ユーザー固有の設定が完全にある場合はそれを返す
                    if client_id and client_secret:
                        logger.info(f"ユーザーID {user_id} のPayPal設定を使用: {mode}モード")
                        return str(client_id), str(client_secret), str(mode)
                    else:
                        logger.info(f"ユーザーID {user_id} のPayPal設定が不完全なため、システム設定にフォールバック")
                        
            except Exception as e:
                logger.warning(f"ユーザーPayPal設定取得エラー: {e}")
        
        # システム全体の設定にフォールバック
        logger.info("システム全体のPayPal設定を使用")
        return get_system_paypal_credentials()
        
    except Exception as e:
        logger.error(f"PayPal認証情報取得エラー: {e}")
        return '', '', 'sandbox'

def get_system_paypal_credentials() -> Tuple[str, str, str]:
    """
    システム全体のPayPal認証情報を取得
    
    Returns:
        Tuple[str, str, str]: client_id, client_secret, paypal_mode
    """
    try:
        # 環境変数から認証情報を取得
        client_id = os.environ.get('PAYPAL_CLIENT_ID', '')
        client_secret = os.environ.get('PAYPAL_CLIENT_SECRET', '')
        paypal_mode = os.environ.get('PAYPAL_MODE', 'sandbox')
        
        # 環境変数に設定がない場合はデータベースから取得
        if not client_id or not client_secret:
            try:
                # config_managerから設定を取得
                from config_manager import get_config
                config = get_config()
                
                if not client_id:
                    client_id = config.get('client_id', '') or config.get('paypal_client_id', '')
                if not client_secret:
                    client_secret = config.get('client_secret', '') or config.get('paypal_client_secret', '')
                if not paypal_mode:
                    paypal_mode = config.get('paypal_mode', 'sandbox')
                    
            except Exception as db_err:
                logger.warning(f"データベースからPayPal設定取得エラー: {str(db_err)}")
        
        logger.info(f"システムPayPal設定: {paypal_mode}モード")
        # 常に文字列型を返す
        return str(client_id), str(client_secret), str(paypal_mode)
        
    except Exception as e:
        logger.error(f"システムPayPal認証情報取得エラー: {str(e)}")
        # エラー時はデフォルト値を返す
        return '', '', 'sandbox'


def create_guest_payment_link(customer_name: str, amount: float, user_id: str = None) -> Dict[str, Any]:
    """
    ゲスト決済リンクを作成する
    
    Args:
        customer_name (str): 顧客名
        amount (float): 金額
        user_id (str, optional): ユーザーID
        
    Returns:
        Dict[str, Any]: 決済リンク情報
    """
    logger.info(f"ゲスト決済リンク作成: 顧客={customer_name}, 金額={amount}")
    
    try:
        # payment_utils.pyのget_default_payment_providerを使用してデフォルトプロバイダーを取得
        from payment_utils import get_default_payment_provider, create_payment_link
        provider = get_default_payment_provider()
        
        logger.info(f"デフォルト決済プロバイダー: {provider}")
        
        # 適切なプロバイダーを使用して決済リンクを作成
        result = create_payment_link(
            provider=provider,
            amount=amount,
            customer_name=customer_name,
            description=f"ゲスト決済: {customer_name}"
        )
        
        # 結果を統一フォーマットに変換
        if result.get('success'):
            return {
                'success': True,
                'payment_link': result.get('payment_link'),
                'provider': result.get('provider'),
                'details': result.get('details', {})
            }
        else:
            return {
                'success': False,
                'error': result.get('message', 'ゲスト決済リンク作成に失敗しました'),
                'payment_link': None,
                'provider': result.get('provider')
            }
    
    except Exception as e:
        logger.error(f"ゲスト決済リンク作成エラー: {str(e)}")
        return {
            'success': False,
            'error': f'ゲスト決済リンク作成エラー: {str(e)}',
            'payment_link': None
        }


def create_payment_link(customer_name: str, amount: float, user_id: str = None) -> Dict[str, Any]:
    """
    通常の決済リンクを作成する
    
    Args:
        customer_name (str): 顧客名
        amount (float): 金額
        user_id (str, optional): ユーザーID
        
    Returns:
        Dict[str, Any]: 決済リンク情報
    """
    logger.info(f"通常決済リンク作成: 顧客={customer_name}, 金額={amount}")
    
    try:
        # payment_utils.pyのget_default_payment_providerを使用してデフォルトプロバイダーを取得
        from payment_utils import get_default_payment_provider, create_payment_link as utils_create_payment_link
        provider = get_default_payment_provider()
        
        logger.info(f"デフォルト決済プロバイダー: {provider}")
        
        # 適切なプロバイダーを使用して決済リンクを作成
        result = utils_create_payment_link(
            provider=provider,
            amount=amount,
            customer_name=customer_name,
            description=f"決済: {customer_name}"
        )
        
        # 結果を統一フォーマットに変換
        if result.get('success'):
            return {
                'success': True,
                'payment_link': result.get('payment_link'),
                'provider': result.get('provider'),
                'details': result.get('details', {})
            }
        else:
            return {
                'success': False,
                'error': result.get('message', '決済リンク作成に失敗しました'),
                'payment_link': None,
                'provider': result.get('provider')
            }
    
    except Exception as e:
        logger.error(f"決済リンク作成エラー: {str(e)}")
        return {
            'success': False,
            'error': f'決済リンク作成エラー: {str(e)}',
            'payment_link': None
        }


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
