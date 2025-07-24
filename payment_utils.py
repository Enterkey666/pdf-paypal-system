#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
決済プロバイダー統合ユーティリティ
PayPal および Stripe の統一インターフェースを提供
"""

import os
import logging
from typing import Dict, Any, Optional
from flask import url_for, request

# ロガーの設定
logger = logging.getLogger(__name__)

def get_available_payment_providers() -> Dict[str, bool]:
    """
    利用可能な決済プロバイダーを取得
    
    Returns:
        Dict[str, bool]: 各プロバイダーの利用可能状況
    """
    from config_manager import get_config
    
    try:
        config = get_config()
        logger.info(f"設定ファイルから読み込んだ有効な決済プロバイダー: {config.get('enabled_payment_providers', [])}")
        
        # 有効な決済プロバイダーをチェック
        enabled_providers = config.get('enabled_payment_providers', [])
        logger.info(f"有効化された決済プロバイダー: {enabled_providers}")
        
        # PayPalの利用可能性をチェック - 新しいget_paypal_credentials関数を使用
        paypal_enabled = 'paypal' in enabled_providers
        try:
            from paypal_helpers import get_paypal_credentials
            client_id, client_secret, mode = get_paypal_credentials()
            paypal_configured = bool(client_id and client_secret)
        except ImportError:
            # 後方互換性のため
            paypal_configured = bool(
                config.get('client_id') and 
                config.get('client_secret')
            )
        
        paypal_available = paypal_enabled and paypal_configured
        logger.info(f"PayPalの状態 - 有効化: {paypal_enabled}, 設定完了: {paypal_configured}, 利用可能: {paypal_available}")
        
        # Stripeの利用可能性をチェック - 新しいget_stripe_credentials関数を使用
        stripe_enabled = 'stripe' in enabled_providers
        try:
            from stripe_helpers import get_stripe_credentials
            publishable_key, secret_key, mode = get_stripe_credentials()
            stripe_configured = bool(publishable_key and secret_key)
        except ImportError:
            # 後方互換性のため
            stripe_mode = config.get('stripe_mode', 'test')
            if stripe_mode == 'test':
                stripe_configured = bool(
                    config.get('stripe_publishable_key_test') and 
                    config.get('stripe_secret_key_test')
                )
            else:  # live mode
                stripe_configured = bool(
                    config.get('stripe_publishable_key_live') and 
                    config.get('stripe_secret_key_live')
                )
        
        stripe_available = stripe_enabled and stripe_configured
        logger.info(f"Stripeの状態 - 有効化: {stripe_enabled}, 設定完了: {stripe_configured}, 利用可能: {stripe_available}")
        
        result = {
            'paypal': paypal_available,
            'stripe': stripe_available
        }
        logger.info(f"利用可能な決済プロバイダー結果: {result}")
        return result
        
    except Exception as e:
        logger.error(f"決済プロバイダー確認エラー: {str(e)}")
        return {
            'paypal': False,
            'stripe': False
        }

def create_payment_link(
    provider: str,
    amount: float,
    customer_name: str,
    description: str = "",
    currency: str = "JPY"
) -> Dict[str, Any]:
    """
    指定された決済プロバイダーで決済リンクを作成
    
    Args:
        provider (str): 決済プロバイダー ('paypal' または 'stripe')
        amount (float): 金額
        customer_name (str): 顧客名
        description (str): 決済の説明
        currency (str): 通貨コード
        
    Returns:
        Dict[str, Any]: 決済リンク作成結果
    """
    try:
        # 利用可能なプロバイダーをチェック
        available_providers = get_available_payment_providers()
        logger.info(f"決済リンク作成: 利用可能なプロバイダー={available_providers}, 指定プロバイダー={provider}")
        
        # 指定されたプロバイダーが存在するかチェック
        if provider not in available_providers:
            logger.warning(f"不明な決済プロバイダーが指定されました: {provider}")
            return {
                'success': False,
                'message': f'不明な決済プロバイダー: {provider}',
                'payment_link': None,
                'provider': provider
            }
        
        # プロバイダーの設定が完了しているかチェック
        if not available_providers[provider]:
            # 利用可能な代替プロバイダーを探す
            original_provider = provider
            for alt_provider, available in available_providers.items():
                if available:
                    logger.warning(f"プロバイダー {provider} が利用できないため、{alt_provider} に切り替えます")
                    provider = alt_provider
                    break
                    
            # 利用可能なプロバイダーが見つからなかった場合
            if provider == original_provider:
                logger.error(f"{provider.upper()}の設定が不完全です")
                return {
                    'success': False,
                    'message': f'{provider.upper()}の設定が不完全です',
                    'payment_link': None,
                    'provider': provider
                }
            
            logger.info(f"代替プロバイダーに切り替えました: {provider}")
        
        
        # 成功・キャンセルURL を生成
        success_url = None
        cancel_url = None
        
        try:
            if request:
                success_url = url_for('payment_success', provider=provider, _external=True)
                cancel_url = url_for('payment_cancel', provider=provider, _external=True)
        except Exception:
            logger.warning("URLの生成に失敗しました（Flaskコンテキスト外）")
        
        # プロバイダー別の処理
        if provider.lower() == 'paypal':
            return create_paypal_payment_link_unified(
                amount=amount,
                customer_name=customer_name,
                description=description,
                currency=currency,
                success_url=success_url,
                cancel_url=cancel_url
            )
        
        elif provider.lower() == 'stripe':
            return create_stripe_payment_link_unified(
                amount=amount,
                customer_name=customer_name,
                description=description,
                currency=currency.lower(),
                success_url=success_url,
                cancel_url=cancel_url
            )
        
        else:
            return {
                'success': False,
                'message': f'サポートされていない決済プロバイダー: {provider}',
                'payment_link': None,
                'provider': provider
            }
            
    except Exception as e:
        logger.error(f"決済リンク作成エラー: {str(e)}")
        return {
            'success': False,
            'message': f'決済リンク作成エラー: {str(e)}',
            'payment_link': None,
            'provider': provider
        }

def create_paypal_payment_link_unified(
    amount: float,
    customer_name: str,
    description: str = "",
    currency: str = "JPY",
    success_url: str = None,
    cancel_url: str = None
) -> Dict[str, Any]:
    """
    PayPal決済リンクを作成（統一インターフェース）
    
    Args:
        amount (float): 金額
        customer_name (str): 顧客名
        description (str): 決済の説明
        currency (str): 通貨コード
        success_url (str): 成功時のリダイレクトURL
        cancel_url (str): キャンセル時のリダイレクトURL
        
    Returns:
        Dict[str, Any]: 決済リンク作成結果
    """
    try:
        # PayPalの設定を取得
        from paypal_helpers import get_paypal_credentials
        client_id, client_secret, mode = get_paypal_credentials()
        
        if not client_id or not client_secret:
            logger.error("PayPalの認証情報が設定されていません")
            return {
                'success': False,
                'message': 'PayPalの認証情報が設定されていません',
                'payment_link': None,
                'provider': 'paypal'
            }
        
        # PayPalのAPIを使用して決済リンクを作成
        import paypalrestsdk
        from paypalrestsdk import Payment
        
        # PayPalSDKを設定
        paypalrestsdk.configure({
            "mode": mode,  # sandbox または live
            "client_id": client_id,
            "client_secret": client_secret
        })
        
        # 説明が空の場合は顧客名を使用
        if not description:
            description = f"Payment for {customer_name}"
        
        # PayPal決済を作成
        payment = Payment({
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "redirect_urls": {
                "return_url": success_url or "http://example.com/success",
                "cancel_url": cancel_url or "http://example.com/cancel"
            },
            "transactions": [{
                "amount": {
                    "total": str(amount),
                    "currency": currency
                },
                "description": description[:127]  # PayPalの制限に合わせて切り詰め
            }]
        })
        
        # 決済を作成
        if payment.create():
            # 承認URLを取得
            for link in payment.links:
                if link.rel == "approval_url":
                    approval_url = link.href
                    payment_id = payment.id
                    
                    logger.info(f"PayPal決済リンクを作成しました: {approval_url}")
                    
                    return {
                        'success': True,
                        'message': 'PayPal決済リンクが正常に作成されました',
                        'payment_link': approval_url,
                        'provider': 'paypal',
                        'details': {
                            'payment_id': payment_id,
                            'amount': amount,
                            'currency': currency,
                            'customer_name': customer_name
                        }
                    }
            
            # 承認URLが見つからない場合
            logger.error("PayPal承認URLが見つかりません")
            return {
                'success': False,
                'message': 'PayPal承認URLが見つかりません',
                'payment_link': None,
                'provider': 'paypal',
                'details': {'payment_id': payment.id}
            }
        else:
            # 決済作成失敗
            logger.error(f"PayPal決済作成失敗: {payment.error}")
            return {
                'success': False,
                'message': f'PayPal決済作成失敗: {payment.error}',
                'payment_link': None,
                'provider': 'paypal'
            }
            
    except Exception as e:
        logger.error(f"PayPal決済リンク作成エラー: {str(e)}")
        return {
            'success': False,
            'message': f'PayPal決済リンク作成エラー: {str(e)}',
            'payment_link': None,
            'provider': 'paypal'
        }


def create_stripe_payment_link_unified(
    amount: float,
    customer_name: str,
    description: str = "",
    currency: str = "jpy",
    success_url: str = None,
    cancel_url: str = None
) -> Dict[str, Any]:
    """
    Stripe決済リンクを作成（統一インターフェース）
    
    Args:
        amount (float): 金額
        customer_name (str): 顧客名
        description (str): 決済の説明
        currency (str): 通貨コード
        success_url (str): 成功時のリダイレクトURL
        cancel_url (str): キャンセル時のリダイレクトURL
        
    Returns:
        Dict[str, Any]: 決済リンク作成結果
    """
    try:
        # Stripeの設定を取得
        from stripe_helpers import get_stripe_credentials
        publishable_key, secret_key, mode = get_stripe_credentials()
        
        if not publishable_key or not secret_key:
            logger.error("Stripeの認証情報が設定されていません")
            return {
                'success': False, 
                'message': 'Stripeの認証情報が設定されていません', 
                'payment_link': None, 
                'provider': 'stripe'
            }
            
        # Stripe APIを使用して決済リンクを作成
        from stripe_utils import create_stripe_payment_link
        result = create_stripe_payment_link(
            amount=amount,
            customer_name=customer_name,
            description=description,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url
        )
        
        # プロバイダー情報を追加
        result['provider'] = 'stripe'
        return result
        
    except ImportError as e:
        logger.error(f"Stripe関連モジュールのインポートエラー: {str(e)}")
        return {
            'success': False,
            'message': f'Stripeモジュールのインポートエラー: {str(e)}',
            'payment_link': None,
            'provider': 'stripe'
        }
    except Exception as e:
        logger.error(f"Stripe決済リンク作成エラー: {str(e)}")
        return {
            'success': False,
            'message': f'Stripe決済リンク作成エラー: {str(e)}',
            'payment_link': None,
            'provider': 'stripe'
        }

def test_payment_provider_connection(provider: str) -> Dict[str, Any]:
    """
    指定された決済プロバイダーの接続をテスト
    
    Args:
        provider (str): 決済プロバイダー ('paypal' または 'stripe')
        
    Returns:
        Dict[str, Any]: 接続テスト結果
    """
    try:
        if provider.lower() == 'paypal':
            from paypal_helpers import safe_test_paypal_connection
            return safe_test_paypal_connection()
        
        elif provider.lower() == 'stripe':
            from stripe_utils import test_stripe_connection
            return test_stripe_connection()
        
        else:
            return {
                'success': False,
                'message': f'サポートされていない決済プロバイダー: {provider}',
                'details': {}
            }
            
    except Exception as e:
        logger.error(f"決済プロバイダー接続テストエラー: {str(e)}")
        return {
            'success': False,
            'message': f'接続テストエラー: {str(e)}',
            'details': {'error': str(e)}
        }

def get_default_payment_provider() -> str:
    """
    デフォルトの決済プロバイダーを取得
    
    Returns:
        str: デフォルトの決済プロバイダー名
    """
    try:
        from config_manager import get_config
        config = get_config()
        
        default_provider = config.get('default_payment_provider', 'paypal')
        logger.info(f"設定ファイルから読み込んだデフォルト決済プロバイダー: {default_provider}")
        
        available_providers = get_available_payment_providers()
        logger.info(f"利用可能な決済プロバイダー: {available_providers}")
        
        # デフォルトプロバイダーが利用可能かチェック
        if available_providers.get(default_provider, False):
            logger.info(f"デフォルト決済プロバイダー {default_provider} を使用します")
            return default_provider
        
        # 利用可能な他のプロバイダーを選択
        for provider, available in available_providers.items():
            if available:
                logger.warning(f"デフォルトプロバイダー({default_provider})が利用不可のため、{provider}を使用します")
                return provider
        
        # どのプロバイダーも利用不可の場合
        logger.warning("利用可能な決済プロバイダーがありません")
        return default_provider
        
    except Exception as e:
        logger.error(f"デフォルト決済プロバイダー取得エラー: {str(e)}")
        return 'paypal'

def format_payment_result_for_display(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    決済結果を表示用にフォーマット
    
    Args:
        result (Dict[str, Any]): 決済プロバイダーからの結果
        
    Returns:
        Dict[str, Any]: 表示用にフォーマットされた結果
    """
    try:
        provider = result.get('provider', 'unknown')
        success = result.get('success', False)
        
        formatted = {
            'success': success,
            'provider': provider,
            'provider_display': provider.upper(),
            'message': result.get('message', ''),
            'payment_link': result.get('payment_link'),
            'timestamp': result.get('timestamp'),
            'details': result.get('details', {})
        }
        
        # プロバイダー固有の表示情報を追加
        if provider == 'paypal':
            formatted['provider_display'] = 'PayPal'
            formatted['icon'] = 'fab fa-paypal'
            formatted['color'] = 'primary'
        elif provider == 'stripe':
            formatted['provider_display'] = 'Stripe'
            formatted['icon'] = 'fab fa-stripe'
            formatted['color'] = 'info'
        
        return formatted
        
    except Exception as e:
        logger.error(f"決済結果フォーマットエラー: {str(e)}")
        return {
            'success': False,
            'provider': 'unknown',
            'provider_display': 'Unknown',
            'message': 'フォーマットエラーが発生しました',
            'payment_link': None,
            'icon': 'fas fa-exclamation-triangle',
            'color': 'danger'
        }

def create_payment_link_from_ocr(
    provider: str,
    ocr_data: Dict[str, Any],
    filename: str = "",
    override_amount: float = None,
    override_customer: str = None
) -> Dict[str, Any]:
    """
    OCR抽出データから決済リンクを作成（プロバイダー統一インターフェース）
    
    Args:
        provider (str): 決済プロバイダー ('paypal' または 'stripe')
        ocr_data (Dict[str, Any]): OCRで抽出されたデータ
        filename (str): 元のファイル名
        override_amount (float, optional): 金額の上書き
        override_customer (str, optional): 顧客名の上書き
        
    Returns:
        Dict[str, Any]: 決済リンク作成結果
    """
    try:
        logger.info(f"OCR連携決済リンク作成: {provider}, ファイル={filename}")
        
        # 利用可能なプロバイダーをチェック
        available_providers = get_available_payment_providers()
        logger.info(f"OCR連携決済リンク作成: 利用可能なプロバイダー={available_providers}")
        
        # 指定されたプロバイダーが存在するかチェック
        if provider not in available_providers:
            logger.warning(f"不明な決済プロバイダーが指定されました: {provider}")
            return {
                'success': False,
                'message': f'不明な決済プロバイダー: {provider}',
                'payment_link': None,
                'provider': provider
            }
        
        # プロバイダーの設定が完了しているかチェック
        if not available_providers[provider]:
            # 利用可能な代替プロバイダーを探す
            original_provider = provider
            for alt_provider, available in available_providers.items():
                if available:
                    logger.warning(f"プロバイダー {provider} が利用できないため、{alt_provider} に切り替えます")
                    provider = alt_provider
                    break
                    
            # 利用可能なプロバイダーが見つからなかった場合
            if provider == original_provider:
                logger.error(f"{provider.upper()}の設定が不完全です")
                return {
                    'success': False,
                    'message': f'{provider.upper()}の設定が不完全です',
                    'payment_link': None,
                    'provider': provider
                }
            
            logger.info(f"代替プロバイダーに切り替えました: {provider}")
        
        # OCRデータから顧客名と金額を抽出（プロバイダー共通処理）
        customer_name = override_customer or ocr_data.get('customer_name') or ocr_data.get('顧客名') or '不明な顧客'
        amount = override_amount or ocr_data.get('amount') or ocr_data.get('金額') or 0
        
        # 金額が文字列の場合は数値に変換
        if isinstance(amount, str):
            amount_str = amount.replace(',', '').replace('¥', '').replace('円', '').strip()
            try:
                amount = float(amount_str)
            except ValueError:
                amount = 0
        
        if amount <= 0:
            return {
                'success': False,
                'message': 'OCRから有効な金額を抽出できませんでした',
                'payment_link': None,
                'provider': provider
            }
        
        logger.info(f"OCR連携決済リンク作成: プロバイダー={provider}, 顧客名={customer_name}, 金額={amount}")
        
        # 統一インターフェースを使用して決済リンクを作成
        result = create_payment_link(
            provider=provider,
            amount=amount,
            customer_name=customer_name,
            description=filename
        )
        
        # OCRデータを追加
        if 'details' not in result:
            result['details'] = {}
            
        result['details']['ocr_data'] = {
            'extracted_customer': ocr_data.get('customer_name') or ocr_data.get('顧客名'),
            'extracted_amount': ocr_data.get('amount') or ocr_data.get('金額'),
            'filename': filename
        }
        
        return result
            
    except Exception as e:
        logger.error(f"OCR連携決済リンク作成エラー: {str(e)}")
        return {
            'success': False,
            'message': f'OCR連携決済リンク作成エラー: {str(e)}',
            'payment_link': None,
            'provider': provider
        }

def extract_and_validate_payment_data(ocr_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    OCRデータから決済に必要な情報を抽出・検証
    
    Args:
        ocr_data (Dict[str, Any]): OCRで抽出されたデータ
        
    Returns:
        Dict[str, Any]: 抽出・検証結果
    """
    try:
        result = {
            'valid': False,
            'customer_name': None,
            'amount': None,
            'formatted_amount': None,
            'currency': 'JPY',
            'date': None,
            'errors': [],
            'warnings': []
        }
        
        # 顧客名の抽出
        customer_name = (
            ocr_data.get('customer_name') or 
            ocr_data.get('顧客名') or 
            ocr_data.get('customer') or
            ''
        ).strip()
        
        if customer_name:
            result['customer_name'] = customer_name
        else:
            result['errors'].append('顧客名が抽出できませんでした')
        
        # 金額の抽出・検証
        amount_raw = (
            ocr_data.get('amount') or 
            ocr_data.get('金額') or 
            ocr_data.get('total') or 
            0
        )
        
        if isinstance(amount_raw, str):
            # 金額文字列の正規化
            amount_str = amount_raw.replace(',', '').replace('¥', '').replace('円', '').strip()
            try:
                amount = float(amount_str)
                if amount > 0:
                    result['amount'] = amount
                    result['formatted_amount'] = f"¥{amount:,.0f}"
                else:
                    result['errors'].append('金額が0以下です')
            except ValueError:
                result['errors'].append(f'金額の形式が正しくありません: {amount_raw}')
        elif isinstance(amount_raw, (int, float)):
            if amount_raw > 0:
                result['amount'] = float(amount_raw)
                result['formatted_amount'] = f"¥{amount_raw:,.0f}"
            else:
                result['errors'].append('金額が0以下です')
        else:
            result['errors'].append('金額が抽出できませんでした')
        
        # 日付の抽出（オプション）
        date_info = (
            ocr_data.get('date') or 
            ocr_data.get('日付') or 
            ocr_data.get('発行日') or
            None
        )
        if date_info:
            result['date'] = str(date_info).strip()
        
        # 金額の範囲チェック
        if result['amount']:
            if result['amount'] > 1000000:  # 100万円以上
                result['warnings'].append('金額が高額です（100万円以上）')
            elif result['amount'] < 100:  # 100円未満
                result['warnings'].append('金額が少額です（100円未満）')
        
        # 顧客名の長さチェック
        if result['customer_name'] and len(result['customer_name']) > 50:
            result['warnings'].append('顧客名が長すぎます（50文字以上）')
        
        # 全体の検証
        result['valid'] = len(result['errors']) == 0 and result['customer_name'] and result['amount']
        
        return result
        
    except Exception as e:
        logger.error(f"決済データ抽出・検証エラー: {str(e)}")
        return {
            'valid': False,
            'customer_name': None,
            'amount': None,
            'formatted_amount': None,
            'currency': 'JPY',
            'date': None,
            'errors': [f'データ抽出中にエラーが発生しました: {str(e)}'],
            'warnings': []
        }