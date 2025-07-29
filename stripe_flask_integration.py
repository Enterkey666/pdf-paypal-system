#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe Subscription Blueprint
サブスクリプション管理用のBlueprint、Checkout、Portal、Webhookルート
"""

import os
import json
import logging
from flask import Blueprint, request, jsonify, redirect, session, current_app
from flask_login import login_required, current_user
from stripe_utils import (
    create_subscription_checkout_session,
    create_customer_portal_session,
    verify_webhook_signature,
    process_stripe_webhook,
    get_stripe_keys
)

# ロガーの設定
logger = logging.getLogger(__name__)

# Blueprint作成
stripe_bp = Blueprint('stripe', __name__, url_prefix='/api/stripe')

@stripe_bp.route('/checkout', methods=['POST'])
@login_required
def create_checkout():
    """
    サブスクリプションCheckout Session作成
    
    Body: {"plan": "monthly" | "yearly"}
    """
    try:
        data = request.get_json()
        if not data or 'plan' not in data:
            return jsonify({
                'success': False,
                'message': 'プランが指定されていません'
            }), 400
        
        plan = data['plan']
        if plan not in ['monthly', 'yearly']:
            return jsonify({
                'success': False,
                'message': '無効なプランです'
            }), 400
        
        # 成功/キャンセルURLを構築
        base_url = request.host_url.rstrip('/')
        success_url = f"{base_url}/payment_success?provider=stripe"
        cancel_url = f"{base_url}/payment_cancel?provider=stripe"
        
        # Checkout Session作成
        result = create_subscription_checkout_session(
            user_id=current_user.id,
            plan=plan,
            success_url=success_url,
            cancel_url=cancel_url
        )
        
        if result['success']:
            logger.info(f"Checkout Session作成: user_id={current_user.id}, plan={plan}")
            return jsonify({
                'success': True,
                'checkout_url': result['checkout_url'],
                'session_id': result.get('session_id')
            })
        else:
            logger.error(f"Checkout Session作成失敗: {result['message']}")
            return jsonify({
                'success': False,
                'message': result['message']
            }), 500
            
    except Exception as e:
        logger.error(f"Checkout Session作成エラー: {str(e)}")
        return jsonify({
            'success': False,
            'message': '内部エラーが発生しました'
        }), 500

@stripe_bp.route('/portal', methods=['GET'])
@login_required
def customer_portal():
    """
    Stripe Customer Portalセッション作成とリダイレクト
    """
    try:
        # 戻りURLを設定
        return_url = os.environ.get('STRIPE_PORTAL_RETURN_URL')
        if not return_url:
            return_url = f"{request.host_url.rstrip('/')}/settings"
        
        # Portal Session作成
        result = create_customer_portal_session(
            user_id=current_user.id,
            return_url=return_url
        )
        
        if result['success']:
            logger.info(f"Portal Session作成: user_id={current_user.id}")
            return redirect(result['portal_url'])
        else:
            logger.error(f"Portal Session作成失敗: {result['message']}")
            return jsonify({
                'success': False,
                'message': result['message']
            }), 500
            
    except Exception as e:
        logger.error(f"Portal Session作成エラー: {str(e)}")
        return jsonify({
            'success': False,
            'message': '内部エラーが発生しました'
        }), 500

@stripe_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """
    Stripe Webhookエンドポイント
    """
    try:
        # ペイロードと署名を取得
        payload = request.get_data()
        signature = request.headers.get('Stripe-Signature')
        
        if not signature:
            logger.error("Webhook: Stripe-Signatureヘッダーがありません")
            return jsonify({'error': 'Missing signature'}), 400
        
        # Webhook秘密鍵を取得
        webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
        if not webhook_secret:
            logger.error("Webhook: STRIPE_WEBHOOK_SECRETが設定されていません")
            return jsonify({'error': 'Webhook secret not configured'}), 500
        
        # 署名検証
        if not verify_webhook_signature(payload, signature, webhook_secret):
            logger.error("Webhook: 署名検証失敗")
            return jsonify({'error': 'Invalid signature'}), 400
        
        # イベントデータをパース
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            logger.error("Webhook: 無効なJSONペイロード")
            return jsonify({'error': 'Invalid JSON'}), 400
        
        # イベント処理
        result = process_stripe_webhook(event)
        
        if result['success']:
            logger.info(f"Webhook処理成功: {event.get('type')} - {result['message']}")
            return jsonify({'received': True}), 200
        else:
            logger.error(f"Webhook処理失敗: {event.get('type')} - {result['message']}")
            return jsonify({'error': result['message']}), 500
            
    except Exception as e:
        logger.error(f"Webhookエラー: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@stripe_bp.route('/config', methods=['GET'])
@login_required
def get_stripe_config():
    """
    Stripe設定情報を取得（フロントエンド用）
    """
    try:
        keys = get_stripe_keys()
        
        # フロントエンドに必要な情報のみ返す
        return jsonify({
            'publishable_key': keys['publishable_key'],
            'mode': keys['mode'],
            'configured': bool(keys['secret_key'] and keys['publishable_key'])
        })
        
    except Exception as e:
        logger.error(f"Stripe設定取得エラー: {str(e)}")
        return jsonify({
            'error': '設定取得エラー'
        }), 500

def register_stripe_blueprint(app):
    """
    Stripe Blueprintをアプリに登録
    
    Args:
        app: Flaskアプリケーションインスタンス
    """
    try:
        app.register_blueprint(stripe_bp)
        logger.info("Stripe Blueprintが登録されました")
    except Exception as e:
        logger.error(f"Stripe Blueprint登録エラー: {str(e)}")
        raise

# 既存アプリとの統合用関数
def integrate_with_existing_app(app):
    """
    既存のapp.pyとの統合
    
    Args:
        app: Flaskアプリケーションインスタンス
    """
    # Blueprint登録
    register_stripe_blueprint(app)
    
    # 既存の/payment_successルートでStripeセッションを処理
    def handle_stripe_payment_success():
        """
        Stripe決済成功時の処理を既存ルートに統合
        """
        session_id = request.args.get('session_id')
        provider = request.args.get('provider')
        
        if provider == 'stripe' and session_id:
            logger.info(f"Stripe決済成功: session_id={session_id}")
            # セッションに成功メッセージを設定
            session['payment_success_message'] = 'サブスクリプションの登録が完了しました。'
    
    return handle_stripe_payment_success