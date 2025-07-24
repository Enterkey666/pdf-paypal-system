#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe統合セットアップスクリプト
Flask アプリケーションにStripe機能を統合するためのセットアップ
"""

import os
import sys
import logging
from typing import Dict, Any

# ロガーの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_dependencies() -> Dict[str, bool]:
    """
    必要な依存関係をチェック
    
    Returns:
        Dict[str, bool]: 依存関係チェック結果
    """
    dependencies = {}
    
    try:
        import stripe
        dependencies['stripe'] = True
        logger.info(f"✓ stripe ライブラリ: v{stripe.VERSION}")
    except ImportError:
        dependencies['stripe'] = False
        logger.error("✗ stripe ライブラリが見つかりません")
    
    try:
        import flask
        dependencies['flask'] = True
        logger.info(f"✓ Flask: v{flask.__version__}")
    except ImportError:
        dependencies['flask'] = False
        logger.error("✗ Flask が見つかりません")
    
    # 必要なファイルの存在チェック
    required_files = [
        'stripe_utils.py',
        'stripe_webhook.py', 
        'stripe_routes.py',
        'stripe_flask_integration.py',
        'payment_utils.py',
        'provider_api_routes.py'
    ]
    
    for filename in required_files:
        if os.path.exists(filename):
            dependencies[filename] = True
            logger.info(f"✓ {filename}")
        else:
            dependencies[filename] = False
            logger.error(f"✗ {filename} が見つかりません")
    
    return dependencies

def install_missing_dependencies():
    """
    不足している依存関係をインストール
    """
    try:
        import subprocess
        
        logger.info("Stripe ライブラリをインストール中...")
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', 'stripe==7.0.0'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✓ Stripe ライブラリのインストール完了")
        else:
            logger.error(f"✗ Stripe ライブラリのインストール失敗: {result.stderr}")
            
    except Exception as e:
        logger.error(f"依存関係インストールエラー: {str(e)}")

def setup_environment_file():
    """
    環境変数ファイルのセットアップ
    """
    try:
        env_file = '.env'
        example_file = '.env.stripe.example'
        
        if not os.path.exists(env_file):
            if os.path.exists(example_file):
                logger.info(f"{example_file} から {env_file} を作成中...")
                with open(example_file, 'r', encoding='utf-8') as src:
                    content = src.read()
                
                with open(env_file, 'w', encoding='utf-8') as dst:
                    dst.write(content)
                
                logger.info(f"✓ {env_file} を作成しました")
                logger.warning(f"⚠ {env_file} を編集してStripe APIキーを設定してください")
            else:
                logger.warning(f"⚠ {example_file} が見つかりません")
        else:
            logger.info(f"✓ {env_file} は既に存在します")
            
    except Exception as e:
        logger.error(f"環境変数ファイルセットアップエラー: {str(e)}")

def validate_stripe_configuration():
    """
    Stripe設定の検証
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        stripe_secret_key = os.environ.get('STRIPE_SECRET_KEY', '')
        stripe_publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
        stripe_mode = os.environ.get('STRIPE_MODE', 'test')
        
        logger.info("Stripe設定検証中...")
        
        if not stripe_secret_key:
            logger.warning("⚠ STRIPE_SECRET_KEY が設定されていません")
        elif stripe_mode == 'test' and stripe_secret_key.startswith('sk_test_'):
            logger.info("✓ テスト用Secret Key が正しく設定されています")
        elif stripe_mode == 'live' and stripe_secret_key.startswith('sk_live_'):
            logger.info("✓ 本番用Secret Key が正しく設定されています")
        else:
            logger.warning(f"⚠ Secret Key の形式が {stripe_mode} モードに適していません")
        
        if not stripe_publishable_key:
            logger.warning("⚠ STRIPE_PUBLISHABLE_KEY が設定されていません")
        elif stripe_mode == 'test' and stripe_publishable_key.startswith('pk_test_'):
            logger.info("✓ テスト用Publishable Key が正しく設定されています")
        elif stripe_mode == 'live' and stripe_publishable_key.startswith('pk_live_'):
            logger.info("✓ 本番用Publishable Key が正しく設定されています")
        else:
            logger.warning(f"⚠ Publishable Key の形式が {stripe_mode} モードに適していません")
        
        # 接続テスト
        if stripe_secret_key:
            logger.info("Stripe API接続テスト中...")
            try:
                from stripe_utils import test_stripe_connection
                result = test_stripe_connection(stripe_secret_key)
                
                if result.get('success'):
                    logger.info("✓ Stripe API接続テスト成功")
                else:
                    logger.error(f"✗ Stripe API接続テスト失敗: {result.get('message')}")
            except Exception as e:
                logger.error(f"✗ Stripe API接続テストエラー: {str(e)}")
                
    except Exception as e:
        logger.error(f"Stripe設定検証エラー: {str(e)}")

def generate_integration_instructions():
    """
    app.py統合の手順を生成
    """
    instructions = """
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
"""
    
    print(instructions)
    
    # ファイルとしても保存
    with open('STRIPE_INTEGRATION_GUIDE.md', 'w', encoding='utf-8') as f:
        f.write(instructions)
    
    logger.info("✓ 統合手順を STRIPE_INTEGRATION_GUIDE.md に保存しました")

def main():
    """
    メイン実行関数
    """
    logger.info("=== Stripe統合セットアップ開始 ===")
    
    # 1. 依存関係チェック
    logger.info("1. 依存関係をチェック中...")
    dependencies = check_dependencies()
    
    # 2. 不足している依存関係をインストール
    if not dependencies.get('stripe', False):
        logger.info("2. 不足している依存関係をインストール中...")
        install_missing_dependencies()
    
    # 3. 環境変数ファイルのセットアップ
    logger.info("3. 環境変数ファイルをセットアップ中...")
    setup_environment_file()
    
    # 4. Stripe設定の検証
    logger.info("4. Stripe設定を検証中...")
    validate_stripe_configuration()
    
    # 5. 統合手順の生成
    logger.info("5. 統合手順を生成中...")
    generate_integration_instructions()
    
    logger.info("=== Stripe統合セットアップ完了 ===")
    
    print("\n次の手順:")
    print("1. .env ファイルを編集してStripe APIキーを設定")
    print("2. STRIPE_INTEGRATION_GUIDE.md の手順に従ってapp.pyを修正")
    print("3. アプリケーションを再起動")
    print("4. /api/stripe/test でテスト実行")

if __name__ == '__main__':
    main()