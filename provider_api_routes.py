#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
決済プロバイダーAPI関連のルート
フロントエンドからの決済プロバイダー利用可能性チェック等を処理
"""

import logging
from flask import Blueprint, jsonify, request
from payment_utils import get_available_payment_providers, test_payment_provider_connection

# ロガーの設定
logger = logging.getLogger(__name__)

# Blueprintの作成
provider_api_bp = Blueprint('provider_api', __name__, url_prefix='/api')

@provider_api_bp.route('/check_provider/<provider>', methods=['GET'])
def check_provider_availability(provider):
    """
    指定された決済プロバイダーの利用可能性をチェック
    
    Args:
        provider (str): 決済プロバイダー名 ('paypal' または 'stripe')
        
    Returns:
        JSON: 利用可能性とステータス情報
    """
    try:
        logger.info(f"プロバイダー利用可能性チェック: {provider}")
        
        # 利用可能なプロバイダー一覧を取得
        available_providers = get_available_payment_providers()
        
        if provider not in available_providers:
            return jsonify({
                'available': False,
                'message': f'サポートされていないプロバイダー: {provider}',
                'details': {}
            }), 400
        
        is_available = available_providers[provider]
        
        result = {
            'available': is_available,
            'provider': provider,
            'message': f'{provider.upper()}は{"利用可能" if is_available else "設定が必要"}です'
        }
        
        # 利用可能な場合は接続テストも実行
        if is_available:
            connection_test = test_payment_provider_connection(provider)
            result['connection_test'] = connection_test
            if not connection_test.get('success'):
                result['available'] = False
                result['message'] = f'{provider.upper()}の設定に問題があります: {connection_test.get("message", "")}'
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"プロバイダーチェックエラー: {str(e)}")
        return jsonify({
            'available': False,
            'message': f'チェック中にエラーが発生しました: {str(e)}',
            'details': {'error': str(e)}
        }), 500

@provider_api_bp.route('/available_providers', methods=['GET'])
def get_available_providers():
    """
    利用可能な決済プロバイダー一覧を取得
    
    Returns:
        JSON: 利用可能なプロバイダー一覧
    """
    try:
        logger.info("利用可能プロバイダー一覧取得")
        
        available_providers = get_available_payment_providers()
        
        return jsonify({
            'success': True,
            'providers': available_providers,
            'available_count': sum(available_providers.values()),
            'total_count': len(available_providers)
        })
        
    except Exception as e:
        logger.error(f"プロバイダー一覧取得エラー: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'プロバイダー一覧取得中にエラーが発生しました: {str(e)}',
            'providers': {},
            'available_count': 0,
            'total_count': 0
        }), 500

@provider_api_bp.route('/test_provider/<provider>', methods=['POST'])
def test_provider_connection_api(provider):
    """
    指定された決済プロバイダーの接続テスト
    
    Args:
        provider (str): 決済プロバイダー名
        
    Returns:
        JSON: 接続テスト結果
    """
    try:
        logger.info(f"プロバイダー接続テスト: {provider}")
        
        # 接続テストを実行
        result = test_payment_provider_connection(provider)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"プロバイダー接続テストエラー: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'接続テスト中にエラーが発生しました: {str(e)}',
            'details': {'error': str(e)}
        }), 500