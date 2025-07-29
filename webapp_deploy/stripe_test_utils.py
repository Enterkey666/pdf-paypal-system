#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe機能テストユーティリティ
Stripe Payment Links API機能の包括的テスト
"""

import os
import json
import logging
from typing import Dict, Any, List
from datetime import datetime

# ロガーの設定
logger = logging.getLogger(__name__)

def run_stripe_comprehensive_test() -> Dict[str, Any]:
    """
    Stripe機能の包括的テストを実行
    
    Returns:
        Dict[str, Any]: テスト結果
    """
    try:
        logger.info("Stripe包括的テスト開始")
        
        test_results = {
            'overall_success': False,
            'timestamp': datetime.now().isoformat(),
            'tests': {}
        }
        
        # 1. 設定検証テスト
        logger.info("1. Stripe設定検証テスト実行中...")
        config_test = test_stripe_configuration()
        test_results['tests']['configuration'] = config_test
        
        # 2. 接続テスト
        logger.info("2. Stripe接続テスト実行中...")
        connection_test = test_stripe_connection_comprehensive()
        test_results['tests']['connection'] = connection_test
        
        # 3. Payment Link作成テスト
        logger.info("3. Stripe Payment Link作成テスト実行中...")
        payment_link_test = test_stripe_payment_link_creation()
        test_results['tests']['payment_link_creation'] = payment_link_test
        
        # 4. OCR連携テスト
        logger.info("4. Stripe OCR連携テスト実行中...")
        ocr_integration_test = test_stripe_ocr_integration()
        test_results['tests']['ocr_integration'] = ocr_integration_test
        
        # 5. エラーハンドリングテスト
        logger.info("5. Stripeエラーハンドリングテスト実行中...")
        error_handling_test = test_stripe_error_handling()
        test_results['tests']['error_handling'] = error_handling_test
        
        # 全体の成功判定
        all_tests_passed = all(
            test.get('success', False) for test in test_results['tests'].values()
        )
        test_results['overall_success'] = all_tests_passed
        
        # サマリー生成
        passed_count = sum(1 for test in test_results['tests'].values() if test.get('success', False))
        total_count = len(test_results['tests'])
        
        test_results['summary'] = {
            'passed': passed_count,
            'total': total_count,
            'success_rate': f"{(passed_count/total_count)*100:.1f}%" if total_count > 0 else "0%"
        }
        
        logger.info(f"Stripe包括的テスト完了: {passed_count}/{total_count} 成功")
        
        return test_results
        
    except Exception as e:
        logger.error(f"Stripe包括的テストエラー: {str(e)}")
        return {
            'overall_success': False,
            'timestamp': datetime.now().isoformat(),
            'error': str(e),
            'tests': {},
            'summary': {'passed': 0, 'total': 0, 'success_rate': '0%'}
        }

def test_stripe_configuration() -> Dict[str, Any]:
    """
    Stripe設定の検証テスト
    """
    try:
        from stripe_utils import validate_stripe_configuration
        
        result = validate_stripe_configuration()
        
        return {
            'success': result.get('valid', False),
            'message': 'Stripe設定検証完了',
            'details': result
        }
        
    except Exception as e:
        logger.error(f"Stripe設定検証テストエラー: {str(e)}")
        return {
            'success': False,
            'message': f'設定検証テストエラー: {str(e)}',
            'details': {}
        }

def test_stripe_connection_comprehensive() -> Dict[str, Any]:
    """
    Stripe接続の包括的テスト
    """
    try:
        from stripe_utils import test_stripe_connection
        
        result = test_stripe_connection()
        
        # 追加の接続テスト項目
        additional_tests = {}
        
        if result.get('success'):
            # アカウント詳細の確認
            details = result.get('details', {})
            additional_tests['account_active'] = bool(details.get('charges_enabled'))
            additional_tests['currency_support'] = details.get('default_currency') in ['jpy', 'usd', 'eur']
            additional_tests['country_code'] = bool(details.get('country'))
        
        return {
            'success': result.get('success', False),
            'message': result.get('message', '接続テスト失敗'),
            'details': {
                **result.get('details', {}),
                'additional_tests': additional_tests
            }
        }
        
    except Exception as e:
        logger.error(f"Stripe接続テストエラー: {str(e)}")
        return {
            'success': False,
            'message': f'接続テストエラー: {str(e)}',
            'details': {}
        }

def test_stripe_payment_link_creation() -> Dict[str, Any]:
    """
    Stripe Payment Link作成テスト
    """
    try:
        from stripe_utils import create_stripe_payment_link
        
        # テスト用のダミーデータ
        test_cases = [
            {
                'name': '基本テスト',
                'amount': 1000,
                'customer_name': 'テスト顧客',
                'description': 'テスト決済',
                'currency': 'jpy'
            },
            {
                'name': '高額テスト',
                'amount': 100000,
                'customer_name': '高額テスト顧客',
                'description': '高額決済テスト',
                'currency': 'jpy'
            },
            {
                'name': '少額テスト',
                'amount': 100,
                'customer_name': '少額テスト顧客',
                'description': '少額決済テスト',
                'currency': 'jpy'
            }
        ]
        
        test_results = []
        overall_success = True
        
        for test_case in test_cases:
            try:
                result = create_stripe_payment_link(
                    amount=test_case['amount'],
                    customer_name=test_case['customer_name'],
                    description=test_case['description'],
                    currency=test_case['currency']
                )
                
                test_success = result.get('success', False)
                if not test_success:
                    overall_success = False
                
                test_results.append({
                    'test_name': test_case['name'],
                    'success': test_success,
                    'message': result.get('message', ''),
                    'payment_link_created': bool(result.get('payment_link'))
                })
                
            except Exception as e:
                overall_success = False
                test_results.append({
                    'test_name': test_case['name'],
                    'success': False,
                    'message': f'テストエラー: {str(e)}',
                    'payment_link_created': False
                })
        
        return {
            'success': overall_success,
            'message': f'Payment Link作成テスト完了 ({sum(1 for r in test_results if r["success"])}/{len(test_results)} 成功)',
            'details': {
                'test_results': test_results,
                'total_tests': len(test_results),
                'passed_tests': sum(1 for r in test_results if r['success'])
            }
        }
        
    except Exception as e:
        logger.error(f"Stripe Payment Link作成テストエラー: {str(e)}")
        return {
            'success': False,
            'message': f'Payment Link作成テストエラー: {str(e)}',
            'details': {}
        }

def test_stripe_ocr_integration() -> Dict[str, Any]:
    """
    Stripe OCR連携テスト
    """
    try:
        from payment_utils import create_payment_link_from_ocr
        from payment_utils import extract_and_validate_payment_data
        
        # テスト用のOCRデータ
        test_ocr_data = [
            {
                'name': '正常データ',
                'data': {
                    'customer_name': 'テスト株式会社',
                    'amount': '10,000',
                    'date': '2024-01-15'
                }
            },
            {
                'name': '円マーク付きデータ',
                'data': {
                    '顧客名': 'サンプル会社',
                    '金額': '¥5,500',
                    '日付': '2024-02-01'
                }
            },
            {
                'name': '数値データ',
                'data': {
                    'customer_name': '数値テスト会社',
                    'amount': 25000,
                    'date': '2024-03-01'
                }
            }
        ]
        
        test_results = []
        overall_success = True
        
        for test_case in test_ocr_data:
            try:
                # データ抽出・検証テスト
                validation_result = extract_and_validate_payment_data(test_case['data'])
                
                if validation_result.get('valid'):
                    # Payment Link作成テスト
                    payment_result = create_payment_link_from_ocr(
                        provider='stripe',
                        ocr_data=test_case['data'],
                        filename=f"test_{test_case['name']}.pdf"
                    )
                    
                    test_success = payment_result.get('success', False)
                else:
                    test_success = False
                    payment_result = {'message': 'データ検証失敗'}
                
                if not test_success:
                    overall_success = False
                
                test_results.append({
                    'test_name': test_case['name'],
                    'success': test_success,
                    'validation_result': validation_result,
                    'payment_result': {
                        'success': payment_result.get('success', False),
                        'message': payment_result.get('message', ''),
                        'payment_link_created': bool(payment_result.get('payment_link'))
                    }
                })
                
            except Exception as e:
                overall_success = False
                test_results.append({
                    'test_name': test_case['name'],
                    'success': False,
                    'error': str(e),
                    'validation_result': {},
                    'payment_result': {}
                })
        
        return {
            'success': overall_success,
            'message': f'OCR連携テスト完了 ({sum(1 for r in test_results if r["success"])}/{len(test_results)} 成功)',
            'details': {
                'test_results': test_results,
                'total_tests': len(test_results),
                'passed_tests': sum(1 for r in test_results if r['success'])
            }
        }
        
    except Exception as e:
        logger.error(f"Stripe OCR連携テストエラー: {str(e)}")
        return {
            'success': False,
            'message': f'OCR連携テストエラー: {str(e)}',
            'details': {}
        }

def test_stripe_error_handling() -> Dict[str, Any]:
    """
    Stripeエラーハンドリングテスト
    """
    try:
        from stripe_utils import create_stripe_payment_link, test_stripe_connection
        
        error_test_cases = [
            {
                'name': '無効な金額テスト',
                'test_func': lambda: create_stripe_payment_link(
                    amount=-100,  # 負の金額
                    customer_name='テスト顧客',
                    description='エラーテスト'
                ),
                'expected_error': True
            },
            {
                'name': '空の顧客名テスト',
                'test_func': lambda: create_stripe_payment_link(
                    amount=1000,
                    customer_name='',  # 空の顧客名
                    description='エラーテスト'
                ),
                'expected_error': False  # 空でも処理できるはず
            },
            {
                'name': '無効なAPIキーテスト',
                'test_func': lambda: test_stripe_connection('sk_test_invalid_key'),
                'expected_error': True
            }
        ]
        
        test_results = []
        overall_success = True
        
        for test_case in error_test_cases:
            try:
                result = test_case['test_func']()
                
                # エラーが期待される場合
                if test_case['expected_error']:
                    test_success = not result.get('success', True)  # 失敗することが期待される
                else:
                    test_success = result.get('success', False)  # 成功することが期待される
                
                if not test_success:
                    overall_success = False
                
                test_results.append({
                    'test_name': test_case['name'],
                    'success': test_success,
                    'expected_error': test_case['expected_error'],
                    'actual_result': result.get('success', False),
                    'message': result.get('message', '')
                })
                
            except Exception as e:
                # 例外が発生した場合
                if test_case['expected_error']:
                    # エラーが期待される場合は成功
                    test_success = True
                else:
                    # エラーが期待されない場合は失敗
                    test_success = False
                    overall_success = False
                
                test_results.append({
                    'test_name': test_case['name'],
                    'success': test_success,
                    'expected_error': test_case['expected_error'],
                    'exception': str(e)
                })
        
        return {
            'success': overall_success,
            'message': f'エラーハンドリングテスト完了 ({sum(1 for r in test_results if r["success"])}/{len(test_results)} 成功)',
            'details': {
                'test_results': test_results,
                'total_tests': len(test_results),
                'passed_tests': sum(1 for r in test_results if r['success'])
            }
        }
        
    except Exception as e:
        logger.error(f"Stripeエラーハンドリングテストエラー: {str(e)}")
        return {
            'success': False,
            'message': f'エラーハンドリングテストエラー: {str(e)}',
            'details': {}
        }

def generate_test_report(test_results: Dict[str, Any]) -> str:
    """
    テスト結果レポートを生成
    
    Args:
        test_results (Dict[str, Any]): テスト結果
        
    Returns:
        str: HTMLフォーマットのレポート
    """
    try:
        report_html = f"""
        <div class="stripe-test-report">
            <h2>Stripe機能テストレポート</h2>
            <div class="test-summary">
                <p><strong>実行日時:</strong> {test_results.get('timestamp', '不明')}</p>
                <p><strong>全体結果:</strong> {'✅ 成功' if test_results.get('overall_success') else '❌ 失敗'}</p>
                <p><strong>成功率:</strong> {test_results.get('summary', {}).get('success_rate', '0%')}</p>
            </div>
            
            <div class="test-details">
                <h3>テスト詳細</h3>
        """
        
        for test_name, test_result in test_results.get('tests', {}).items():
            status_icon = '✅' if test_result.get('success') else '❌'
            report_html += f"""
                <div class="test-item">
                    <h4>{status_icon} {test_name.replace('_', ' ').title()}</h4>
                    <p><strong>結果:</strong> {test_result.get('message', 'メッセージなし')}</p>
                </div>
            """
        
        report_html += """
            </div>
        </div>
        """
        
        return report_html
        
    except Exception as e:
        logger.error(f"テストレポート生成エラー: {str(e)}")
        return f"<div class='error'>レポート生成エラー: {str(e)}</div>"