#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe Flask統合モジュール
app.pyに統合するためのルート定義とブループリント登録
"""

import logging
from flask import Flask
from stripe_webhook import stripe_webhook_bp
from stripe_routes import stripe_bp
from provider_api_routes import provider_api_bp

# ロガーの設定
logger = logging.getLogger(__name__)

def register_stripe_blueprints(app: Flask) -> None:
    """
    Stripe関連のブループリントをFlaskアプリに登録
    
    Args:
        app (Flask): Flaskアプリケーションインスタンス
    """
    try:
        # Stripe Webhook Blueprint登録
        app.register_blueprint(stripe_webhook_bp)
        logger.info("Stripe Webhook Blueprintを登録しました")
        
        # Stripe設定管理 Blueprint登録
        app.register_blueprint(stripe_bp)
        logger.info("Stripe設定管理 Blueprintを登録しました")
        
        # 決済プロバイダーAPI Blueprint登録
        app.register_blueprint(provider_api_bp)
        logger.info("決済プロバイダーAPI Blueprintを登録しました")
        
    except Exception as e:
        logger.error(f"Stripe Blueprints登録エラー: {str(e)}")
        raise

def add_stripe_routes_to_existing_app(app: Flask) -> None:
    """
    既存のFlaskアプリにStripe関連ルートを追加
    
    Args:
        app (Flask): 既存のFlaskアプリケーションインスタンス
    """
    
    @app.route('/api/stripe/test', methods=['GET', 'POST'])
    def stripe_comprehensive_test():
        """
        Stripe機能の包括的テスト用エンドポイント
        """
        try:
            from flask import jsonify, request
            
            # JSON形式が要求されている場合は必ずJSONで応答
            is_json_request = request.args.get('format') == 'json'
            
            try:
                from stripe_test_utils import run_stripe_comprehensive_test, generate_test_report
                
                logger.info("Stripe包括的テスト実行")
                
                # テスト実行
                test_results = run_stripe_comprehensive_test()
                
                # リクエスト形式に応じてレスポンスを変更
                if is_json_request:
                    # JSON形式でレスポンス
                    return jsonify(test_results)
                else:
                    # HTMLレポート生成
                    html_report = generate_test_report(test_results)
                    from flask import render_template_string
                    
                    html_template = """
                    <!DOCTYPE html>
                    <html lang="ja">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Stripe機能テストレポート</title>
                        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
                        <style>
                            .test-report { margin: 2rem; }
                            .test-item { margin: 1rem 0; padding: 1rem; border: 1px solid #ddd; border-radius: 5px; }
                            .test-summary { background: #f8f9fa; padding: 1rem; border-radius: 5px; margin-bottom: 2rem; }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            {{ html_report|safe }}
                            <div class="mt-4">
                                <a href="/settings" class="btn btn-primary">設定画面に戻る</a>
                                <a href="/api/stripe/test?format=json" class="btn btn-secondary">JSON形式で表示</a>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    
                    return render_template_string(html_template, html_report=html_report)
                    
            except ImportError as import_error:
                logger.error(f"Stripe test utils インポートエラー: {str(import_error)}")
                if is_json_request:
                    return jsonify({
                        'success': False,
                        'error': f'テストモジュールのインポートに失敗しました: {str(import_error)}'
                    }), 500
                else:
                    raise  # HTMLの場合は外側のexception handlerに委ねる
                
        except Exception as e:
            logger.error(f"Stripe包括的テストエラー: {str(e)}")
            # JSON要求の場合は必ずJSONで応答
            if request.args.get('format') == 'json':
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
            else:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
    
    @app.route('/api/stripe/config/validate', methods=['GET'])
    def validate_stripe_config():
        """
        Stripe設定検証エンドポイント
        """
        try:
            from stripe_utils import validate_stripe_configuration
            from flask import jsonify
            
            result = validate_stripe_configuration()
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Stripe設定検証エラー: {str(e)}")
            return jsonify({
                'valid': False,
                'error': str(e)
            }), 500
    
    @app.route('/api/stripe/payment_link', methods=['POST'])
    def create_stripe_payment_link_api():
        """
        Stripe Payment Link作成API
        """
        try:
            from stripe_utils import create_stripe_payment_link
            from flask import request, jsonify
            
            # JSONデータを取得
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'message': 'リクエストデータが見つかりません'
                }), 400
            
            # 必要なパラメータを取得
            amount = data.get('amount')
            customer_name = data.get('customer_name', '')
            description = data.get('description', '')
            currency = data.get('currency', 'jpy')
            
            # パラメータ検証
            if not amount or amount <= 0:
                return jsonify({
                    'success': False,
                    'message': '有効な金額を指定してください'
                }), 400
            
            if not customer_name:
                return jsonify({
                    'success': False,
                    'message': '顧客名を指定してください'
                }), 400
            
            # Payment Link作成
            result = create_stripe_payment_link(
                amount=float(amount),
                customer_name=customer_name,
                description=description,
                currency=currency
            )
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Stripe Payment Link作成APIエラー: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Payment Link作成エラー: {str(e)}'
            }), 500
    
    @app.route('/api/stripe/payment_link/from_ocr', methods=['POST'])
    def create_stripe_payment_link_from_ocr_api():
        """
        OCRデータからStripe Payment Link作成API
        """
        try:
            from payment_utils import create_payment_link_from_ocr
            from flask import request, jsonify
            
            # JSONデータを取得
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'message': 'リクエストデータが見つかりません'
                }), 400
            
            # 必要なパラメータを取得
            ocr_data = data.get('ocr_data', {})
            filename = data.get('filename', '')
            override_amount = data.get('override_amount')
            override_customer = data.get('override_customer')
            
            if not ocr_data:
                return jsonify({
                    'success': False,
                    'message': 'OCRデータが見つかりません'
                }), 400
            
            # OCRデータからPayment Link作成
            result = create_payment_link_from_ocr(
                provider='stripe',
                ocr_data=ocr_data,
                filename=filename,
                override_amount=override_amount,
                override_customer=override_customer
            )
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"OCRからStripe Payment Link作成APIエラー: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'OCRからPayment Link作成エラー: {str(e)}'
            }), 500
    
    logger.info("Stripe関連ルートを既存アプリに追加しました")

# app.pyに追加するためのインポート文
APP_PY_IMPORTS = """
# Stripe統合のためのインポート
try:
    from stripe_flask_integration import register_stripe_blueprints, add_stripe_routes_to_existing_app
    STRIPE_INTEGRATION_AVAILABLE = True
    print("✓ Stripe統合モジュールのインポート成功")
except ImportError as e:
    print(f"⚠ Stripe統合モジュールのインポート失敗: {e}")
    STRIPE_INTEGRATION_AVAILABLE = False
"""

# app.pyに追加するための統合コード
APP_PY_INTEGRATION_CODE = """
# Stripe統合の初期化
if STRIPE_INTEGRATION_AVAILABLE:
    try:
        # Blueprintの登録
        register_stripe_blueprints(app)
        
        # 追加ルートの登録
        add_stripe_routes_to_existing_app(app)
        
        logger.info("Stripe統合が正常に初期化されました")
    except Exception as e:
        logger.error(f"Stripe統合初期化エラー: {str(e)}")
else:
    logger.warning("Stripe統合が利用できません")
"""