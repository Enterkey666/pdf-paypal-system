#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ローカル開発用アプリケーション
Firebase Emulatorを使用してローカル環境でテスト
"""

import os
import sys
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from werkzeug.utils import secure_filename
import tempfile

# 既存のモジュールをインポート
try:
    from config_manager import get_config
    from customer_extractor import extract_customer
    from amount_extractor import extract_invoice_amount
    import paypal_utils
    import stripe_utils
except ImportError as e:
    print(f"既存モジュールのインポートエラー: {e}")
    print("Firebase版のモジュールを使用します")

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
app.secret_key = 'local-dev-secret-key'

# ローカル設定（環境変数または設定ファイルから読み込み）
def get_local_config():
    """ローカル開発用設定を取得"""
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # デフォルト設定
    return {
        'paypal_mode': 'sandbox',
        'paypal_client_id': os.environ.get('PAYPAL_CLIENT_ID', ''),
        'paypal_client_secret': os.environ.get('PAYPAL_CLIENT_SECRET', ''),
        'stripe_secret_key': os.environ.get('STRIPE_SECRET_KEY', ''),
        'stripe_publishable_key': os.environ.get('STRIPE_PUBLISHABLE_KEY', ''),
        'default_currency': 'JPY',
        'default_amount': 1000,
    }

# 設定読み込み
config = get_local_config()

@app.route('/')
def index():
    """メインページ"""
    return render_template_string("""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PDF PayPal System - ローカル開発版</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        .dev-notice {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            text-align: center;
        }
        .upload-area {
            border: 2px dashed #ddd;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            margin: 20px 0;
            background-color: #fafafa;
        }
        .form-group {
            margin: 20px 0;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: bold;
        }
        input, select {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        button {
            background-color: #007cba;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            margin: 10px 5px;
        }
        button:hover {
            background-color: #005a87;
        }
        button:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        .results {
            margin-top: 30px;
            display: none;
        }
        .payment-link {
            background: #e8f5e8;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
            border-left: 4px solid #28a745;
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
            border-left: 4px solid #dc3545;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>PDF PayPal System</h1>
        <div class="dev-notice">
            <strong>🛠️ ローカル開発版</strong><br>
            このバージョンはローカル開発・テスト用です
        </div>

        <form id="uploadForm" enctype="multipart/form-data">
            <div class="upload-area" onclick="document.getElementById('fileInput').click()">
                <p>PDFファイルをクリックして選択</p>
                <input type="file" id="fileInput" name="file" accept=".pdf" style="display: none;">
            </div>

            <div class="form-group">
                <label for="paymentProvider">決済方法</label>
                <select id="paymentProvider" name="payment_provider" required>
                    <option value="stripe">Stripe</option>
                    <option value="paypal">PayPal</option>
                </select>
            </div>

            <div class="form-group">
                <label for="currency">通貨</label>
                <select id="currency" name="currency" required>
                    <option value="JPY">JPY (日本円)</option>
                    <option value="USD">USD (米ドル)</option>
                </select>
            </div>

            <div class="form-group">
                <label for="defaultAmount">デフォルト金額</label>
                <input type="number" id="defaultAmount" name="default_amount" min="1" value="1000" required>
            </div>

            <button type="submit" id="processBtn">PDF処理開始</button>
        </form>

        <div id="results" class="results">
            <h2>処理結果</h2>
            <div id="resultContent"></div>
        </div>
    </div>

    <script>
        const fileInput = document.getElementById('fileInput');
        const uploadForm = document.getElementById('uploadForm');
        const results = document.getElementById('results');
        const resultContent = document.getElementById('resultContent');

        fileInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                document.querySelector('.upload-area p').textContent = `選択されたファイル: ${file.name}`;
            }
        });

        uploadForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const processBtn = document.getElementById('processBtn');
            
            if (!fileInput.files[0]) {
                alert('PDFファイルを選択してください');
                return;
            }

            processBtn.disabled = true;
            processBtn.textContent = '処理中...';
            results.style.display = 'none';

            try {
                const response = await fetch('/api/process-pdf', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                
                if (data.success) {
                    showResults(data);
                } else {
                    showError(data.error || '処理に失敗しました');
                }

            } catch (error) {
                console.error('処理エラー:', error);
                showError('処理中にエラーが発生しました: ' + error.message);
            } finally {
                processBtn.disabled = false;
                processBtn.textContent = 'PDF処理開始';
            }
        });

        function showResults(data) {
            results.style.display = 'block';
            resultContent.innerHTML = '';

            if (data.payments && data.payments.length > 0) {
                data.payments.forEach((payment, index) => {
                    const paymentDiv = document.createElement('div');
                    paymentDiv.className = 'payment-link';
                    paymentDiv.innerHTML = `
                        <h3>決済リンク ${index + 1}</h3>
                        <p><strong>顧客:</strong> ${payment.customer || '不明'}</p>
                        <p><strong>金額:</strong> ${payment.amount} ${payment.currency}</p>
                        <p><strong>決済方法:</strong> ${payment.provider}</p>
                        <p><a href="${payment.link}" target="_blank" style="color: #007cba;">決済ページを開く</a></p>
                    `;
                    resultContent.appendChild(paymentDiv);
                });
            } else {
                showError('決済リンクが生成されませんでした');
            }
        }

        function showError(message) {
            results.style.display = 'block';
            resultContent.innerHTML = `<div class="error">${message}</div>`;
        }
    </script>
</body>
</html>
    """)

@app.route('/api/process-pdf', methods=['POST'])
def process_pdf():
    """PDF処理API（ローカル版）"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'ファイルが選択されていません'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'ファイルが選択されていません'})
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'error': 'PDFファイルを選択してください'})
        
        # フォームデータ取得
        payment_provider = request.form.get('payment_provider', 'stripe')
        currency = request.form.get('currency', 'JPY')
        default_amount = int(request.form.get('default_amount', 1000))
        
        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            file.save(tmp_file.name)
            temp_path = tmp_file.name
        
        try:
            # PDF処理（既存のロジックを使用）
            results = process_pdf_file(temp_path, payment_provider, currency, default_amount)
            return jsonify({
                'success': True,
                'payments': results
            })
            
        finally:
            # 一時ファイル削除
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
    except Exception as e:
        logger.error(f"PDF処理エラー: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

def process_pdf_file(pdf_path, payment_provider, currency, default_amount):
    """PDFファイル処理（簡易版）"""
    try:
        # 既存の抽出ロジックを使用（エラーハンドリング付き）
        customer_info = "テスト顧客"  # デフォルト値
        amount = default_amount  # デフォルト値
        
        # 既存のモジュールが利用可能な場合は使用
        try:
            customer_info = extract_customer(pdf_path)
            if not customer_info:
                customer_info = "不明な顧客"
        except Exception as e:
            logger.warning(f"顧客抽出エラー: {e}")
        
        try:
            extracted_amount = extract_invoice_amount(pdf_path)
            if extracted_amount and extracted_amount > 0:
                amount = extracted_amount
        except Exception as e:
            logger.warning(f"金額抽出エラー: {e}")
        
        # 決済リンク生成（モック版）
        if payment_provider == 'stripe':
            payment_link = f"https://checkout.stripe.com/pay/test#{amount}_{currency}"
        else:  # paypal
            payment_link = f"https://www.sandbox.paypal.com/cgi-bin/webscr?amount={amount}&currency_code={currency}"
        
        return [{
            'customer': customer_info,
            'amount': amount,
            'currency': currency,
            'provider': payment_provider,
            'link': payment_link
        }]
        
    except Exception as e:
        logger.error(f"PDF処理エラー: {str(e)}")
        raise

@app.route('/health')
def health_check():
    """ヘルスチェック"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': 'local-dev'
    })

@app.route('/config')
def show_config():
    """設定確認用エンドポイント"""
    safe_config = config.copy()
    # 機密情報をマスク
    for key in ['paypal_client_secret', 'stripe_secret_key']:
        if key in safe_config and safe_config[key]:
            safe_config[key] = '*' * 10
    
    return jsonify(safe_config)

if __name__ == '__main__':
    print("🚀 ローカル開発サーバーを起動中...")
    print("📋 設定確認: http://localhost:5000/config")
    print("🏥 ヘルスチェック: http://localhost:5000/health")
    print("📄 メインページ: http://localhost:5000")
    
    app.run(debug=True, host='0.0.0.0', port=5000)