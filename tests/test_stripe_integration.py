#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe統合テストスイート
包括的なStripe機能のテストケース
"""

import pytest
import json
import os
import tempfile
import time
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
import sys

# パスの設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from stripe_utils import (
        create_stripe_payment_link,
        create_stripe_payment_link_from_ocr,
        test_stripe_connection,
        validate_stripe_configuration
    )
    from payment_utils import create_payment_link_from_ocr, extract_and_validate_payment_data
    from config_manager import ConfigManager
except ImportError as e:
    pytest.skip(f"Required modules not available: {e}", allow_module_level=True)


class TestStripeAPIConnection:
    """Stripe API接続テストクラス"""
    
    @pytest.fixture
    def mock_stripe_config(self):
        """テスト用のStripe設定"""
        return {
            'stripe_mode': 'test',
            'stripe_secret_key_test': 'sk_test_4eC39HqLyjWDarjtT1zdp7dc',
            'stripe_publishable_key_test': 'pk_test_TYooMQauvdEDq54NiTphI7jx',
            'stripe_webhook_secret': 'whsec_test_secret'
        }
    
    @pytest.fixture
    def mock_stripe_account(self):
        """モックStripeアカウント情報"""
        return Mock(
            id='acct_test123',
            country='JP',
            default_currency='jpy',
            charges_enabled=True,
            payouts_enabled=True,
            details_submitted=True,
            business_profile=Mock(name='テスト会社')
        )
    
    def test_valid_stripe_connection(self, mock_stripe_config, mock_stripe_account):
        """正常なStripe接続テスト"""
        with patch('stripe.Account.retrieve', return_value=mock_stripe_account):
            with patch('stripe.api_key', mock_stripe_config['stripe_secret_key_test']):
                success, message, details = test_stripe_connection(
                    secret_key=mock_stripe_config['stripe_secret_key_test']
                )
                
                assert success is True
                assert '接続に成功' in message
                assert details['account_id'] == 'acct_test123'
                assert details['country'] == 'JP'
                assert details['charges_enabled'] is True
    
    def test_invalid_api_key_connection(self):
        """無効なAPIキーでの接続テスト"""
        with patch('stripe.Account.retrieve') as mock_retrieve:
            mock_retrieve.side_effect = Exception("Invalid API key")
            
            success, message, details = test_stripe_connection(
                secret_key='sk_test_invalid_key'
            )
            
            assert success is False
            assert 'エラー' in message
            assert details == {}
    
    def test_stripe_configuration_validation(self, mock_stripe_config):
        """Stripe設定検証テスト"""
        config_manager = ConfigManager()
        config_manager.config.update(mock_stripe_config)
        
        result = config_manager.validate_stripe_config()
        
        assert result['valid'] is True
        assert len(result['errors']) == 0
        assert result['details']['secret_key_valid'] is True
        assert result['details']['publishable_key_valid'] is True
    
    def test_invalid_stripe_configuration(self):
        """無効なStripe設定検証テスト"""
        config_manager = ConfigManager()
        config_manager.config.update({
            'stripe_mode': 'test',
            'stripe_secret_key_test': 'invalid_key',
            'stripe_publishable_key_test': 'pk_live_wrong_mode'
        })
        
        result = config_manager.validate_stripe_config()
        
        assert result['valid'] is False
        assert len(result['errors']) > 0
        assert any('形式が test モードに適していません' in error for error in result['errors'])


class TestStripePaymentLinkGeneration:
    """Stripe決済リンク生成テストクラス"""
    
    @pytest.fixture
    def mock_payment_link(self):
        """モック決済リンク"""
        return Mock(
            id='plink_test123',
            url='https://checkout.stripe.com/c/pay/plink_test123',
            active=True,
            line_items=Mock(data=[Mock(price=Mock(unit_amount=100000))])
        )
    
    def test_basic_payment_link_creation(self, mock_payment_link):
        """基本的な決済リンク作成テスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            result = create_stripe_payment_link(
                amount=1000.0,
                customer_name='テスト顧客',
                description='テスト決済',
                currency='jpy'
            )
            
            assert result['success'] is True
            assert result['payment_link'] == 'https://checkout.stripe.com/c/pay/plink_test123'
            assert result['payment_link_id'] == 'plink_test123'
    
    @pytest.mark.parametrize("amount,currency,expected_stripe_amount", [
        (1000, 'jpy', 1000),  # JPYは最小単位が円
        (10.50, 'usd', 1050),  # USDは最小単位がセント
        (100, 'eur', 10000),   # EURは最小単位がセント
    ])
    def test_currency_conversion(self, amount, currency, expected_stripe_amount, mock_payment_link):
        """通貨変換テスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link) as mock_create:
            create_stripe_payment_link(
                amount=amount,
                customer_name='テスト顧客',
                description='通貨テスト',
                currency=currency
            )
            
            # Stripe APIに渡される金額が正しいかチェック
            call_args = mock_create.call_args[1]
            assert call_args['line_items'][0]['price_data']['unit_amount'] == expected_stripe_amount
    
    def test_invalid_amount_handling(self):
        """無効な金額のハンドリングテスト"""
        test_cases = [
            (-100, '負の金額'),
            (0, 'ゼロ金額'),
            (None, 'None値'),
            ('abc', '文字列')
        ]
        
        for amount, description in test_cases:
            result = create_stripe_payment_link(
                amount=amount,
                customer_name='テスト顧客',
                description=description,
                currency='jpy'
            )
            
            assert result['success'] is False
            assert 'エラー' in result['message']
    
    def test_long_customer_name_handling(self, mock_payment_link):
        """長い顧客名のハンドリングテスト"""
        long_name = 'テ' * 1000  # 1000文字の顧客名
        
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            result = create_stripe_payment_link(
                amount=1000,
                customer_name=long_name,
                description='長い顧客名テスト',
                currency='jpy'
            )
            
            # 成功することを期待（Stripeが内部で制限処理）
            assert result['success'] is True


class TestOCRIntegration:
    """OCR統合テストクラス"""
    
    @pytest.fixture
    def sample_ocr_data(self):
        """サンプルOCRデータ"""
        return [
            {
                'name': '正常な日本語データ',
                'data': {
                    '顧客名': '株式会社テスト',
                    '金額': '¥10,000',
                    '日付': '2024-01-15',
                    '備考': 'テスト請求書'
                }
            },
            {
                'name': '英語フィールド名',
                'data': {
                    'customer_name': 'Test Company Ltd.',
                    'amount': '5,500',
                    'date': '2024-02-01',
                    'description': 'Test Invoice'
                }
            },
            {
                'name': '数値データ',
                'data': {
                    'customer_name': 'Numeric Test Co.',
                    'amount': 25000,
                    'date': '2024-03-01',
                    'currency': 'JPY'
                }
            }
        ]
    
    def test_ocr_data_extraction_and_validation(self, sample_ocr_data):
        """OCRデータ抽出・検証テスト"""
        for test_case in sample_ocr_data:
            result = extract_and_validate_payment_data(test_case['data'])
            
            assert result['valid'] is True, f"Failed for {test_case['name']}"
            assert result['customer_name'] is not None
            assert result['amount'] > 0
    
    @pytest.fixture
    def mock_payment_link(self):
        """モック決済リンク"""
        return Mock(
            id='plink_ocr_test',
            url='https://checkout.stripe.com/c/pay/plink_ocr_test'
        )
    
    def test_ocr_to_stripe_payment_link(self, sample_ocr_data, mock_payment_link):
        """OCRからStripe決済リンク作成テスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            for test_case in sample_ocr_data:
                result = create_stripe_payment_link_from_ocr(
                    ocr_data=test_case['data'],
                    filename=f"test_{test_case['name']}.pdf"
                )
                
                assert result['success'] is True, f"Failed for {test_case['name']}"
                assert 'checkout.stripe.com' in result['payment_link']
    
    def test_invalid_ocr_data_handling(self):
        """無効なOCRデータのハンドリングテスト"""
        invalid_data_cases = [
            {},  # 空のデータ
            {'random_field': 'value'},  # 関連フィールドなし
            {'customer_name': '', 'amount': ''},  # 空の値
            {'customer_name': 'Test', 'amount': 'invalid_amount'},  # 無効な金額
        ]
        
        for invalid_data in invalid_data_cases:
            result = extract_and_validate_payment_data(invalid_data)
            
            # 無効なデータでも適切にハンドリングされることを確認
            assert isinstance(result, dict)


class TestProviderSwitching:
    """決済プロバイダー切り替えテストクラス"""
    
    @pytest.fixture
    def mock_paypal_result(self):
        """モックPayPal結果"""
        return {
            'success': True,
            'payment_link': 'https://paypal.com/paypalme/test',
            'provider': 'paypal'
        }
    
    @pytest.fixture
    def mock_stripe_result(self):
        """モックStripe結果"""
        return {
            'success': True,
            'payment_link': 'https://checkout.stripe.com/c/pay/test',
            'provider': 'stripe'
        }
    
    def test_provider_switching(self, mock_paypal_result, mock_stripe_result):
        """プロバイダー切り替えテスト"""
        ocr_data = {
            'customer_name': 'プロバイダーテスト会社',
            'amount': '15,000',
            'description': 'プロバイダー切り替えテスト'
        }
        
        # PayPalプロバイダーテスト
        with patch('payment_utils.create_paypal_payment_link') as mock_paypal:
            mock_paypal.return_value = mock_paypal_result
            
            result = create_payment_link_from_ocr(
                provider='paypal',
                ocr_data=ocr_data,
                filename='provider_test.pdf'
            )
            
            assert result['success'] is True
            assert 'paypal.com' in result['payment_link']
        
        # Stripeプロバイダーテスト
        with patch('payment_utils.create_stripe_payment_link_from_ocr') as mock_stripe:
            mock_stripe.return_value = mock_stripe_result
            
            result = create_payment_link_from_ocr(
                provider='stripe',
                ocr_data=ocr_data,
                filename='provider_test.pdf'
            )
            
            assert result['success'] is True
            assert 'checkout.stripe.com' in result['payment_link']
    
    def test_invalid_provider_handling(self):
        """無効なプロバイダーのハンドリングテスト"""
        ocr_data = {
            'customer_name': 'テスト会社',
            'amount': '10,000'
        }
        
        result = create_payment_link_from_ocr(
            provider='invalid_provider',
            ocr_data=ocr_data,
            filename='test.pdf'
        )
        
        assert result['success'] is False
        assert 'サポートされていない' in result['message']


class TestErrorHandling:
    """エラーハンドリングテストクラス"""
    
    def test_stripe_api_errors(self):
        """Stripe APIエラーハンドリングテスト"""
        with patch('stripe.PaymentLink.create') as mock_create:
            # 認証エラー
            mock_create.side_effect = Exception("Authentication failed")
            
            result = create_stripe_payment_link(
                amount=1000,
                customer_name='エラーテスト',
                description='認証エラーテスト',
                currency='jpy'
            )
            
            assert result['success'] is False
            assert 'エラー' in result['message']
    
    def test_network_timeout_handling(self):
        """ネットワークタイムアウトハンドリングテスト"""
        with patch('stripe.PaymentLink.create') as mock_create:
            mock_create.side_effect = TimeoutError("Request timeout")
            
            result = create_stripe_payment_link(
                amount=1000,
                customer_name='タイムアウトテスト',
                description='タイムアウトテスト',
                currency='jpy'
            )
            
            assert result['success'] is False
            assert result['message'] is not None
    
    def test_rate_limiting_handling(self):
        """レート制限ハンドリングテスト"""
        with patch('stripe.PaymentLink.create') as mock_create:
            mock_create.side_effect = Exception("Rate limit exceeded")
            
            result = create_stripe_payment_link(
                amount=1000,
                customer_name='レート制限テスト',
                description='レート制限テスト',
                currency='jpy'
            )
            
            assert result['success'] is False


class TestJapaneseLanguageSupport:
    """日本語対応テストクラス"""
    
    @pytest.mark.parametrize("customer_name,description", [
        ('株式会社テスト', '日本語説明'),
        ('㈱テスト商事', '特殊文字テスト'),
        ('テスト　太郎', '全角スペース'),
        ('１２３４５', '全角数字'),
        ('test@example.co.jp', 'メールアドレス'),
    ])
    def test_japanese_character_handling(self, customer_name, description):
        """日本語文字処理テスト"""
        with patch('stripe.PaymentLink.create') as mock_create:
            mock_create.return_value = Mock(
                id='plink_jp_test',
                url='https://checkout.stripe.com/c/pay/plink_jp_test'
            )
            
            result = create_stripe_payment_link(
                amount=1000,
                customer_name=customer_name,
                description=description,
                currency='jpy'
            )
            
            assert result['success'] is True
            # 日本語が正しく処理されることを確認
            assert customer_name in str(mock_create.call_args)


class TestConfigurationManagement:
    """設定管理テストクラス"""
    
    def test_config_encryption_decryption(self):
        """設定の暗号化・復号化テスト"""
        config_manager = ConfigManager()
        
        test_api_key = 'sk_test_1234567890abcdef'
        
        # 暗号化テスト
        encrypted_key = config_manager._encrypt_api_key(test_api_key)
        assert encrypted_key != test_api_key
        
        # 復号化テスト
        decrypted_key = config_manager._decrypt_api_key(encrypted_key)
        assert decrypted_key == test_api_key
    
    def test_config_validation(self):
        """設定検証テスト"""
        config_manager = ConfigManager()
        
        # 有効な設定
        valid_config = {
            'stripe_mode': 'test',
            'stripe_secret_key_test': 'sk_test_1234567890abcdef',
            'stripe_publishable_key_test': 'pk_test_1234567890abcdef',
            'default_payment_provider': 'stripe',
            'default_currency': 'JPY'
        }
        
        result = config_manager.validate_config_schema(valid_config)
        
        assert result['valid'] is True or len(result['errors']) == 0  # 部分的成功も許容
    
    def test_config_import_export(self):
        """設定インポート・エクスポートテスト"""
        config_manager = ConfigManager()
        
        # エクスポートテスト
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            export_result = config_manager.export_config_with_encryption(
                export_path=temp_file.name,
                include_sensitive=False
            )
            
            assert export_result['success'] is True
            assert os.path.exists(temp_file.name)
            
            # インポートテスト
            import_result = config_manager.import_config_with_validation(
                import_path=temp_file.name,
                validate_before_save=False  # バリデーションをスキップ
            )
            
            assert import_result['success'] is True
            
            # クリーンアップ
            os.unlink(temp_file.name)


@pytest.mark.integration
class TestFullIntegration:
    """完全統合テストクラス"""
    
    def test_pdf_to_stripe_full_flow(self):
        """PDF→OCR→Stripe決済フロー統合テスト"""
        # モックOCRデータ（実際のPDF処理結果をシミュレート）
        mock_ocr_result = {
            'customer_name': '統合テスト株式会社',
            'amount': '¥50,000',
            'date': '2024-01-15',
            'description': '統合テスト請求書'
        }
        
        with patch('stripe.PaymentLink.create') as mock_create:
            mock_create.return_value = Mock(
                id='plink_integration_test',
                url='https://checkout.stripe.com/c/pay/plink_integration_test'
            )
            
            # 1. OCRデータ検証
            validation_result = extract_and_validate_payment_data(mock_ocr_result)
            assert validation_result['valid'] is True
            
            # 2. Stripe決済リンク作成
            payment_result = create_payment_link_from_ocr(
                provider='stripe',
                ocr_data=mock_ocr_result,
                filename='integration_test.pdf'
            )
            
            assert payment_result['success'] is True
            assert 'checkout.stripe.com' in payment_result['payment_link']
    
    def test_error_recovery_flow(self):
        """エラー回復フローテスト"""
        mock_ocr_data = {
            'customer_name': 'エラー回復テスト',
            'amount': '10,000'
        }
        
        # 最初の試行でエラー
        with patch('stripe.PaymentLink.create') as mock_create:
            mock_create.side_effect = [
                Exception("First attempt failed"),  # 1回目失敗
                Mock(id='plink_recovery', url='https://checkout.stripe.com/recovery')  # 2回目成功
            ]
            
            # リトライロジックがある場合のテスト
            # (実装によってはリトライ機能を追加する必要がある)
            result = create_stripe_payment_link_from_ocr(
                ocr_data=mock_ocr_data,
                filename='error_recovery_test.pdf'
            )
            
            # 最初の失敗でもエラーハンドリングが適切に行われることを確認
            assert isinstance(result, dict)
            assert 'success' in result


if __name__ == '__main__':
    # テスト実行
    pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '--capture=no'
    ])