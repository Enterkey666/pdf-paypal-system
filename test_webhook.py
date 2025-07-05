#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import json
import time
import os
import logging

# ロガー設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    """設定ファイルを読み込む"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"設定ファイル読み込みエラー: {str(e)}")
        return {}

def simulate_webhook_event(event_type="CHECKOUT.ORDER.APPROVED"):
    """PayPal Webhookイベントをシミュレートする"""
    
    config = load_config()
    webhook_url = "http://localhost:5000/webhook/paypal"
    
    # テスト用の注文ID
    order_id = "5O190127TN364715T"
    
    # イベントタイプに基づいてペイロードを作成
    if event_type == "CHECKOUT.ORDER.APPROVED":
        payload = {
            "id": "WH-58D329510W112710V-9KH94010MC7571132",
            "event_version": "1.0",
            "create_time": "2023-04-28T07:30:00.000Z",
            "resource_type": "checkout-order",
            "resource_version": "2.0",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "summary": "An order has been approved by buyer",
            "resource": {
                "create_time": "2023-04-28T07:25:12Z",
                "purchase_units": [
                    {
                        "reference_id": "default",
                        "amount": {
                            "currency_code": "JPY",
                            "value": "1000.00"
                        },
                        "payee": {
                            "email_address": "sb-43q0q25379099@business.example.com",
                            "merchant_id": "QKRY6BTWMQQ8C"
                        },
                        "description": "PDF処理サービス",
                        "custom_id": "PDF-123456",
                        "invoice_id": "INV-123456",
                        "soft_descriptor": "PDF処理"
                    }
                ],
                "links": [
                    {
                        "href": f"https://api.sandbox.paypal.com/v2/checkout/orders/{order_id}",
                        "rel": "self",
                        "method": "GET"
                    }
                ],
                "id": order_id,
                "intent": "CAPTURE",
                "payer": {
                    "name": {
                        "given_name": "John",
                        "surname": "Doe"
                    },
                    "email_address": "sb-47nr1d25379100@personal.example.com",
                    "payer_id": "QCEPS6HXTCW9N"
                },
                "status": "APPROVED"
            },
            "links": [
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-58D329510W112710V-9KH94010MC7571132",
                    "rel": "self",
                    "method": "GET"
                },
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-58D329510W112710V-9KH94010MC7571132/resend",
                    "rel": "resend",
                    "method": "POST"
                }
            ]
        }
    elif event_type == "PAYMENT.CAPTURE.COMPLETED":
        payload = {
            "id": "WH-4PP43238R1740622X-2MS07817V4168823B",
            "event_version": "1.0",
            "create_time": "2023-04-28T07:35:00.000Z",
            "resource_type": "capture",
            "resource_version": "2.0",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "summary": "Payment completed for JPY 1000",
            "resource": {
                "amount": {
                    "currency_code": "JPY",
                    "value": "1000.00"
                },
                "seller_protection": {
                    "status": "ELIGIBLE",
                    "dispute_categories": [
                        "ITEM_NOT_RECEIVED",
                        "UNAUTHORIZED_TRANSACTION"
                    ]
                },
                "supplementary_data": {
                    "related_ids": {
                        "order_id": order_id
                    }
                },
                "update_time": "2023-04-28T07:35:00Z",
                "create_time": "2023-04-28T07:35:00Z",
                "final_capture": True,
                "seller_receivable_breakdown": {
                    "gross_amount": {
                        "currency_code": "JPY",
                        "value": "1000.00"
                    },
                    "paypal_fee": {
                        "currency_code": "JPY",
                        "value": "50.00"
                    },
                    "net_amount": {
                        "currency_code": "JPY",
                        "value": "950.00"
                    }
                },
                "custom_id": "PDF-123456",
                "links": [
                    {
                        "href": "https://api.sandbox.paypal.com/v2/payments/captures/3C679366HH908993F",
                        "rel": "self",
                        "method": "GET"
                    },
                    {
                        "href": "https://api.sandbox.paypal.com/v2/payments/captures/3C679366HH908993F/refund",
                        "rel": "refund",
                        "method": "POST"
                    },
                    {
                        "href": f"https://api.sandbox.paypal.com/v2/checkout/orders/{order_id}",
                        "rel": "up",
                        "method": "GET"
                    }
                ],
                "id": "3C679366HH908993F",
                "status": "COMPLETED"
            },
            "links": [
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-4PP43238R1740622X-2MS07817V4168823B",
                    "rel": "self",
                    "method": "GET"
                },
                {
                    "href": "https://api.sandbox.paypal.com/v1/notifications/webhooks-events/WH-4PP43238R1740622X-2MS07817V4168823B/resend",
                    "rel": "resend",
                    "method": "POST"
                }
            ]
        }
    else:
        logger.error(f"未対応のイベントタイプ: {event_type}")
        return False, f"未対応のイベントタイプ: {event_type}"

    # ヘッダーを設定（実際のPayPalからのリクエストをシミュレート）
    # 注意: 実際の署名検証はスキップされる（テスト用）
    headers = {
        "Content-Type": "application/json",
        "Paypal-Transmission-Id": "12345678-1234-1234-1234-123456789012",
        "Paypal-Transmission-Time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Paypal-Cert-Url": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-360caa42-fca2a594-a5cafa77",
        "Paypal-Auth-Algo": "SHA256withRSA",
        "Paypal-Transmission-Sig": "dummy_signature_for_testing"
    }

    try:
        # WebhookエンドポイントにPOSTリクエストを送信
        response = requests.post(webhook_url, json=payload, headers=headers)
        
        # レスポンスを確認
        if response.status_code == 200:
            logger.info(f"Webhookリクエスト成功: {response.json()}")
            return True, response.json()
        else:
            logger.error(f"Webhookリクエスト失敗: ステータスコード {response.status_code}, レスポンス: {response.text}")
            return False, f"ステータスコード: {response.status_code}, レスポンス: {response.text}"
            
    except Exception as e:
        logger.error(f"Webhookリクエスト例外: {str(e)}")
        return False, str(e)

if __name__ == "__main__":
    # 引数がなければデフォルトのイベントタイプを使用
    import sys
    event_type = sys.argv[1] if len(sys.argv) > 1 else "CHECKOUT.ORDER.APPROVED"
    
    print(f"イベントタイプ '{event_type}' のWebhookをシミュレートします...")
    success, result = simulate_webhook_event(event_type)
    
    if success:
        print("Webhookシミュレーション成功!")
        print(f"結果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"Webhookシミュレーション失敗: {result}")
