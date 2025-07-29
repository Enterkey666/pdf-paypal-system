#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe Payment Links API統合モジュール
Stripe Payment Links APIを使用した決済リンク生成機能
"""

import os
import json
import logging
import stripe
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

# ロガーの設定
logger = logging.getLogger(__name__)

# Stripeキー設定
def configure_stripe(api_key: str = None) -> bool:
    """
    Stripe APIキーを設定
    
    Args:
        api_key (str): Stripe Secret Key
        
    Returns:
        bool: 設定成功/失敗
    """
    try:
        if not api_key:
            # 新しいget_stripe_credentials関数を使用
            try:
                from stripe_helpers import get_stripe_credentials
                _, api_key, _ = get_stripe_credentials()
            except ImportError:
                # 後方互換性のため
                from config_manager import get_config
                config = get_config()
                
                # モードに応じたキーを取得
                stripe_mode = config.get('stripe_mode', 'test')
                if stripe_mode == 'test':
                    api_key = config.get('stripe_secret_key_test', '')
                else:
                    api_key = config.get('stripe_secret_key_live', '')
                    
                # 後方互換性のため
                if not api_key:
                    api_key = config.get('stripe_secret_key', '')
        
        if not api_key:
            logger.error("Stripe APIキーが設定されていません")
            return False
            
        stripe.api_key = api_key
        logger.info("Stripe APIキーが正常に設定されました")
        return True
    except Exception as e:
        logger.error(f"Stripe APIキー設定エラー: {str(e)}")
        return False

def test_stripe_connection(api_key: str = None) -> Dict[str, Any]:
    """
    Stripe API接続テスト
    
    Args:
        api_key (str, optional): Stripe Secret Key
        
    Returns:
        Dict[str, Any]: テスト結果
    """
    try:
        # 指定されたAPIキーがない場合は、get_stripe_credentials関数を使用
        if not api_key:
            try:
                from stripe_helpers import get_stripe_credentials
                publishable_key, api_key, mode = get_stripe_credentials()
                if not api_key:
                    return {
                        'success': False,
                        'message': 'Stripeの認証情報が設定されていません',
                        'details': {}
                    }
                stripe.api_key = api_key
            except ImportError:
                # 後方互換性のため
                if not configure_stripe(api_key):
                    return {
                        'success': False,
                        'message': 'Stripe APIキーの設定に失敗しました',
                        'details': {}
                    }
        else:
            # 指定されたAPIキーを使用
            stripe.api_key = api_key
        
        # アカウント情報を取得してテスト
        account = stripe.Account.retrieve()
        
        # テスト環境の場合は決済機能を有効と判定
        is_test_mode = stripe.api_key.startswith('sk_test_')
        effective_charges_enabled = account.get('charges_enabled') or is_test_mode
        
        return {
            'success': True,
            'message': f'Stripe接続成功: {account.get("display_name", "Unknown")}',
            'details': {
                'account_id': account.get('id'),
                'country': account.get('country'),
                'default_currency': account.get('default_currency'),
                'charges_enabled': effective_charges_enabled,
                'payouts_enabled': account.get('payouts_enabled'),
                'is_test_mode': is_test_mode,
                'raw_charges_enabled': account.get('charges_enabled')
            }
        }
    except stripe.error.AuthenticationError as e:
        logger.error(f"Stripe認証エラー: {str(e)}")
        return {
            'success': False,
            'message': f'Stripe認証エラー: APIキーが無効です',
            'details': {'error': str(e)}
        }
    except Exception as e:
        logger.error(f"Stripe接続テストエラー: {str(e)}")
        return {
            'success': False,
            'message': f'Stripe接続エラー: {str(e)}',
            'details': {'error': str(e)}
        }

def create_stripe_payment_link(
    amount: float,
    customer_name: str,
    description: str = "",
    currency: str = "jpy",
    success_url: str = None,
    cancel_url: str = None
) -> Dict[str, Any]:
    """
    Stripe Payment Linkを作成
    
    Args:
        amount (float): 金額
        customer_name (str): 顧客名
        description (str): 決済の説明
        currency (str): 通貨コード（デフォルト: jpy）
        success_url (str): 成功時のリダイレクトURL
        cancel_url (str): キャンセル時のリダイレクトURL
        
    Returns:
        Dict[str, Any]: 決済リンク作成結果
    """
    try:
        # stripe_helpersモジュールからget_stripe_credentials関数を使用
        try:
            from stripe_helpers import get_stripe_credentials
            publishable_key, secret_key, mode = get_stripe_credentials()
            if not secret_key:
                return {
                    'success': False,
                    'message': 'Stripeの認証情報が設定されていません',
                    'payment_link': None,
                    'details': {}
                }
            # 取得した認証情報でStripe APIを設定
            stripe.api_key = secret_key
        except ImportError:
            # 後方互換性のため
            if not configure_stripe():
                return {
                    'success': False,
                    'message': 'Stripe設定エラー',
                    'payment_link': None,
                    'details': {}
                }
        
        # 金額を最小単位に変換（JPYは整数、USDは×100）
        if currency.lower() == 'jpy':
            unit_amount = int(amount)
        else:
            unit_amount = int(amount * 100)
        
        # 商品を作成
        product_name = f"請求書決済 - {customer_name}"
        if description:
            product_name += f" ({description})"
            
        product = stripe.Product.create(
            name=product_name,
            description=f"顧客: {customer_name}\n説明: {description}" if description else f"顧客: {customer_name}"
        )
        
        # 価格を作成
        price = stripe.Price.create(
            product=product.id,
            unit_amount=unit_amount,
            currency=currency.lower(),
            billing_scheme='per_unit'
        )
        
        # Payment Linkを作成
        payment_link_params = {
            'line_items': [{
                'price': price.id,
                'quantity': 1,
            }],
            'metadata': {
                'customer_name': customer_name,
                'description': description,
                'created_at': datetime.now().isoformat()
            }
        }
        
        # URLが指定されている場合は追加
        if success_url:
            # 成功時のリダイレクトURL設定（session_idパラメータを追加）
            # StripeのPayment Linkは{CHECKOUT_SESSION_ID}プレースホルダーを使用
            separator = '&' if '?' in success_url else '?'
            success_url_with_params = f"{success_url}{separator}session_id={{CHECKOUT_SESSION_ID}}"
            
            payment_link_params['after_completion'] = {
                'type': 'redirect',
                'redirect': {'url': success_url_with_params}
            }
            logger.info(f"Stripe Payment Link成功時リダイレクト設定: {success_url_with_params}")
        
        # キャンセル時のリダイレクトURL設定（カスタムテキストで代替）
        if cancel_url:
            payment_link_params['custom_text'] = {
                'submit': {
                    'message': 'お支払いをキャンセルしたい場合は、ブラウザを閉じてください。'
                }
            }
            logger.info(f"Stripe Payment Linkキャンセル時の案内を設定: {cancel_url}")
        
        payment_link = stripe.PaymentLink.create(**payment_link_params)
        
        logger.info(f"Stripe Payment Link作成成功: {payment_link.id}")
        
        return {
            'success': True,
            'message': '決済リンクが正常に作成されました',
            'payment_link': payment_link.url,
            'details': {
                'payment_link_id': payment_link.id,
                'product_id': product.id,
                'price_id': price.id,
                'amount': amount,
                'currency': currency,
                'customer_name': customer_name
            }
        }
        
    except stripe.error.InvalidRequestError as e:
        logger.error(f"Stripe無効リクエストエラー: {str(e)}")
        return {
            'success': False,
            'message': f'無効なリクエスト: {str(e)}',
            'payment_link': None,
            'details': {'error': str(e)}
        }
    except stripe.error.AuthenticationError as e:
        logger.error(f"Stripe認証エラー: {str(e)}")
        return {
            'success': False,
            'message': 'Stripe認証エラー: APIキーを確認してください',
            'payment_link': None,
            'details': {'error': str(e)}
        }
    except Exception as e:
        logger.error(f"Stripe Payment Link作成エラー: {str(e)}")
        return {
            'success': False,
            'message': f'決済リンク作成エラー: {str(e)}',
            'payment_link': None,
            'details': {'error': str(e)}
        }

def retrieve_payment_link_status(payment_link_id: str) -> Dict[str, Any]:
    """
    Payment Linkのステータスを取得
    
    Args:
        payment_link_id (str): Payment Link ID
        
    Returns:
        Dict[str, Any]: ステータス情報
    """
    try:
        if not configure_stripe():
            return {
                'success': False,
                'message': 'Stripe設定エラー',
                'status': None
            }
        
        payment_link = stripe.PaymentLink.retrieve(payment_link_id)
        
        return {
            'success': True,
            'message': 'ステータス取得成功',
            'status': {
                'id': payment_link.id,
                'url': payment_link.url,
                'active': payment_link.active,
                'metadata': payment_link.metadata,
                'created': payment_link.created
            }
        }
    except Exception as e:
        logger.error(f"Payment Linkステータス取得エラー: {str(e)}")
        return {
            'success': False,
            'message': f'ステータス取得エラー: {str(e)}',
            'status': None
        }

def create_stripe_payment_link_from_ocr(
    ocr_data: Dict[str, Any],
    filename: str = "",
    override_amount: float = None,
    override_customer: str = None
) -> Dict[str, Any]:
    """
    OCR抽出データからStripe Payment Linkを作成
    
    Args:
        ocr_data (Dict[str, Any]): OCRで抽出されたデータ
        filename (str): 元のファイル名
        override_amount (float, optional): 金額の上書き
        override_customer (str, optional): 顧客名の上書き
        
    Returns:
        Dict[str, Any]: 決済リンク作成結果
    """
    try:
        logger.info(f"OCRデータからStripe決済リンク作成開始: {filename}")
        
        # OCRデータから顧客名と金額を抽出
        customer_name = override_customer or ocr_data.get('customer_name') or ocr_data.get('顧客名') or '不明な顧客'
        amount = override_amount or ocr_data.get('amount') or ocr_data.get('金額') or 0
        
        # 金額が文字列の場合は数値に変換
        if isinstance(amount, str):
            # カンマや円マークを除去して数値化
            amount_str = amount.replace(',', '').replace('¥', '').replace('円', '').strip()
            try:
                amount = float(amount_str)
            except ValueError:
                logger.warning(f"金額の変換に失敗: {amount}")
                amount = 0
        
        if amount <= 0:
            return {
                'success': False,
                'message': '有効な金額が抽出できませんでした',
                'payment_link': None,
                'details': {'ocr_data': ocr_data}
            }
        
        # 説明文を作成
        description = f"請求書: {filename}" if filename else "OCR自動抽出による請求"
        if ocr_data.get('date') or ocr_data.get('日付'):
            date_info = ocr_data.get('date') or ocr_data.get('日付')
            description += f" ({date_info})"
        
        # Stripe Payment Linkを作成
        result = create_stripe_payment_link(
            amount=amount,
            customer_name=customer_name,
            description=description,
            currency="jpy"
        )
        
        # OCRデータを詳細情報に追加
        if result.get('success') and result.get('details'):
            result['details']['ocr_data'] = {
                'extracted_customer': ocr_data.get('customer_name') or ocr_data.get('顧客名'),
                'extracted_amount': ocr_data.get('amount') or ocr_data.get('金額'),
                'filename': filename,
                'processing_timestamp': datetime.now().isoformat()
            }
        
        logger.info(f"OCRデータからStripe決済リンク作成完了: {customer_name}, ¥{amount}")
        return result
        
    except Exception as e:
        logger.error(f"OCRデータからStripe決済リンク作成エラー: {str(e)}")
        return {
            'success': False,
            'message': f'OCRデータからの決済リンク作成エラー: {str(e)}',
            'payment_link': None,
            'details': {'error': str(e), 'ocr_data': ocr_data}
        }

def validate_stripe_configuration() -> Dict[str, Any]:
    """
    Stripe設定の妥当性を検証
    
    Returns:
        Dict[str, Any]: 検証結果
    """
    try:
        from config import get_config
        config = get_config()
        
        issues = []
        warnings = []
        
        # 必須設定のチェック
        stripe_mode = config.get('stripe_mode', 'test')
        
        # モードに応じたキーを取得
        if stripe_mode == 'test':
            stripe_secret_key = config.get('stripe_secret_key_test', config.get('stripe_secret_key', ''))
            stripe_publishable_key = config.get('stripe_publishable_key_test', config.get('stripe_publishable_key', ''))
        else:
            stripe_secret_key = config.get('stripe_secret_key_live', config.get('stripe_secret_key', ''))
            stripe_publishable_key = config.get('stripe_publishable_key_live', config.get('stripe_publishable_key', ''))
        
        if not stripe_secret_key:
            issues.append("Stripe Secret Keyが設定されていません")
        elif stripe_mode == 'test' and not stripe_secret_key.startswith('sk_test_'):
            issues.append("テストモードですがSecret Keyがテスト用ではありません")
        elif stripe_mode == 'live' and not stripe_secret_key.startswith('sk_live_'):
            issues.append("本番モードですがSecret Keyが本番用ではありません")
        
        if not stripe_publishable_key:
            warnings.append("Stripe Publishable Keyが設定されていません（フロントエンド機能で必要）")
        elif stripe_mode == 'test' and not stripe_publishable_key.startswith('pk_test_'):
            warnings.append("テストモードですがPublishable Keyがテスト用ではありません")
        elif stripe_mode == 'live' and not stripe_publishable_key.startswith('pk_live_'):
            warnings.append("本番モードですがPublishable Keyが本番用ではありません")
        
        # 接続テスト
        connection_test = None
        if stripe_secret_key and not issues:
            connection_test = test_stripe_connection(stripe_secret_key)
            if not connection_test.get('success'):
                issues.append(f"Stripe接続テスト失敗: {connection_test.get('message')}")
            else:
                # テスト環境の場合は決済機能が使用可能であることを確認
                details = connection_test.get('details', {})
                if details.get('is_test_mode') and not details.get('raw_charges_enabled'):
                    warnings.append("テスト環境では決済機能が利用可能です（本番環境では要アカウント認証）")
        
        # 結果をまとめ
        is_valid = len(issues) == 0
        
        return {
            'valid': is_valid,
            'mode': stripe_mode,
            'issues': issues,
            'warnings': warnings,
            'connection_test': connection_test,
            'configuration': {
                'secret_key_configured': bool(stripe_secret_key),
                'publishable_key_configured': bool(stripe_publishable_key),
                'secret_key_format': 'valid' if stripe_secret_key and (
                    (stripe_mode == 'test' and stripe_secret_key.startswith('sk_test_')) or
                    (stripe_mode == 'live' and stripe_secret_key.startswith('sk_live_'))
                ) else 'invalid',
                'publishable_key_format': 'valid' if stripe_publishable_key and (
                    (stripe_mode == 'test' and stripe_publishable_key.startswith('pk_test_')) or
                    (stripe_mode == 'live' and stripe_publishable_key.startswith('pk_live_'))
                ) else 'invalid'
            }
        }
        
    except Exception as e:
        logger.error(f"Stripe設定検証エラー: {str(e)}")
        return {
            'valid': False,
            'mode': 'unknown',
            'issues': [f'設定検証中にエラーが発生しました: {str(e)}'],
            'warnings': [],
            'connection_test': None,
            'configuration': {}
        }

def retrieve_stripe_checkout_session(session_id: str) -> Dict[str, Any]:
    """
    Stripe Checkout Sessionの詳細情報を取得
    
    Args:
        session_id (str): Checkout Session ID
        
    Returns:
        Dict[str, Any]: セッション詳細情報
    """
    try:
        if not configure_stripe():
            return {
                'success': False,
                'message': 'Stripe設定エラー',
                'session': None
            }
        
        # Checkout Sessionを取得
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Payment Intentも取得（詳細情報のため）
        payment_intent = None
        if session.payment_intent:
            try:
                payment_intent = stripe.PaymentIntent.retrieve(session.payment_intent)
            except Exception as e:
                logger.warning(f"Payment Intent取得エラー: {str(e)}")
        
        return {
            'success': True,
            'message': 'セッション情報取得成功',
            'session': {
                'id': session.id,
                'payment_status': session.payment_status,
                'amount_total': session.amount_total,
                'currency': session.currency,
                'customer_email': session.customer_details.email if session.customer_details else None,
                'customer_name': session.customer_details.name if session.customer_details else None,
                'payment_intent_id': session.payment_intent,
                'payment_intent_status': payment_intent.status if payment_intent else None,
                'created': session.created,
                'metadata': session.metadata
            }
        }
    except stripe.error.InvalidRequestError as e:
        logger.error(f"無効なStripe Session ID: {session_id}, エラー: {str(e)}")
        return {
            'success': False,
            'message': f'無効なセッションID: {session_id}',
            'session': None
        }
    except Exception as e:
        logger.error(f"Stripe Checkout Session取得エラー: {str(e)}")
        return {
            'success': False,
            'message': f'セッション取得エラー: {str(e)}',
            'session': None
        }

def get_stripe_webhook_events(limit: int = 10) -> Dict[str, Any]:
    """
    Stripe Webhook イベントを取得（デバッグ用）
    
    Args:
        limit (int): 取得するイベント数
        
    Returns:
        Dict[str, Any]: イベント一覧
    """
    try:
        if not configure_stripe():
            return {
                'success': False,
                'message': 'Stripe設定エラー',
                'events': []
            }
        
        events = stripe.Event.list(limit=limit)
        
        return {
            'success': True,
            'message': f'{len(events.data)}件のイベントを取得',
            'events': [
                {
                    'id': event.id,
                    'type': event.type,
                    'created': event.created,
                    'data': event.data
                } for event in events.data
            ]
        }
    except Exception as e:
        logger.error(f"Stripe Webhook イベント取得エラー: {str(e)}")
        return {
            'success': False,
            'message': f'イベント取得エラー: {str(e)}',
            'events': []
        }

# ==== Stripe Subscription 機能 ====

def get_stripe_keys() -> Dict[str, str]:
    """
    環境変数からStripeキーを取得
    
    Returns:
        Dict[str, str]: Stripeキー情報
    """
    return {
        'secret_key': os.environ.get('STRIPE_SECRET_KEY', ''),
        'publishable_key': os.environ.get('STRIPE_PUBLISHABLE_KEY', ''),
        'webhook_secret': os.environ.get('STRIPE_WEBHOOK_SECRET', ''),
        'price_monthly': os.environ.get('STRIPE_PRICE_MONTHLY', ''),
        'price_yearly': os.environ.get('STRIPE_PRICE_YEARLY', ''),
        'mode': 'test' if os.environ.get('STRIPE_SECRET_KEY', '').startswith('sk_test_') else 'live'
    }

def get_or_create_stripe_customer(user_id: int, email: str, name: str = None) -> Optional[str]:
    """
    Stripe顧客を取得または作成
    
    Args:
        user_id (int): ユーザーID
        email (str): メールアドレス
        name (str): 顧客名
        
    Returns:
        Optional[str]: Stripe Customer ID
    """
    try:
        if not configure_stripe():
            return None
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 既存のStripe Customer IDを確認
        cursor.execute("SELECT stripe_customer_id FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result and result['stripe_customer_id']:
            try:
                # 既存顧客の有効性を確認
                customer = stripe.Customer.retrieve(result['stripe_customer_id'])
                if not customer.deleted:
                    return result['stripe_customer_id']
            except stripe.error.InvalidRequestError:
                logger.warning(f"無効なStripe Customer ID: {result['stripe_customer_id']}")
        
        # 新規顧客作成
        customer_params = {
            'email': email,
            'metadata': {
                'user_id': str(user_id),
                'created_at': datetime.now().isoformat()
            }
        }
        if name:
            customer_params['name'] = name
            
        customer = stripe.Customer.create(**customer_params)
        
        # DBに保存
        cursor.execute(
            "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
            (customer.id, user_id)
        )
        conn.commit()
        
        logger.info(f"新規Stripe顧客作成: {customer.id} (user_id: {user_id})")
        return customer.id
        
    except Exception as e:
        logger.error(f"Stripe顧客作成エラー: {str(e)}")
        return None
    finally:
        if 'conn' in locals():
            conn.close()

def create_subscription_checkout_session(
    user_id: int,
    plan: str,  # 'monthly' or 'yearly'
    success_url: str,
    cancel_url: str
) -> Dict[str, Any]:
    """
    サブスクリプション用Checkout Sessionを作成
    
    Args:
        user_id (int): ユーザーID
        plan (str): プラン ('monthly' or 'yearly')
        success_url (str): 成功時リダイレクトURL
        cancel_url (str): キャンセル時リダイレクトURL
        
    Returns:
        Dict[str, Any]: Checkout Session情報
    """
    try:
        if not configure_stripe():
            return {
                'success': False,
                'message': 'Stripe設定エラー',
                'checkout_url': None
            }
        
        # 価格IDを環境変数から取得
        if plan == 'monthly':
            price_id = os.environ.get('STRIPE_PRICE_MONTHLY')
        elif plan == 'yearly':
            price_id = os.environ.get('STRIPE_PRICE_YEARLY')
        else:
            return {
                'success': False,
                'message': f'無効なプラン: {plan}',
                'checkout_url': None
            }
        
        if not price_id:
            return {
                'success': False,
                'message': f'{plan}プランの価格IDが設定されていません',
                'checkout_url': None
            }
        
        # ユーザー情報を取得
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT email, username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return {
                'success': False,
                'message': 'ユーザーが見つかりません',
                'checkout_url': None
            }
        
        # Stripe顧客を取得または作成
        customer_id = get_or_create_stripe_customer(
            user_id, user['email'], user['username']
        )
        
        if not customer_id:
            return {
                'success': False,
                'message': 'Stripe顧客の作成に失敗しました',
                'checkout_url': None
            }
        
        # Checkout Session作成
        session = stripe.checkout.Session.create(
            mode='subscription',
            customer=customer_id,
            line_items=[{
                'price': price_id,
                'quantity': 1
            }],
            success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=cancel_url,
            metadata={
                'user_id': str(user_id),
                'plan': plan
            },
            subscription_data={
                'trial_period_days': 30,
                'metadata': {
                    'user_id': str(user_id),
                    'plan': plan
                }
            }
        )
        
        logger.info(f"Checkout Session作成成功: {session.id} (user_id: {user_id}, plan: {plan})")
        
        return {
            'success': True,
            'message': 'Checkout Session作成成功',
            'checkout_url': session.url,
            'session_id': session.id
        }
        
    except Exception as e:
        logger.error(f"Checkout Session作成エラー: {str(e)}")
        return {
            'success': False,
            'message': f'Checkout Session作成エラー: {str(e)}',
            'checkout_url': None
        }

def create_customer_portal_session(user_id: int, return_url: str) -> Dict[str, Any]:
    """
    Customer Portal Sessionを作成
    
    Args:
        user_id (int): ユーザーID
        return_url (str): 戻りURL
        
    Returns:
        Dict[str, Any]: Portal Session情報
    """
    try:
        if not configure_stripe():
            return {
                'success': False,
                'message': 'Stripe設定エラー',
                'portal_url': None
            }
        
        # ユーザーのStripe Customer IDを取得
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT stripe_customer_id FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result or not result['stripe_customer_id']:
            return {
                'success': False,
                'message': 'Stripe顧客情報が見つかりません',
                'portal_url': None
            }
        
        # Portal Session作成
        session = stripe.billing_portal.Session.create(
            customer=result['stripe_customer_id'],
            return_url=return_url
        )
        
        logger.info(f"Portal Session作成成功: {session.id} (user_id: {user_id})")
        
        return {
            'success': True,
            'message': 'Portal Session作成成功',
            'portal_url': session.url
        }
        
    except Exception as e:
        logger.error(f"Portal Session作成エラー: {str(e)}")
        return {
            'success': False,
            'message': f'Portal Session作成エラー: {str(e)}',
            'portal_url': None
        }

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Stripe Webhook署名を検証
    
    Args:
        payload (bytes): Webhookペイロード
        signature (str): Stripe署名ヘッダー
        secret (str): Webhook秘密鍵
        
    Returns:
        bool: 署名の有効性
    """
    try:
        stripe.Webhook.construct_event(payload, signature, secret)
        return True
    except ValueError:
        logger.error("Webhook署名検証: 無効なペイロード")
        return False
    except stripe.error.SignatureVerificationError:
        logger.error("Webhook署名検証: 署名が一致しません")
        return False

def is_webhook_event_processed(event_id: str) -> bool:
    """
    Webhookイベントが既に処理済みかチェック（冪等性保証）
    
    Args:
        event_id (str): Stripe Event ID
        
    Returns:
        bool: 処理済みかどうか
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM webhook_events WHERE stripe_event_id = ?",
            (event_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        logger.error(f"Webhook処理状況確認エラー: {str(e)}")
        return False

def mark_webhook_event_processed(event_id: str, event_type: str, result: str = "success") -> bool:
    """
    Webhookイベントを処理済みとしてマーク
    
    Args:
        event_id (str): Stripe Event ID
        event_type (str): イベントタイプ
        result (str): 処理結果
        
    Returns:
        bool: マーク成功
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO webhook_events (stripe_event_id, event_type, processing_result) VALUES (?, ?, ?)",
            (event_id, event_type, result)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Webhookイベントマークエラー: {str(e)}")
        return False

def upsert_subscription(subscription_data: Dict[str, Any]) -> bool:
    """
    サブスクリプション情報をDB に挿入または更新
    
    Args:
        subscription_data (Dict[str, Any]): サブスクリプション情報
        
    Returns:
        bool: 処理成功
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # トランザクション開始
        cursor.execute("BEGIN")
        
        cursor.execute("""
            INSERT OR REPLACE INTO subscriptions (
                user_id, stripe_subscription_id, plan_id, status,
                current_period_start, current_period_end, cancel_at_period_end,
                trial_end, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            subscription_data['user_id'],
            subscription_data['stripe_subscription_id'],
            subscription_data['plan_id'],
            subscription_data['status'],
            subscription_data['current_period_start'],
            subscription_data['current_period_end'],
            subscription_data['cancel_at_period_end'],
            subscription_data.get('trial_end')
        ))
        
        conn.commit()
        logger.info(f"サブスクリプション更新成功: {subscription_data['stripe_subscription_id']}")
        return True
        
    except Exception as e:
        logger.error(f"サブスクリプション更新エラー: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def handle_checkout_session_completed(event_data: Dict[str, Any]) -> bool:
    """
    checkout.session.completed イベントを処理
    
    Args:
        event_data (Dict[str, Any]): イベントデータ
        
    Returns:
        bool: 処理成功
    """
    try:
        session = event_data.get('object', {})
        user_id = session.get('metadata', {}).get('user_id')
        
        if not user_id:
            logger.error("checkout.session.completed: user_idが見つかりません")
            return False
        
        subscription_id = session.get('subscription')
        if not subscription_id:
            logger.error("checkout.session.completed: subscription_idが見つかりません")
            return False
        
        # サブスクリプション詳細を取得
        subscription = stripe.Subscription.retrieve(subscription_id)
        
        subscription_data = {
            'user_id': int(user_id),
            'stripe_subscription_id': subscription.id,
            'plan_id': 'Pro',
            'status': subscription.status,
            'current_period_start': datetime.fromtimestamp(subscription.current_period_start),
            'current_period_end': datetime.fromtimestamp(subscription.current_period_end),
            'cancel_at_period_end': subscription.cancel_at_period_end,
            'trial_end': datetime.fromtimestamp(subscription.trial_end) if subscription.trial_end else None
        }
        
        return upsert_subscription(subscription_data)
        
    except Exception as e:
        logger.error(f"checkout.session.completed処理エラー: {str(e)}")
        return False

def handle_subscription_updated(event_data: Dict[str, Any]) -> bool:
    """
    customer.subscription.updated イベントを処理
    
    Args:
        event_data (Dict[str, Any]): イベントデータ
        
    Returns:
        bool: 処理成功
    """
    try:
        subscription = event_data.get('object', {})
        
        # user_idをサブスクリプションから取得
        user_id = subscription.get('metadata', {}).get('user_id')
        if not user_id:
            # Stripe Customer IDからuser_idを逆引き
            customer_id = subscription.get('customer')
            if customer_id:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE stripe_customer_id = ?", (customer_id,))
                result = cursor.fetchone()
                conn.close()
                if result:
                    user_id = result['id']
        
        if not user_id:
            logger.error("subscription.updated: user_idが特定できません")
            return False
        
        subscription_data = {
            'user_id': int(user_id),
            'stripe_subscription_id': subscription['id'],
            'plan_id': 'Pro',
            'status': subscription['status'],
            'current_period_start': datetime.fromtimestamp(subscription['current_period_start']),
            'current_period_end': datetime.fromtimestamp(subscription['current_period_end']),
            'cancel_at_period_end': subscription['cancel_at_period_end'],
            'trial_end': datetime.fromtimestamp(subscription['trial_end']) if subscription.get('trial_end') else None
        }
        
        return upsert_subscription(subscription_data)
        
    except Exception as e:
        logger.error(f"subscription.updated処理エラー: {str(e)}")
        return False

def handle_subscription_deleted(event_data: Dict[str, Any]) -> bool:
    """
    customer.subscription.deleted イベントを処理
    
    Args:
        event_data (Dict[str, Any]): イベントデータ
        
    Returns:
        bool: 処理成功
    """
    try:
        subscription = event_data.get('object', {})
        subscription_id = subscription.get('id')
        
        if not subscription_id:
            logger.error("subscription.deleted: subscription_idが見つかりません")
            return False
        
        # サブスクリプションのステータスを'canceled'に更新
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE subscriptions SET status = 'canceled', updated_at = CURRENT_TIMESTAMP WHERE stripe_subscription_id = ?",
            (subscription_id,)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"サブスクリプション削除処理完了: {subscription_id}")
        return True
        
    except Exception as e:
        logger.error(f"subscription.deleted処理エラー: {str(e)}")
        return False

def handle_invoice_paid(event_data: Dict[str, Any]) -> bool:
    """
    invoice.paid イベントを処理
    
    Args:
        event_data (Dict[str, Any]): イベントデータ
        
    Returns:
        bool: 処理成功
    """
    try:
        invoice = event_data.get('object', {})
        subscription_id = invoice.get('subscription')
        
        if not subscription_id:
            logger.info("invoice.paid: サブスクリプション以外の請求書")
            return True
        
        # サブスクリプション情報を更新
        subscription = stripe.Subscription.retrieve(subscription_id)
        
        # user_idを特定
        user_id = subscription.metadata.get('user_id')
        if not user_id:
            customer_id = subscription.customer
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE stripe_customer_id = ?", (customer_id,))
            result = cursor.fetchone()
            conn.close()
            if result:
                user_id = result['id']
        
        if not user_id:
            logger.error("invoice.paid: user_idが特定できません")
            return False
        
        subscription_data = {
            'user_id': int(user_id),
            'stripe_subscription_id': subscription.id,
            'plan_id': 'Pro',
            'status': subscription.status,
            'current_period_start': datetime.fromtimestamp(subscription.current_period_start),
            'current_period_end': datetime.fromtimestamp(subscription.current_period_end),
            'cancel_at_period_end': subscription.cancel_at_period_end,
            'trial_end': datetime.fromtimestamp(subscription.trial_end) if subscription.trial_end else None
        }
        
        return upsert_subscription(subscription_data)
        
    except Exception as e:
        logger.error(f"invoice.paid処理エラー: {str(e)}")
        return False

def handle_invoice_payment_failed(event_data: Dict[str, Any]) -> bool:
    """
    invoice.payment_failed イベントを処理
    
    Args:
        event_data (Dict[str, Any]): イベントデータ
        
    Returns:
        bool: 処理成功
    """
    try:
        invoice = event_data.get('object', {})
        subscription_id = invoice.get('subscription')
        
        if not subscription_id:
            logger.info("invoice.payment_failed: サブスクリプション以外の請求書")
            return True
        
        # サブスクリプション情報を更新（past_dueステータスに）
        subscription = stripe.Subscription.retrieve(subscription_id)
        
        # user_idを特定
        user_id = subscription.metadata.get('user_id')
        if not user_id:
            customer_id = subscription.customer
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE stripe_customer_id = ?", (customer_id,))
            result = cursor.fetchone()
            conn.close()
            if result:
                user_id = result['id']
        
        if not user_id:
            logger.error("invoice.payment_failed: user_idが特定できません")
            return False
        
        subscription_data = {
            'user_id': int(user_id),
            'stripe_subscription_id': subscription.id,
            'plan_id': 'Pro',
            'status': subscription.status,  # 'past_due'になる
            'current_period_start': datetime.fromtimestamp(subscription.current_period_start),
            'current_period_end': datetime.fromtimestamp(subscription.current_period_end),
            'cancel_at_period_end': subscription.cancel_at_period_end,
            'trial_end': datetime.fromtimestamp(subscription.trial_end) if subscription.trial_end else None
        }
        
        success = upsert_subscription(subscription_data)
        
        # 督促通知などの追加処理をここに追加可能
        logger.warning(f"決済失敗: user_id={user_id}, subscription_id={subscription_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"invoice.payment_failed処理エラー: {str(e)}")
        return False

def process_stripe_webhook(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stripe Webhookイベントを処理
    
    Args:
        event (Dict[str, Any]): Stripe Event
        
    Returns:
        Dict[str, Any]: 処理結果
    """
    event_id = event.get('id')
    event_type = event.get('type')
    
    if not event_id or not event_type:
        return {
            'success': False,
            'message': '無効なイベント形式'
        }
    
    # 冪等性チェック
    if is_webhook_event_processed(event_id):
        logger.info(f"Webhook既に処理済み: {event_id}")
        return {
            'success': True,
            'message': '既に処理済み'
        }
    
    try:
        success = False
        
        # イベントタイプに応じて処理
        if event_type == 'checkout.session.completed':
            success = handle_checkout_session_completed(event.get('data', {}))
        elif event_type == 'customer.subscription.updated':
            success = handle_subscription_updated(event.get('data', {}))
        elif event_type == 'customer.subscription.deleted':
            success = handle_subscription_deleted(event.get('data', {}))
        elif event_type == 'invoice.paid':
            success = handle_invoice_paid(event.get('data', {}))
        elif event_type == 'invoice.payment_failed':
            success = handle_invoice_payment_failed(event.get('data', {}))
        else:
            logger.info(f"未対応のWebhookイベント: {event_type}")
            success = True  # 未対応イベントは成功扱い
        
        # 処理結果をマーク
        mark_webhook_event_processed(
            event_id, event_type, "success" if success else "failed"
        )
        
        return {
            'success': success,
            'message': f'{event_type} 処理完了' if success else f'{event_type} 処理失敗'
        }
        
    except Exception as e:
        logger.error(f"Webhook処理エラー: {str(e)}")
        mark_webhook_event_processed(event_id, event_type, f"error: {str(e)}")
        return {
            'success': False,
            'message': f'処理エラー: {str(e)}'
        }