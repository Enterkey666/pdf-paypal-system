#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe Webhook処理モジュール
Stripe からの支払い完了通知を処理
"""

import os
import json
import logging
import stripe
from typing import Dict, Any, Optional
from datetime import datetime
from flask import Blueprint, request, jsonify

# ロガーの設定
logger = logging.getLogger(__name__)

# Blueprintの作成
stripe_webhook_bp = Blueprint('stripe_webhook', __name__, url_prefix='/webhook')

# Webhookエンドポイントシークレット（環境変数から取得）
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

def verify_stripe_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Stripe Webhookの署名を検証
    
    Args:
        payload (bytes): リクエストボディ
        signature (str): Stripeから送信されたシグネチャ
        secret (str): Webhookエンドポイントシークレット
        
    Returns:
        bool: 検証結果
    """
    try:
        stripe.Webhook.construct_event(payload, signature, secret)
        return True
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Stripe Webhook署名検証失敗: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Stripe Webhook検証エラー: {str(e)}")
        return False

def process_payment_completed(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    支払い完了イベントを処理
    
    Args:
        event_data (Dict[str, Any]): Stripeイベントデータ
        
    Returns:
        Dict[str, Any]: 処理結果
    """
    try:
        # イベントからオブジェクトを取得
        stripe_object = event_data.get('data', {}).get('object', {})
        object_type = stripe_object.get('object')
        
        logger.info(f"支払い完了イベント処理開始: {object_type}")
        
        if object_type == 'checkout.session':
            # Checkout Session完了の場合
            session_id = stripe_object.get('id')
            customer_email = stripe_object.get('customer_details', {}).get('email')
            amount_total = stripe_object.get('amount_total')
            currency = stripe_object.get('currency')
            payment_status = stripe_object.get('payment_status')
            
            payment_info = {
                'session_id': session_id,
                'customer_email': customer_email,
                'amount': amount_total / 100 if amount_total else 0,  # centからyenに変換
                'currency': currency.upper() if currency else 'JPY',
                'status': payment_status,
                'timestamp': datetime.now().isoformat()
            }
            
        elif object_type == 'payment_intent':
            # Payment Intent完了の場合
            payment_intent_id = stripe_object.get('id')
            amount = stripe_object.get('amount')
            currency = stripe_object.get('currency')
            status = stripe_object.get('status')
            
            payment_info = {
                'payment_intent_id': payment_intent_id,
                'amount': amount / 100 if amount else 0,  # centからyenに変換
                'currency': currency.upper() if currency else 'JPY',
                'status': status,
                'timestamp': datetime.now().isoformat()
            }
            
        else:
            logger.warning(f"未対応のオブジェクトタイプ: {object_type}")
            return {
                'success': False,
                'message': f'未対応のオブジェクトタイプ: {object_type}'
            }
        
        # データベースに支払い情報を保存
        save_result = save_payment_completion(payment_info)
        
        # 処理完了通知（必要に応じて外部システムに通知）
        notification_result = send_payment_notification(payment_info)
        
        logger.info(f"支払い完了イベント処理完了: {payment_info}")
        
        return {
            'success': True,
            'message': '支払い完了イベントが正常に処理されました',
            'payment_info': payment_info,
            'save_result': save_result,
            'notification_result': notification_result
        }
        
    except Exception as e:
        logger.error(f"支払い完了イベント処理エラー: {str(e)}")
        return {
            'success': False,
            'message': f'支払い完了イベント処理エラー: {str(e)}'
        }

def save_payment_completion(payment_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    支払い完了情報をデータベースに保存
    
    Args:
        payment_info (Dict[str, Any]): 支払い情報
        
    Returns:
        Dict[str, Any]: 保存結果
    """
    try:
        # データベース接続（既存のdatabase.pyを使用）
        import database
        
        conn = database.get_db_connection()
        cursor = conn.cursor()
        
        # stripe_payments テーブルに保存
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stripe_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                payment_intent_id TEXT,
                customer_email TEXT,
                amount REAL,
                currency TEXT,
                status TEXT,
                payment_timestamp TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            INSERT INTO stripe_payments 
            (session_id, payment_intent_id, customer_email, amount, currency, status, payment_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            payment_info.get('session_id'),
            payment_info.get('payment_intent_id'),
            payment_info.get('customer_email'),
            payment_info.get('amount'),
            payment_info.get('currency'),
            payment_info.get('status'),
            payment_info.get('timestamp')
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Stripe支払い情報をデータベースに保存しました: {payment_info}")
        
        return {
            'success': True,
            'message': 'データベースに正常に保存されました'
        }
        
    except Exception as e:
        logger.error(f"支払い情報保存エラー: {str(e)}")
        return {
            'success': False,
            'message': f'データベース保存エラー: {str(e)}'
        }

def send_payment_notification(payment_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    支払い完了通知を送信（必要に応じて実装）
    
    Args:
        payment_info (Dict[str, Any]): 支払い情報
        
    Returns:
        Dict[str, Any]: 通知結果
    """
    try:
        # メール通知やSlack通知などを実装する場合はここに追加
        logger.info(f"支払い完了通知: {payment_info}")
        
        # 現在は通知機能は実装せず、ログ出力のみ
        return {
            'success': True,
            'message': '通知処理完了（現在はログ出力のみ）'
        }
        
    except Exception as e:
        logger.error(f"支払い完了通知エラー: {str(e)}")
        return {
            'success': False,
            'message': f'通知送信エラー: {str(e)}'
        }

@stripe_webhook_bp.route('/stripe', methods=['POST'])
def handle_stripe_webhook():
    """
    Stripe Webhookエンドポイント
    """
    try:
        # リクエストボディとシグネチャを取得
        payload = request.get_data()
        signature = request.headers.get('Stripe-Signature', '')
        
        logger.info(f"Stripe Webhook受信: signature={'あり' if signature else 'なし'}")
        
        # 署名検証（本番環境では必須）
        if STRIPE_WEBHOOK_SECRET:
            if not verify_stripe_webhook_signature(payload, signature, STRIPE_WEBHOOK_SECRET):
                logger.error("Stripe Webhook署名検証失敗")
                return jsonify({'error': 'Invalid signature'}), 400
        else:
            logger.warning("Stripe Webhook署名検証をスキップしています（STRIPE_WEBHOOK_SECRETが未設定）")
        
        # イベントデータを解析
        try:
            event = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Stripe Webhook JSONパース失敗: {str(e)}")
            return jsonify({'error': 'Invalid JSON'}), 400
        
        event_type = event.get('type')
        event_id = event.get('id')
        
        logger.info(f"Stripe Webhook イベント: {event_type} (ID: {event_id})")
        
        # イベントタイプに応じて処理を分岐
        if event_type in ['checkout.session.completed', 'payment_intent.succeeded']:
            # 支払い完了イベント
            result = process_payment_completed(event)
            
            if result.get('success'):
                logger.info(f"Stripe Webhook処理成功: {event_type}")
                return jsonify({'received': True, 'result': result}), 200
            else:
                logger.error(f"Stripe Webhook処理失敗: {result.get('message')}")
                return jsonify({'error': result.get('message')}), 500
        
        elif event_type in ['payment_intent.payment_failed', 'checkout.session.expired']:
            # 支払い失敗・期限切れイベント
            logger.info(f"Stripe 支払い失敗/期限切れイベント: {event_type}")
            return jsonify({'received': True, 'message': 'Payment failure logged'}), 200
        
        else:
            # その他のイベント（現在は無視）
            logger.info(f"Stripe 未対応イベント: {event_type}")
            return jsonify({'received': True, 'message': 'Event type not handled'}), 200
    
    except Exception as e:
        logger.error(f"Stripe Webhook処理エラー: {str(e)}")
        return jsonify({'error': f'Webhook processing error: {str(e)}'}), 500

@stripe_webhook_bp.route('/stripe/test', methods=['POST'])
def test_stripe_webhook():
    """
    Stripe Webhookテスト用エンドポイント（開発用）
    """
    try:
        # テスト用の模擬イベントデータ
        test_event = {
            'type': 'checkout.session.completed',
            'id': 'evt_test_webhook',
            'data': {
                'object': {
                    'object': 'checkout.session',
                    'id': 'cs_test_session',
                    'customer_details': {
                        'email': 'test@example.com'
                    },
                    'amount_total': 10000,  # 100円（cent単位）
                    'currency': 'jpy',
                    'payment_status': 'paid'
                }
            }
        }
        
        result = process_payment_completed(test_event)
        
        logger.info("Stripe Webhookテスト実行完了")
        
        return jsonify({
            'test': True,
            'result': result
        }), 200
        
    except Exception as e:
        logger.error(f"Stripe Webhookテストエラー: {str(e)}")
        return jsonify({'error': f'Test error: {str(e)}'}), 500