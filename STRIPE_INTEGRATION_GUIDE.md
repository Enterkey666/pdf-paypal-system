
=== app.py への統合手順 ===

1. app.py の先頭付近（他のインポート文の後）に以下を追加:

```python
# Stripe統合のためのインポート
try:
    from stripe_flask_integration import register_stripe_blueprints, add_stripe_routes_to_existing_app
    STRIPE_INTEGRATION_AVAILABLE = True
    print("✓ Stripe統合モジュールのインポート成功")
except ImportError as e:
    print(f"⚠ Stripe統合モジュールのインポート失敗: {e}")
    STRIPE_INTEGRATION_AVAILABLE = False
```

2. app作成後（app = Flask(__name__) の後）に以下を追加:

```python
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
```

3. 利用可能なエンドポイント:
   - /api/stripe/test - Stripe機能テスト
   - /api/stripe/config/validate - 設定検証
   - /api/stripe/payment_link - Payment Link作成
   - /api/stripe/payment_link/from_ocr - OCRからPayment Link作成
   - /webhook/stripe - Stripe Webhook
   - /settings/test_stripe_connection - 接続テスト
   - /settings/save_stripe - 設定保存

4. フロントエンドでの使用:
   - 既存のpayment_utils.pyが拡張されているため、create_payment_link()で
     provider='stripe' を指定するだけでStripe決済リンクが作成可能
