import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
import firebase_admin
from firebase_admin import credentials, firestore, storage
from functions_framework import create_app
import stripe
import paypalrestsdk

# Firebase初期化
if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()
bucket = storage.bucket()

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app for Cloud Functions
app = Flask(__name__)

# 設定読み込み
def get_config():
    """環境変数から設定を読み込み"""
    return {
        'paypal_mode': os.environ.get('PAYPAL_MODE', 'sandbox'),
        'paypal_client_id': os.environ.get('PAYPAL_CLIENT_ID'),
        'paypal_client_secret': os.environ.get('PAYPAL_CLIENT_SECRET'),
        'stripe_secret_key': os.environ.get('STRIPE_SECRET_KEY'),
        'stripe_publishable_key': os.environ.get('STRIPE_PUBLISHABLE_KEY'),
        'default_currency': os.environ.get('DEFAULT_CURRENCY', 'JPY'),
    }

# PayPal設定
def configure_paypal():
    config = get_config()
    paypalrestsdk.configure({
        "mode": config['paypal_mode'],
        "client_id": config['paypal_client_id'],
        "client_secret": config['paypal_client_secret']
    })

# Stripe設定
def configure_stripe():
    config = get_config()
    stripe.api_key = config['stripe_secret_key']

@app.route('/health', methods=['GET'])
def health_check():
    """ヘルスチェック"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/api/create-payment-link', methods=['POST'])
def create_payment_link():
    """決済リンク作成API"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        amount = float(data.get('amount', 0))
        currency = data.get('currency', 'JPY')
        provider = data.get('provider', 'stripe')
        description = data.get('description', 'Payment')
        
        if not user_id or amount <= 0:
            return jsonify({'error': 'Invalid parameters'}), 400
        
        # 決済リンク作成
        if provider == 'stripe':
            configure_stripe()
            payment_link = create_stripe_payment_link(amount, currency, description)
        elif provider == 'paypal':
            configure_paypal()
            payment_link = create_paypal_payment_link(amount, currency, description)
        else:
            return jsonify({'error': 'Unsupported payment provider'}), 400
        
        # Firestoreに保存
        payment_doc = {
            'user_id': user_id,
            'amount': amount,
            'currency': currency,
            'provider': provider,
            'description': description,
            'payment_link': payment_link,
            'status': 'pending',
            'created_at': datetime.now(),
        }
        
        doc_ref = db.collection('payments').add(payment_doc)
        payment_doc['id'] = doc_ref[1].id
        
        return jsonify(payment_doc)
        
    except Exception as e:
        logger.error(f"Payment link creation error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

def create_stripe_payment_link(amount, currency, description):
    """Stripe決済リンク作成"""
    try:
        product = stripe.Product.create(name=description)
        price = stripe.Price.create(
            product=product.id,
            unit_amount=int(amount * 100),  # JPYの場合は円単位
            currency=currency.lower()
        )
        
        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            after_completion={"type": "redirect", "redirect": {"url": "https://your-domain.com/success"}}
        )
        
        return payment_link.url
    except Exception as e:
        logger.error(f"Stripe payment link error: {str(e)}")
        raise

def create_paypal_payment_link(amount, currency, description):
    """PayPal決済リンク作成"""
    try:
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {"payment_method": "paypal"},
            "redirect_urls": {
                "return_url": "https://your-domain.com/success",
                "cancel_url": "https://your-domain.com/cancel"
            },
            "transactions": [{
                "item_list": {"items": [{
                    "name": description,
                    "sku": "item",
                    "price": str(amount),
                    "currency": currency,
                    "quantity": 1
                }]},
                "amount": {
                    "total": str(amount),
                    "currency": currency
                },
                "description": description
            }]
        })
        
        if payment.create():
            for link in payment.links:
                if link.rel == "approval_url":
                    return link.href
        else:
            logger.error(f"PayPal payment creation error: {payment.error}")
            raise Exception("PayPal payment creation failed")
            
    except Exception as e:
        logger.error(f"PayPal payment link error: {str(e)}")
        raise

@app.route('/api/pdf-process', methods=['POST'])
def process_pdf():
    """PDF処理API"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        user_id = request.form.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        # Cloud Storageにアップロード
        filename = f"uploads/{user_id}/{datetime.now().isoformat()}_{file.filename}"
        blob = bucket.blob(filename)
        blob.upload_from_file(file)
        
        # PDF処理（既存のロジックを使用）
        # この部分は既存のPDF処理コードを移植
        
        # 処理結果をFirestoreに保存
        result_doc = {
            'user_id': user_id,
            'filename': filename,
            'status': 'processed',
            'created_at': datetime.now(),
            'file_url': blob.public_url
        }
        
        db.collection('pdf_history').add(result_doc)
        
        return jsonify(result_doc)
        
    except Exception as e:
        logger.error(f"PDF processing error: {str(e)}")
        return jsonify({'error': 'Processing failed'}), 500

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Stripe Webhook処理"""
    try:
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature')
        
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ.get('STRIPE_WEBHOOK_SECRET')
        )
        
        # Webhook処理ロジック
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            # 決済完了処理
            update_payment_status(session.get('metadata', {}).get('payment_id'), 'completed')
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Stripe webhook error: {str(e)}")
        return jsonify({'error': 'Webhook processing failed'}), 400

@app.route('/webhook/paypal', methods=['POST'])
def paypal_webhook():
    """PayPal Webhook処理"""
    try:
        data = request.get_json()
        event_type = data.get('event_type')
        
        if event_type == 'PAYMENT.SALE.COMPLETED':
            # 決済完了処理
            payment_id = data.get('resource', {}).get('parent_payment')
            update_payment_status(payment_id, 'completed')
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        logger.error(f"PayPal webhook error: {str(e)}")
        return jsonify({'error': 'Webhook processing failed'}), 400

def update_payment_status(payment_id, status):
    """決済ステータス更新"""
    try:
        doc_ref = db.collection('payments').document(payment_id)
        doc_ref.update({
            'status': status,
            'updated_at': datetime.now()
        })
        logger.info(f"Payment {payment_id} status updated to {status}")
    except Exception as e:
        logger.error(f"Status update error: {str(e)}")

# Cloud Functions用のエントリーポイント
def app_function(request):
    """Cloud Functions用のエントリーポイント"""
    with app.app_context():
        return app(request.environ, lambda *args: None)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))