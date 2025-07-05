#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PayPal Webhook 処理モジュール
PayPalからのWebhookイベントを処理し、支払いステータスを更新する
"""

import os
import json
import logging
import requests
import base64
import hashlib
import hmac
import time
from typing import Dict, Any, Tuple, Optional

# ロガー設定
logger = logging.getLogger(__name__)

# データベース関数をインポート
from database import update_payment_status, get_payment_status_by_order_id

# 設定ファイルからWebhook IDを取得する関数
def get_webhook_id():
    """
    設定ファイルからPayPal Webhook IDを取得する
    
    Returns:
        str: PayPal Webhook ID
    """
    try:
        # 設定ファイルのパスを取得
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        
        # 設定ファイルが存在するか確認
        if not os.path.exists(config_path):
            logger.warning(f"設定ファイルが見つかりません: {config_path}")
            return None
            
        # 設定ファイルを読み込む
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # Webhook IDを取得
        webhook_id = config.get('PAYPAL_WEBHOOK_ID')
        
        if not webhook_id:
            logger.warning("設定ファイルにPAYPAL_WEBHOOK_IDが設定されていません")
            return None
            
        return webhook_id
        
    except Exception as e:
        logger.error(f"Webhook ID取得エラー: {str(e)}")
        return None

def verify_webhook_signature(
    transmission_id: str,
    timestamp: str,
    webhook_id: str,
    event_body: str,
    cert_url: str,
    actual_sig: str,
    auth_algo: str = "SHA256withRSA"
) -> bool:
    """
    PayPal Webhookシグネチャを検証する
    
    Args:
        transmission_id (str): PayPalから送信されたtransmission_id
        timestamp (str): PayPalから送信されたタイムスタンプ
        webhook_id (str): PayPalダッシュボードで設定したWebhook ID
        event_body (str): イベント本文の生文字列
        cert_url (str): PayPal証明書URL
        actual_sig (str): PayPalから送信された署名
        auth_algo (str): 認証アルゴリズム
        
    Returns:
        bool: 署名が有効かどうか
    """
    try:
        # webhook_idが空の場合は設定ファイルから取得
        if not webhook_id:
            webhook_id = get_webhook_id()
            
            # 設定ファイルにない場合は環境変数を試す
            if not webhook_id:
                webhook_id = os.environ.get('PAYPAL_WEBHOOK_ID', '')
                
            # どこにも設定がない場合はエラー
            if not webhook_id:
                logger.error("PayPal Webhook IDが設定されていません")
                return False
        
        # 証明書を取得
        try:
            cert_response = requests.get(cert_url)
            if cert_response.status_code != 200:
                logger.error(f"証明書の取得に失敗: {cert_response.status_code}")
                return False
            cert_data = cert_response.content
        except Exception as cert_err:
            logger.error(f"証明書取得エラー: {str(cert_err)}")
            return False
        
        # 検証文字列を作成
        validation_str = transmission_id + "|" + timestamp + "|" + webhook_id + "|" + hashlib.sha256(event_body.encode('utf-8')).hexdigest()
        
        # 署名を検証
        try:
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives import hashes
            from cryptography import x509
            
            # 証明書からパブリックキーを取得
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            public_key = cert.public_key()
            
            # 署名をデコード
            signature = base64.b64decode(actual_sig)
            
            # 署名を検証
            try:
                public_key.verify(
                    signature,
                    validation_str.encode('utf-8'),
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
                logger.info("PayPal Webhook署名の検証に成功しました")
                return True
            except Exception as verify_err:
                logger.error(f"署名検証エラー: {str(verify_err)}")
                return False
                
        except Exception as crypto_err:
            logger.error(f"暗号化処理エラー: {str(crypto_err)}")
            return False
            
    except Exception as e:
        logger.error(f"Webhook署名検証中の例外: {str(e)}")
        return False

def extract_order_id(event_data: Dict[str, Any]) -> Optional[str]:
    """
    イベントデータからPayPal注文IDを抽出する
    
    Args:
        event_data (Dict[str, Any]): PayPalイベントデータ
        
    Returns:
        Optional[str]: 注文ID、見つからない場合はNone
    """
    try:
        # イベントタイプに基づいて適切なパスから注文IDを抽出
        event_type = event_data.get('event_type', '')
        
        # CHECKOUT.ORDER.APPROVED イベントの場合
        if 'CHECKOUT.ORDER' in event_type:
            return event_data.get('resource', {}).get('id')
        
        # PAYMENT.CAPTURE イベントの場合
        elif 'PAYMENT.CAPTURE' in event_type:
            links = event_data.get('resource', {}).get('links', [])
            for link in links:
                if link.get('rel') == 'up':
                    # リンクからorder_idを抽出 (例: /v2/checkout/orders/5O190127TN364715T)
                    href = link.get('href', '')
                    if '/orders/' in href:
                        return href.split('/orders/')[1]
        
        # その他のイベントタイプの場合
        return event_data.get('resource', {}).get('id') or event_data.get('resource', {}).get('order_id')
    
    except Exception as e:
        logger.error(f"注文ID抽出エラー: {str(e)}")
        return None

def process_payment_webhook(event_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    PayPal Webhookイベントを処理する
    
    Args:
        event_data (Dict[str, Any]): PayPalイベントデータ
        
    Returns:
        Tuple[bool, str]: 処理成功フラグとメッセージ
    """
    try:
        # イベントタイプを取得
        event_type = event_data.get('event_type', '')
        logger.info(f"PayPal Webhookイベント処理: {event_type}")
        
        # 注文IDを抽出
        order_id = extract_order_id(event_data)
        if not order_id:
            logger.error("イベントから注文IDを抽出できませんでした")
            return False, "注文IDが見つかりません"
        
        # イベントタイプに基づいて処理
        if 'CHECKOUT.ORDER.APPROVED' in event_type:
            # 注文が承認された
            status = "APPROVED"
            message = "注文が承認されました"
            
        elif 'PAYMENT.CAPTURE.COMPLETED' in event_type:
            # 支払いが完了した
            status = "COMPLETED"
            message = "支払いが完了しました"
            
            # 支払いIDを取得
            payment_id = event_data.get('resource', {}).get('id')
            
            # データベースを更新
            success, db_msg = update_payment_status(order_id, status, payment_id)
            if success:
                logger.info(f"支払いステータス更新成功: {order_id} -> {status}")
                return True, f"支払いステータスを更新しました: {message}"
            else:
                logger.warning(f"支払いステータス更新失敗: {db_msg}")
                return False, f"データベース更新エラー: {db_msg}"
                
        elif 'PAYMENT.CAPTURE.DENIED' in event_type:
            # 支払いが拒否された
            status = "DENIED"
            message = "支払いが拒否されました"
            
        elif 'PAYMENT.CAPTURE.REFUNDED' in event_type:
            # 返金された
            status = "REFUNDED"
            message = "支払いが返金されました"
            
        else:
            # その他のイベント
            status = event_type
            message = f"イベント受信: {event_type}"
        
        # データベースを更新
        success, db_msg = update_payment_status(order_id, status)
        if success:
            logger.info(f"支払いステータス更新成功: {order_id} -> {status}")
            return True, f"支払いステータスを更新しました: {message}"
        else:
            logger.warning(f"支払いステータス更新失敗: {db_msg}")
            return False, f"データベース更新エラー: {db_msg}"
            
    except Exception as e:
        logger.error(f"Webhookイベント処理中の例外: {str(e)}")
        return False, f"処理エラー: {str(e)}"
