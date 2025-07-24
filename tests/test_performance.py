#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
パフォーマンステストスイート
Stripe機能の性能測定とスケーラビリティテスト
"""

import pytest
import time
import threading
import concurrent.futures
from unittest.mock import Mock, patch
import statistics
import sys
import os

# パスの設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from stripe_utils import create_stripe_payment_link, create_stripe_payment_link_from_ocr
    from payment_utils import create_payment_link_from_ocr, extract_and_validate_payment_data
    from config_manager import ConfigManager
except ImportError as e:
    pytest.skip(f"Required modules not available: {e}", allow_module_level=True)


class TestPerformance:
    """パフォーマンステストクラス"""
    
    @pytest.fixture
    def mock_payment_link(self):
        """モック決済リンク"""
        return Mock(
            id='plink_perf_test',
            url='https://checkout.stripe.com/c/pay/plink_perf_test'
        )
    
    def test_single_payment_link_creation_time(self, mock_payment_link):
        """単一決済リンク作成時間テスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            start_time = time.time()
            
            result = create_stripe_payment_link(
                amount=1000,
                customer_name='パフォーマンステスト',
                description='処理時間測定',
                currency='jpy'
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            assert result['success'] is True
            assert processing_time < 1.0  # 1秒以内で完了すること
            print(f"処理時間: {processing_time:.3f}秒")
    
    def test_multiple_sequential_requests(self, mock_payment_link):
        """連続複数リクエストテスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            request_count = 10
            processing_times = []
            
            for i in range(request_count):
                start_time = time.time()
                
                result = create_stripe_payment_link(
                    amount=1000 + i,
                    customer_name=f'パフォーマンステスト_{i}',
                    description=f'連続テスト_{i}',
                    currency='jpy'
                )
                
                end_time = time.time()
                processing_time = end_time - start_time
                processing_times.append(processing_time)
                
                assert result['success'] is True
            
            # 統計情報
            avg_time = statistics.mean(processing_times)
            max_time = max(processing_times)
            min_time = min(processing_times)
            
            print(f"\\n連続{request_count}リクエスト統計:")
            print(f"平均処理時間: {avg_time:.3f}秒")
            print(f"最大処理時間: {max_time:.3f}秒")
            print(f"最小処理時間: {min_time:.3f}秒")
            
            # パフォーマンス基準
            assert avg_time < 0.5  # 平均500ms以内
            assert max_time < 2.0  # 最大2秒以内
    
    def test_concurrent_requests(self, mock_payment_link):
        """同時並行リクエストテスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            concurrent_count = 5
            
            def create_payment_link_task(task_id):
                """並行タスク"""
                start_time = time.time()
                
                result = create_stripe_payment_link(
                    amount=2000 + task_id,
                    customer_name=f'並行テスト_{task_id}',
                    description=f'並行処理テスト_{task_id}',
                    currency='jpy'
                )
                
                end_time = time.time()
                return {
                    'task_id': task_id,
                    'success': result['success'],
                    'processing_time': end_time - start_time
                }
            
            # 並行実行
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_count) as executor:
                start_time = time.time()
                
                futures = [
                    executor.submit(create_payment_link_task, i) 
                    for i in range(concurrent_count)
                ]
                
                results = [future.result() for future in concurrent.futures.as_completed(futures)]
                
                total_time = time.time() - start_time
            
            # 結果検証
            assert len(results) == concurrent_count
            assert all(result['success'] for result in results)
            
            processing_times = [result['processing_time'] for result in results]
            avg_time = statistics.mean(processing_times)
            
            print(f"\\n並行{concurrent_count}リクエスト結果:")
            print(f"総実行時間: {total_time:.3f}秒")
            print(f"平均処理時間: {avg_time:.3f}秒")
            print(f"理論効率: {(sum(processing_times) / total_time):.2f}")
            
            # 並行処理の効果確認
            assert total_time < sum(processing_times)  # 並行処理により総時間が短縮
    
    def test_large_data_processing(self, mock_payment_link):
        """大量データ処理テスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            # 大きなOCRデータをシミュレート
            large_ocr_data = {
                'customer_name': 'A' * 500,  # 500文字の顧客名
                'description': 'B' * 1000,  # 1000文字の説明
                'amount': '999999',  # 大きな金額
                'additional_data': 'C' * 2000  # 追加データ
            }
            
            start_time = time.time()
            
            result = create_stripe_payment_link_from_ocr(
                ocr_data=large_ocr_data,
                filename='large_data_test.pdf'
            )
            
            processing_time = time.time() - start_time
            
            assert result['success'] is True
            assert processing_time < 3.0  # 大量データでも3秒以内
            print(f"大量データ処理時間: {processing_time:.3f}秒")
    
    def test_memory_usage_stability(self, mock_payment_link):
        """メモリ使用量安定性テスト"""
        import psutil
        import gc
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            # 多数のリクエストでメモリリークを確認
            for i in range(100):
                result = create_stripe_payment_link(
                    amount=1000,
                    customer_name=f'メモリテスト_{i}',
                    description='メモリ使用量確認',
                    currency='jpy'
                )
                assert result['success'] is True
                
                # 定期的にガベージコレクション
                if i % 20 == 0:
                    gc.collect()
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        print(f"\\nメモリ使用量:")
        print(f"初期: {initial_memory:.2f} MB")
        print(f"最終: {final_memory:.2f} MB")
        print(f"増加: {memory_increase:.2f} MB")
        
        # メモリ増加が50MB以内であることを確認
        assert memory_increase < 50.0


class TestScalability:
    """スケーラビリティテストクラス"""
    
    @pytest.fixture
    def mock_payment_link(self):
        """モック決済リンク"""
        return Mock(
            id='plink_scale_test',
            url='https://checkout.stripe.com/c/pay/plink_scale_test'
        )
    
    @pytest.mark.parametrize("batch_size", [1, 5, 10, 20, 50])
    def test_batch_processing_scalability(self, batch_size, mock_payment_link):
        """バッチ処理スケーラビリティテスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            start_time = time.time()
            
            successful_requests = 0
            for i in range(batch_size):
                result = create_stripe_payment_link(
                    amount=1000 + i,
                    customer_name=f'バッチテスト_{i}',
                    description=f'バッチ処理_{batch_size}_{i}',
                    currency='jpy'
                )
                if result['success']:
                    successful_requests += 1
            
            total_time = time.time() - start_time
            throughput = successful_requests / total_time  # リクエスト/秒
            
            print(f"\\nバッチサイズ {batch_size}:")
            print(f"成功リクエスト: {successful_requests}/{batch_size}")
            print(f"総処理時間: {total_time:.3f}秒")
            print(f"スループット: {throughput:.2f} req/s")
            
            assert successful_requests == batch_size
            assert throughput > 1.0  # 最低1リクエスト/秒
    
    def test_configuration_performance(self):
        """設定管理パフォーマンステスト"""
        config_manager = ConfigManager()
        
        # 設定読み込み性能
        start_time = time.time()
        for _ in range(100):
            config = config_manager.get_config()
            assert isinstance(config, dict)
        read_time = time.time() - start_time
        
        # 設定検証性能
        test_config = {
            'stripe_mode': 'test',
            'stripe_secret_key_test': 'sk_test_1234567890abcdef',
            'default_payment_provider': 'stripe'
        }
        
        start_time = time.time()
        for _ in range(50):
            result = config_manager.validate_config_schema(test_config)
            assert isinstance(result, dict)
        validation_time = time.time() - start_time
        
        print(f"\\n設定管理パフォーマンス:")
        print(f"設定読み込み (100回): {read_time:.3f}秒")
        print(f"設定検証 (50回): {validation_time:.3f}秒")
        
        assert read_time < 1.0   # 100回読み込みが1秒以内
        assert validation_time < 5.0  # 50回検証が5秒以内


class TestLoadTesting:
    """負荷テストクラス"""
    
    @pytest.fixture
    def mock_payment_link(self):
        """モック決済リンク"""
        return Mock(
            id='plink_load_test',
            url='https://checkout.stripe.com/c/pay/plink_load_test'
        )
    
    @pytest.mark.slow
    def test_sustained_load(self, mock_payment_link):
        """持続負荷テスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            duration = 30  # 30秒間の負荷テスト
            request_count = 0
            errors = 0
            start_time = time.time()
            
            while time.time() - start_time < duration:
                try:
                    result = create_stripe_payment_link(
                        amount=1000,
                        customer_name=f'負荷テスト_{request_count}',
                        description='持続負荷テスト',
                        currency='jpy'
                    )
                    request_count += 1
                    
                    if not result['success']:
                        errors += 1
                        
                except Exception as e:
                    errors += 1
                    print(f"エラー発生: {e}")
            
            total_time = time.time() - start_time
            throughput = request_count / total_time
            error_rate = errors / request_count if request_count > 0 else 0
            
            print(f"\\n持続負荷テスト結果 ({duration}秒):")
            print(f"総リクエスト数: {request_count}")
            print(f"エラー数: {errors}")
            print(f"エラー率: {error_rate:.2%}")
            print(f"平均スループット: {throughput:.2f} req/s")
            
            # 性能基準
            assert request_count > 50  # 最低50リクエスト処理
            assert error_rate < 0.05   # エラー率5%未満
            assert throughput > 2.0    # 平均2req/s以上
    
    @pytest.mark.slow
    def test_spike_load(self, mock_payment_link):
        """スパイク負荷テスト"""
        with patch('stripe.PaymentLink.create', return_value=mock_payment_link):
            spike_duration = 5  # 5秒間のスパイク
            normal_rate = 2     # 通常2req/s
            spike_rate = 20     # スパイク時20req/s
            
            results = {
                'normal_phase': {'requests': 0, 'errors': 0, 'time': 0},
                'spike_phase': {'requests': 0, 'errors': 0, 'time': 0},
                'recovery_phase': {'requests': 0, 'errors': 0, 'time': 0}
            }
            
            phases = [
                ('normal_phase', 10, normal_rate),
                ('spike_phase', spike_duration, spike_rate),
                ('recovery_phase', 10, normal_rate)
            ]
            
            for phase_name, duration, target_rate in phases:
                start_time = time.time()
                request_interval = 1.0 / target_rate
                
                while time.time() - start_time < duration:
                    request_start = time.time()
                    
                    try:
                        result = create_stripe_payment_link(
                            amount=1000,
                            customer_name=f'スパイクテスト_{phase_name}',
                            description=f'{phase_name}テスト',
                            currency='jpy'
                        )
                        results[phase_name]['requests'] += 1
                        
                        if not result['success']:
                            results[phase_name]['errors'] += 1
                            
                    except Exception:
                        results[phase_name]['errors'] += 1
                    
                    # レート制御
                    elapsed = time.time() - request_start
                    if elapsed < request_interval:
                        time.sleep(request_interval - elapsed)
                
                results[phase_name]['time'] = time.time() - start_time
            
            # 結果表示と検証
            for phase_name, data in results.items():
                if data['requests'] > 0:
                    throughput = data['requests'] / data['time']
                    error_rate = data['errors'] / data['requests']
                    
                    print(f"\\n{phase_name}:")
                    print(f"  リクエスト数: {data['requests']}")
                    print(f"  エラー数: {data['errors']}")
                    print(f"  エラー率: {error_rate:.2%}")
                    print(f"  スループット: {throughput:.2f} req/s")
                    
                    # スパイク時でもシステムが安定していることを確認
                    assert error_rate < 0.1  # エラー率10%未満


if __name__ == '__main__':
    # パフォーマンステスト実行
    pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '-m', 'not slow'  # 通常は時間のかかるテストを除外
    ])