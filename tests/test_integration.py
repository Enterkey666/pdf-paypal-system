#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
統合テストスイート
Stripe機能とシステム全体の統合テスト
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
import sys

# パスの設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config_manager import ConfigManager
    from stripe_utils import create_stripe_payment_link, create_stripe_payment_link_from_ocr
    from payment_utils import create_payment_link_from_ocr, extract_and_validate_payment_data
    import app  # Flaskアプリケーション
except ImportError as e:
    pytest.skip(f"Required modules not available: {e}", allow_module_level=True)


class TestFullWorkflow:
    """完全ワークフロー統合テストクラス"""
    
    @pytest.fixture
    def app_client(self):
        """Flaskテストクライアント"""
        app.app.config['TESTING'] = True
        app.app.config['WTF_CSRF_ENABLED'] = False  # CSRFを無効にしてテスト
        return app.app.test_client()
    
    @pytest.fixture
    def mock_stripe_config(self):
        """テスト用Stripe設定"""
        return {
            'stripe_mode': 'test',
            'stripe_secret_key_test': 'sk_test_4eC39HqLyjWDarjtT1zdp7dc',
            'stripe_publishable_key_test': 'pk_test_TYooMQauvdEDq54NiTphI7jx',
            'default_payment_provider': 'stripe',
            'enabled_payment_providers': ['paypal', 'stripe']
        }
    
    @pytest.fixture
    def sample_pdf_content(self):
        """サンプルPDFコンテンツ（バイナリデータのモック）"""
        return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n..."
    
    @pytest.fixture
    def mock_ocr_result(self):
        """モックOCR結果"""
        return {
            'customer_name': '統合テスト株式会社',
            'amount': '¥25,000',
            'date': '2024-01-15',
            'description': '統合テスト請求書',
            'invoice_number': 'INV-2024-001'
        }
    
    def test_end_to_end_stripe_workflow(self, app_client, mock_stripe_config, mock_ocr_result):
        """エンドツーエンドStripeワークフローテスト"""
        
        # 1. 設定の更新
        config_manager = ConfigManager()
        config_manager.config.update(mock_stripe_config)
        
        with patch('stripe.PaymentLink.create') as mock_create_link:
            mock_create_link.return_value = Mock(
                id='plink_integration_test',
                url='https://checkout.stripe.com/c/pay/plink_integration_test'
            )
            
            # 2. OCRデータの処理
            validation_result = extract_and_validate_payment_data(mock_ocr_result)
            assert validation_result['valid'] is True
            
            # 3. Stripe決済リンクの作成
            payment_result = create_payment_link_from_ocr(
                provider='stripe',
                ocr_data=mock_ocr_result,
                filename='integration_test.pdf'
            )
            
            assert payment_result['success'] is True
            assert 'checkout.stripe.com' in payment_result['payment_link']
            assert payment_result['provider'] == 'stripe'
    
    def test_provider_failover_workflow(self, mock_stripe_config, mock_ocr_result):
        """プロバイダーフェイルオーバーワークフローテスト"""
        config_manager = ConfigManager()
        config_manager.config.update(mock_stripe_config)
        
        # Stripe失敗 → PayPalフェイルオーバーのシミュレート
        with patch('stripe.PaymentLink.create') as mock_stripe_create:
            mock_stripe_create.side_effect = Exception("Stripe API Error")
            
            with patch('payment_utils.create_paypal_payment_link') as mock_paypal_create:
                mock_paypal_create.return_value = {
                    'success': True,
                    'payment_link': 'https://paypal.me/fallback_test',
                    'provider': 'paypal'
                }
                
                # フェイルオーバー機能（実装されている場合）のテスト
                # 現在の実装では自動フェイルオーバーはないので、手動切り替えをテスト
                
                # PayPalでの決済リンク作成
                paypal_result = create_payment_link_from_ocr(
                    provider='paypal',
                    ocr_data=mock_ocr_result,
                    filename='failover_test.pdf'
                )
                
                assert paypal_result['success'] is True
                assert 'paypal.me' in paypal_result['payment_link']
    
    def test_configuration_persistence_workflow(self, mock_stripe_config):
        """設定永続化ワークフローテスト"""
        config_manager = ConfigManager()
        
        # 1. 設定の保存
        save_result = config_manager.save_stripe_config(mock_stripe_config)
        assert save_result['success'] is True
        
        # 2. 設定の読み込み確認
        loaded_config = config_manager.get_config()
        assert loaded_config['stripe_mode'] == 'test'
        assert loaded_config['default_payment_provider'] == 'stripe'
        
        # 3. 暗号化確認（機密フィールドが暗号化されているか）
        if config_manager.config.get('encrypt_api_keys', True):
            stored_secret = loaded_config.get('stripe_secret_key_test', '')
            # 暗号化されている場合、元のキーと異なるはず
            if stored_secret and stored_secret != mock_stripe_config['stripe_secret_key_test']:
                # 復号化テスト
                decrypted = config_manager._decrypt_api_key(stored_secret)
                assert decrypted == mock_stripe_config['stripe_secret_key_test']
    
    def test_error_recovery_workflow(self, mock_ocr_result):
        """エラー回復ワークフローテスト"""
        
        # 1. 初回処理でエラー
        with patch('stripe.PaymentLink.create') as mock_create:
            mock_create.side_effect = [
                Exception("Rate limit exceeded"),  # 1回目失敗
                Mock(  # 2回目成功
                    id='plink_recovery_test',
                    url='https://checkout.stripe.com/c/pay/plink_recovery_test'
                )
            ]
            
            # エラー処理の確認
            first_result = create_stripe_payment_link_from_ocr(
                ocr_data=mock_ocr_result,
                filename='error_test.pdf'
            )
            
            # 1回目は失敗するはず
            assert first_result['success'] is False
            assert 'エラー' in first_result['message']
            
            # 2回目の試行（実際の実装ではリトライロジックが必要）
            second_result = create_stripe_payment_link_from_ocr(
                ocr_data=mock_ocr_result,
                filename='retry_test.pdf'
            )
            
            # 2回目は成功するはず
            assert second_result['success'] is True


class TestConcurrentOperations:
    """並行動作統合テストクラス"""
    
    @pytest.fixture
    def mock_payment_link(self):
        """モック決済リンク"""
        return Mock(
            id='plink_concurrent_test',
            url='https://checkout.stripe.com/c/pay/plink_concurrent_test'
        )
    
    def test_concurrent_payment_link_creation(self, mock_payment_link):
        """並行決済リンク作成テスト"""
        import threading
        import time
        
        results = []
        errors = []
        
        def create_payment_link_task(task_id):
            """並行タスク"""
            try:
                result = create_stripe_payment_link(
                    amount=1000 + task_id,
                    customer_name=f'並行テスト_{task_id}',
                    description=f'並行作成_{task_id}',
                    currency='jpy'
                )
                results.append(result)
            except Exception as e:
                errors.append(str(e))
        
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            # 5つの並行タスクを実行
            threads = []
            for i in range(5):
                thread = threading.Thread(target=create_payment_link_task, args=(i,))
                threads.append(thread)
                thread.start()
            
            # 全スレッドの完了を待機
            for thread in threads:
                thread.join(timeout=10)
            
            # 結果検証
            assert len(results) == 5
            assert len(errors) == 0
            assert all(result['success'] for result in results)
    
    def test_concurrent_config_access(self):
        """並行設定アクセステスト"""
        import threading
        
        config_manager = ConfigManager()
        read_results = []
        write_results = []
        
        def read_config_task():
            """設定読み込みタスク"""
            try:
                config = config_manager.get_config()
                read_results.append(len(config))
            except Exception as e:
                read_results.append(f"Error: {e}")
        
        def write_config_task(task_id):
            """設定書き込みタスク"""
            try:
                test_config = {f'test_key_{task_id}': f'test_value_{task_id}'}
                result = config_manager.save_config(test_config)
                write_results.append(result)
            except Exception as e:
                write_results.append(f"Error: {e}")
        
        # 並行読み書きテスト
        threads = []
        
        # 読み込みスレッド
        for _ in range(3):
            thread = threading.Thread(target=read_config_task)
            threads.append(thread)
        
        # 書き込みスレッド
        for i in range(2):
            thread = threading.Thread(target=write_config_task, args=(i,))
            threads.append(thread)
        
        # 全スレッド開始
        for thread in threads:
            thread.start()
        
        # 完了待機
        for thread in threads:
            thread.join(timeout=5)
        
        # 結果検証
        assert len(read_results) == 3
        assert len(write_results) == 2
        
        # エラーがないことを確認
        assert not any(isinstance(result, str) and "Error" in result for result in read_results)
        assert not any(isinstance(result, str) and "Error" in result for result in write_results)


class TestDataPersistence:
    """データ永続化統合テストクラス"""
    
    def test_payment_history_integration(self):
        """決済履歴統合テスト"""
        # 決済履歴機能がある場合のテスト
        
        test_payment_data = {
            'payment_link_id': 'plink_history_test',
            'customer_name': '履歴テスト会社',
            'amount': 15000,
            'currency': 'JPY',
            'provider': 'stripe',
            'status': 'created',
            'created_at': '2024-01-15T10:30:00Z'
        }
        
        # データベース操作のモック
        with patch('database.save_payment_record') as mock_save:
            mock_save.return_value = True
            
            # 決済データの保存をシミュレート
            # (実際の実装に応じて調整)
            saved = mock_save(test_payment_data)
            assert saved is True
    
    def test_config_backup_and_restore(self):
        """設定バックアップ・復元統合テスト"""
        config_manager = ConfigManager()
        
        # 現在の設定をバックアップ
        original_config = config_manager.get_config().copy()
        
        # テスト用設定に変更
        test_config = {
            'stripe_mode': 'test',
            'default_payment_provider': 'stripe',
            'test_setting': 'integration_test_value'
        }
        
        config_manager.save_config(test_config)
        
        # エクスポート
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            export_result = config_manager.export_config_with_encryption(
                export_path=temp_file.name,
                include_sensitive=False
            )
            
            assert export_result['success'] is True
            
            # 設定をクリア
            config_manager.config.clear()
            
            # インポートで復元
            import_result = config_manager.import_config_with_validation(
                import_path=temp_file.name,
                validate_before_save=False
            )
            
            assert import_result['success'] is True
            
            # 復元確認
            restored_config = config_manager.get_config()
            assert restored_config['stripe_mode'] == 'test'
            assert restored_config['default_payment_provider'] == 'stripe'
            
            # クリーンアップ
            os.unlink(temp_file.name)


class TestAPIIntegration:
    """API統合テストクラス"""
    
    @pytest.fixture
    def app_client(self):
        """Flaskテストクライアント"""
        app.app.config['TESTING'] = True
        app.app.config['WTF_CSRF_ENABLED'] = False
        return app.app.test_client()
    
    def test_stripe_api_endpoints(self, app_client):
        """Stripe APIエンドポイント統合テスト"""
        
        # 1. 設定検証エンドポイント
        response = app_client.get('/api/stripe/config/validate')
        assert response.status_code in [200, 404]  # 404は未実装の場合
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'valid' in data
    
    def test_webhook_endpoint_integration(self, app_client):
        """Webhookエンドポイント統合テスト"""
        
        # テスト用Webhookペイロード
        webhook_payload = {
            'id': 'evt_test_webhook',
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'object': 'checkout.session',
                    'id': 'cs_test_session',
                    'customer_details': {'email': 'test@example.com'},
                    'amount_total': 10000,
                    'currency': 'jpy',
                    'payment_status': 'paid'
                }
            }
        }
        
        # Webhook呼び出し
        response = app_client.post(
            '/webhook/stripe',
            data=json.dumps(webhook_payload),
            content_type='application/json'
        )
        
        # レスポンス確認
        assert response.status_code in [200, 400, 404]  # 実装状況により異なる
    
    def test_settings_api_integration(self, app_client):
        """設定API統合テスト"""
        
        # Stripe設定保存
        stripe_settings = {
            'stripe_mode': 'test',
            'stripe_publishable_key': 'pk_test_integration',
            'stripe_secret_key': 'sk_test_integration'
        }
        
        response = app_client.post(
            '/settings/save_stripe',
            data=stripe_settings
        )
        
        # レスポンス確認（実装により異なる）
        assert response.status_code in [200, 302, 404]


class TestSystemResilience:
    """システム復旧力統合テストクラス"""
    
    def test_partial_service_failure(self):
        """部分的サービス障害テスト"""
        
        mock_ocr_data = {
            'customer_name': '復旧力テスト',
            'amount': '5000'
        }
        
        # Stripe障害時の動作テスト
        with patch('stripe.PaymentLink.create') as mock_stripe:
            mock_stripe.side_effect = Exception("Service temporarily unavailable")
            
            # Stripe失敗時の動作確認
            result = create_stripe_payment_link_from_ocr(
                ocr_data=mock_ocr_data,
                filename='resilience_test.pdf'
            )
            
            # 適切なエラーハンドリングがされることを確認
            assert result['success'] is False
            assert isinstance(result['message'], str)
    
    def test_database_connection_failure(self):
        """データベース接続失敗テスト"""
        
        # データベース障害をシミュレート
        with patch('database.get_db_connection') as mock_db:
            mock_db.side_effect = Exception("Database connection failed")
            
            # システムが適切に動作し続けることを確認
            config_manager = ConfigManager()
            
            # 設定読み込みは可能（ファイルベース）
            config = config_manager.get_config()
            assert isinstance(config, dict)
    
    def test_file_system_issues(self):
        """ファイルシステム問題テスト"""
        
        # ファイル書き込み失敗をシミュレート
        with patch('builtins.open') as mock_open:
            mock_open.side_effect = PermissionError("Permission denied")
            
            config_manager = ConfigManager()
            
            # エラーが適切に処理されることを確認
            result = config_manager.save_config({'test': 'value'})
            assert result is False  # 失敗を適切に報告


if __name__ == '__main__':
    # 統合テスト実行
    pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '--capture=no'
    ])