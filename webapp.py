#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PDF PayPal System - Web Application
第三者向けの設定可能なウェブアプリケーション

このアプリケーションは、第三者が独自の環境変数を設定して
PDF処理とPayPal決済リンク生成を行うことができるウェブインターフェースを提供します。
"""

import os
import sys
import json
import logging
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import pdfplumber
import requests
from webapp_extractors import extract_amount_and_customer

# ロガー設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pdf-paypal-web-app-secret-key-2025')

# 設定ファイルのパス
CONFIG_FILE = 'webapp_config.json'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

# アップロードフォルダを作成
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """アップロードされたファイルが許可された拡張子かチェック"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_config():
    """設定ファイルから設定を読み込み"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"設定読み込みエラー: {e}")
    
    # デフォルト設定
    return {
        'paypal_client_id': '',
        'paypal_client_secret': '',
        'paypal_mode': 'sandbox',
        'admin_password': '',
        'app_title': 'PDF PayPal決済リンク生成システム',
        'currency': 'JPY',
        'default_amount': 1000
    }

def save_config(config):
    """設定をファイルに保存"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"設定保存エラー: {e}")
        return False

def get_paypal_access_token(client_id, client_secret, mode):
    """PayPal APIのアクセストークンを取得"""
    api_base = "https://api-m.sandbox.paypal.com" if mode == "sandbox" else "https://api-m.paypal.com"
    url = f"{api_base}/v1/oauth2/token"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US"
    }
    data = {"grant_type": "client_credentials"}
    response = requests.post(
        url, 
        auth=(client_id, client_secret),
        headers=headers,
        data=data
    )
    response.raise_for_status()
    return response.json()["access_token"]

def create_paypal_payment_link(client_id, client_secret, mode, amount, currency="JPY", description=""):
    """PayPalの決済リンクを作成"""
    api_base = "https://api-m.sandbox.paypal.com" if mode == "sandbox" else "https://api-m.paypal.com"
    access_token = get_paypal_access_token(client_id, client_secret, mode)
    url = f"{api_base}/v2/checkout/orders"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": currency,
                    "value": str(amount)
                },
                "description": description[:127] if description else "PDF Payment"
            }
        ],
        "application_context": {
            "return_url": request.url_root + "payment_success",
            "cancel_url": request.url_root + "payment_cancel"
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    response_data = response.json()
    
    # リンクを探す
    for link in response_data["links"]:
        if link["rel"] == "approve":
            return link["href"]
    
    return None

def extract_text_from_pdf(pdf_path):
    """PDFからテキストを抽出"""
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or '' for page in pdf.pages)

@app.route('/')
def index():
    """メインページ"""
    config = load_config()
    return render_template('webapp_index.html', config=config)

@app.route('/settings')
def settings():
    """設定ページ"""
    config = load_config()
    return render_template('webapp_settings.html', config=config)

@app.route('/settings/save', methods=['POST'])
def save_settings():
    """設定を保存"""
    config = load_config()
    
    # フォームから設定を取得
    config['paypal_client_id'] = request.form.get('paypal_client_id', '')
    config['paypal_client_secret'] = request.form.get('paypal_client_secret', '')
    config['paypal_mode'] = request.form.get('paypal_mode', 'sandbox')
    config['app_title'] = request.form.get('app_title', 'PDF PayPal決済リンク生成システム')
    config['currency'] = request.form.get('currency', 'JPY')
    config['default_amount'] = int(request.form.get('default_amount', 1000))
    
    # 管理者パスワードは空でない場合のみ更新
    new_password = request.form.get('admin_password', '')
    if new_password:
        config['admin_password'] = generate_password_hash(new_password)
    
    if save_config(config):
        flash('設定が保存されました', 'success')
    else:
        flash('設定の保存に失敗しました', 'error')
    
    return redirect(url_for('settings'))

@app.route('/settings/test', methods=['POST'])
def test_connection():
    """PayPal接続をテスト"""
    config = load_config()
    client_id = request.form.get('paypal_client_id') or config.get('paypal_client_id')
    client_secret = request.form.get('paypal_client_secret') or config.get('paypal_client_secret')
    mode = request.form.get('paypal_mode') or config.get('paypal_mode', 'sandbox')
    
    try:
        if not client_id or not client_secret:
            return jsonify({'success': False, 'message': 'PayPalのクライアントIDとシークレットが必要です'})
        
        token = get_paypal_access_token(client_id, client_secret, mode)
        if token:
            return jsonify({'success': True, 'message': 'PayPal接続テストが成功しました'})
        else:
            return jsonify({'success': False, 'message': 'アクセストークンの取得に失敗しました'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'接続エラー: {str(e)}'})

@app.route('/upload', methods=['POST'])
def upload_file():
    """PDFファイルをアップロードして処理"""
    if 'file' not in request.files:
        flash('ファイルが選択されていません', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('ファイルが選択されていません', 'error')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        config = load_config()
        
        # PayPal設定をチェック
        if not config.get('paypal_client_id') or not config.get('paypal_client_secret'):
            flash('PayPal設定が完了していません。設定ページで設定を行ってください。', 'error')
            return redirect(url_for('settings'))
        
        try:
            # ファイルを一時保存
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            # PDFからテキスト抽出
            text = extract_text_from_pdf(filepath)
            
            # 金額と顧客名を抽出
            extraction_result = extract_amount_and_customer(text)
            customer_name = extraction_result.customer or "不明"
            amount = extraction_result.amount or config.get('default_amount', 1000)
            
            # 決済リンクを生成
            description = f"{customer_name} {filename}".strip()
            payment_url = create_paypal_payment_link(
                config['paypal_client_id'],
                config['paypal_client_secret'],
                config['paypal_mode'],
                amount,
                config.get('currency', 'JPY'),
                description
            )
            
            if payment_url:
                result = {
                    'filename': filename,
                    'customer_name': customer_name,
                    'amount': amount,
                    'currency': config.get('currency', 'JPY'),
                    'payment_url': payment_url,
                    'description': description,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # 一時ファイルを削除
                os.remove(filepath)
                
                return render_template('webapp_result.html', result=result, config=config)
            else:
                flash('決済リンクの生成に失敗しました', 'error')
                
        except Exception as e:
            logger.error(f"処理エラー: {e}")
            flash(f'処理中にエラーが発生しました: {str(e)}', 'error')
            
            # 一時ファイルを削除
            if os.path.exists(filepath):
                os.remove(filepath)
    else:
        flash('PDFファイルのみアップロード可能です', 'error')
    
    return redirect(url_for('index'))

@app.route('/payment_success')
def payment_success():
    """決済成功ページ"""
    return render_template('webapp_payment_success.html')

@app.route('/payment_cancel')
def payment_cancel():
    """決済キャンセルページ"""
    return render_template('webapp_payment_cancel.html')

@app.route('/admin')
def admin():
    """管理者ページ"""
    config = load_config()
    if not config.get('admin_password'):
        flash('管理者パスワードが設定されていません', 'error')
        return redirect(url_for('settings'))
    
    return render_template('webapp_admin.html', config=config)

@app.route('/health')
def health():
    """ヘルスチェック"""
    return jsonify({'status': 'healthy', 'timestamp': str(datetime.now())})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)