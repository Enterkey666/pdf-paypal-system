#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
設定管理システムの検証・テストスクリプト
拡張されたStripe設定を含む包括的なテスト
"""

import os
import json
import logging
from typing import Dict, Any
from config_manager import ConfigManager

# ロガーの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_stripe_config_validation():
    """
    Stripe設定の検証テスト
    """
    print("=" * 50)
    print("Stripe設定検証テスト")
    print("=" * 50)
    
    config_manager = ConfigManager()
    
    # テストケース1: 正常なStripe設定
    test_config_valid = {
        'stripe_mode': 'test',
        'stripe_secret_key_test': 'sk_test_1234567890abcdef',
        'stripe_publishable_key_test': 'pk_test_1234567890abcdef',
        'stripe_webhook_secret': 'whsec_1234567890abcdef',
        'default_payment_provider': 'stripe',
        'enabled_payment_providers': ['stripe', 'paypal']
    }
    
    config_manager.config.update(test_config_valid)
    result = config_manager.validate_stripe_config()
    
    print(f"✓ 正常設定テスト: {'成功' if result['valid'] else '失敗'}")
    if result['errors']:
        print(f"  エラー: {result['errors']}")
    if result['warnings']:
        print(f"  警告: {result['warnings']}")
    
    # テストケース2: 不正なStripe設定
    test_config_invalid = {
        'stripe_mode': 'test',
        'stripe_secret_key_test': 'invalid_key',  # 不正な形式
        'stripe_publishable_key_test': 'pk_live_wrong_mode',  # モード不一致
        'default_payment_provider': 'stripe',
        'enabled_payment_providers': ['stripe']
    }
    
    config_manager.config.update(test_config_invalid)
    result = config_manager.validate_stripe_config()
    
    print(f"✓ 不正設定テスト: {'期待通り失敗' if not result['valid'] else '予期しない成功'}")
    if result['errors']:
        print(f"  エラー: {result['errors']}")

def test_payment_providers_status():
    """
    決済プロバイダーステータステスト
    """
    print("\\n" + "=" * 50)
    print("決済プロバイダーステータステスト")
    print("=" * 50)
    
    config_manager = ConfigManager()
    status = config_manager.get_payment_providers_status()
    
    print(f"デフォルトプロバイダー: {status['default_provider']}")
    print(f"有効プロバイダー: {status['enabled_providers']}")
    
    for provider_name, provider_info in status['providers'].items():
        print(f"\\n{provider_name.upper()}:")
        print(f"  設定済み: {'✓' if provider_info['configured'] else '✗'}")
        print(f"  接続可能: {'✓' if provider_info['connected'] else '✗'}")
        print(f"  モード: {provider_info['mode']}")

def test_config_schema_validation():
    """
    設定スキーマの包括的検証テスト
    """
    print("\\n" + "=" * 50)
    print("設定スキーマ包括検証テスト")
    print("=" * 50)
    
    config_manager = ConfigManager()
    
    # テスト用の設定
    test_config = {
        'paypal_client_id': 'test_paypal_id',
        'paypal_client_secret': 'test_paypal_secret',
        'paypal_mode': 'sandbox',
        'stripe_mode': 'test',
        'stripe_secret_key_test': 'sk_test_1234567890abcdef',
        'stripe_publishable_key_test': 'pk_test_1234567890abcdef',
        'default_payment_provider': 'stripe',
        'enabled_payment_providers': ['paypal', 'stripe'],
        'default_currency': 'JPY',
        'supported_currencies': ['JPY', 'USD']
    }
    
    result = config_manager.validate_config_schema(test_config)
    
    print(f"全体検証結果: {'✓ 成功' if result['valid'] else '✗ 失敗'}")
    
    for section_name, section_result in result['sections'].items():
        status = '✓' if section_result['valid'] else '✗'
        print(f"  {section_name}: {status}")
        
        if section_result['errors']:
            for error in section_result['errors']:
                print(f"    エラー: {error}")
        
        if section_result['warnings']:
            for warning in section_result['warnings']:
                print(f"    警告: {warning}")

def test_encryption_functionality():
    """
    暗号化機能のテスト
    """
    print("\\n" + "=" * 50)
    print("暗号化機能テスト")
    print("=" * 50)
    
    config_manager = ConfigManager()
    
    # テスト用のAPIキー
    test_api_key = "sk_test_1234567890abcdef"
    
    try:
        # 暗号化テスト
        encrypted_key = config_manager._encrypt_api_key(test_api_key)
        print(f"✓ 暗号化成功: {test_api_key[:10]}... -> {encrypted_key[:20]}...")
        
        # 復号化テスト
        decrypted_key = config_manager._decrypt_api_key(encrypted_key)
        if decrypted_key == test_api_key:
            print("✓ 復号化成功: 元のキーと一致")
        else:
            print("✗ 復号化失敗: 元のキーと不一致")
            
    except Exception as e:
        print(f"✗ 暗号化テストエラー: {str(e)}")

def test_import_export_functionality():
    """
    インポート/エクスポート機能のテスト
    """
    print("\\n" + "=" * 50)
    print("インポート/エクスポート機能テスト")
    print("=" * 50)
    
    config_manager = ConfigManager()
    
    # エクスポートテスト
    export_result = config_manager.export_config_with_encryption(
        export_path="test_export.json",
        include_sensitive=False
    )
    
    if export_result['success']:
        print(f"✓ エクスポート成功: {export_result['export_path']}")
        if export_result['excluded_fields']:
            print(f"  除外フィールド: {export_result['excluded_fields']}")
    else:
        print(f"✗ エクスポート失敗: {export_result['message']}")
        return
    
    # インポートテスト
    if os.path.exists("test_export.json"):
        import_result = config_manager.import_config_with_validation(
            import_path="test_export.json",
            validate_before_save=True
        )
        
        if import_result['success']:
            print(f"✓ インポート成功: {import_result['message']}")
            print(f"  インポート項目: {import_result['imported_fields']}")
        else:
            print(f"✗ インポート失敗: {import_result['message']}")
        
        # テストファイルを削除
        os.remove("test_export.json")
        print("✓ テストファイル削除完了")

def test_environment_variable_mapping():
    """
    環境変数マッピングのテスト
    """
    print("\\n" + "=" * 50)
    print("環境変数マッピングテスト")
    print("=" * 50)
    
    # テスト用環境変数を設定
    test_env_vars = {
        'STRIPE_MODE': 'test',
        'DEFAULT_PAYMENT_PROVIDER': 'stripe',
        'DEFAULT_CURRENCY': 'USD',
        'ENCRYPT_API_KEYS': 'true',
        'PAYMENT_LINK_EXPIRE_DAYS': '45'
    }
    
    # 一時的に環境変数を設定
    original_values = {}
    for key, value in test_env_vars.items():
        original_values[key] = os.environ.get(key)
        os.environ[key] = value
    
    try:
        # 新しいConfigManagerインスタンスを作成（環境変数を読み込む）
        config_manager = ConfigManager()
        
        # 環境変数が正しく反映されているかチェック
        checks = [
            ('stripe_mode', 'test'),
            ('default_payment_provider', 'stripe'),
            ('default_currency', 'USD'),
            ('encrypt_api_keys', True),
            ('payment_link_expire_days', 45)
        ]
        
        for config_key, expected_value in checks:
            actual_value = config_manager.config.get(config_key)
            if actual_value == expected_value:
                print(f"✓ {config_key}: {actual_value}")
            else:
                print(f"✗ {config_key}: 期待値 {expected_value}, 実際 {actual_value}")
    
    finally:
        # 環境変数を元に戻す
        for key, original_value in original_values.items():
            if original_value is None:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = original_value

def run_comprehensive_test():
    """
    包括的なテストスイートを実行
    """
    print("設定管理システム包括テスト開始")
    print("=" * 80)
    
    try:
        test_stripe_config_validation()
        test_payment_providers_status()
        test_config_schema_validation()
        test_encryption_functionality()
        test_import_export_functionality()
        test_environment_variable_mapping()
        
        print("\\n" + "=" * 80)
        print("✓ 全てのテストが完了しました")
        print("=" * 80)
        
    except Exception as e:
        print(f"\\n✗ テスト実行中にエラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_comprehensive_test()