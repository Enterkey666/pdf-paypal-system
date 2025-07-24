#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe設定関連のルート
Stripe設定の保存、接続テスト等を処理
"""

import os
import json
import logging
from flask import Blueprint, request, jsonify, flash, redirect, url_for
from stripe_utils import test_stripe_connection

# ロガーの設定
logger = logging.getLogger(__name__)

# Blueprintの作成
stripe_bp = Blueprint('stripe', __name__, url_prefix='/settings')

@stripe_bp.route('/test_stripe_connection', methods=['POST'])
def test_stripe_connection_route():
    """
    Stripe接続テストエンドポイント
    """
    try:
        # JSONデータを取得
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'リクエストデータがありません'
            }), 400
        
        # 必要なデータを取得
        publishable_key = data.get('publishable_key', '')
        secret_key = data.get('secret_key', '')
        stripe_mode = data.get('stripe_mode', 'test')
        
        logger.info(f"Stripe接続テスト: mode={stripe_mode}")
        
        # 認証情報の検証
        if not secret_key:
            return jsonify({
                'success': False,
                'message': 'Stripe Secret Keyが設定されていません'
            }), 400
        
        # Secret Keyの形式チェック
        expected_prefix = 'sk_test_' if stripe_mode == 'test' else 'sk_live_'
        if not secret_key.startswith(expected_prefix):
            return jsonify({
                'success': False,
                'message': f'Secret Keyの形式が正しくありません。{stripe_mode}環境では{expected_prefix}で始まるキーが必要です'
            }), 400
        
        # Publishable Keyの形式チェック（オプショナル）
        if publishable_key:
            expected_pk_prefix = 'pk_test_' if stripe_mode == 'test' else 'pk_live_'
            if not publishable_key.startswith(expected_pk_prefix):
                logger.warning(f"Publishable Keyの形式が正しくない可能性があります: {publishable_key[:20]}...")
        
        # Stripe接続テストを実行
        result = test_stripe_connection(secret_key)
        
        if result.get('success'):
            logger.info(f"Stripe接続テスト成功: {result.get('message')}")
        else:
            logger.warning(f"Stripe接続テスト失敗: {result.get('message')}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Stripe接続テストエラー: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'接続テスト中にエラーが発生しました: {str(e)}'
        }), 500

@stripe_bp.route('/save_stripe', methods=['POST'])
def save_stripe_settings():
    """
    Stripe設定保存エンドポイント
    """
    try:
        # フォームデータを取得
        stripe_publishable_key = request.form.get('stripe_publishable_key', '').strip()
        stripe_secret_key = request.form.get('stripe_secret_key', '').strip()
        stripe_mode = request.form.get('stripe_mode', 'test')
        default_payment_provider = request.form.get('default_payment_provider', 'paypal')
        
        logger.info(f"Stripe設定保存: mode={stripe_mode}, default_provider={default_payment_provider}")
        
        # 設定マネージャーを使用して設定を保存
        from config_manager import ConfigManager
        config_manager = ConfigManager()
        
        # 設定を更新
        config_updates = {}
        
        # モードに応じてキーを保存
        if stripe_mode == 'test':
            if stripe_publishable_key:
                config_updates['stripe_publishable_key_test'] = stripe_publishable_key
            if stripe_secret_key:
                config_updates['stripe_secret_key_test'] = stripe_secret_key
        else:
            if stripe_publishable_key:
                config_updates['stripe_publishable_key_live'] = stripe_publishable_key
            if stripe_secret_key:
                config_updates['stripe_secret_key_live'] = stripe_secret_key
        
        # 共通設定
        config_updates['stripe_mode'] = stripe_mode
        config_updates['default_payment_provider'] = default_payment_provider
        
        # 設定を保存
        if config_updates:
            # 設定を直接更新
            config_manager.config.update(config_updates)
            save_result = config_manager.save_config(config_manager.config)
            
            if save_result:
                logger.info(f"Stripe設定保存成功: {config_updates}")
                
                # 環境変数も更新（後方互換性のため）
                if stripe_mode == 'test':
                    if stripe_publishable_key:
                        os.environ['STRIPE_PUBLISHABLE_KEY_TEST'] = stripe_publishable_key
                    if stripe_secret_key:
                        os.environ['STRIPE_SECRET_KEY_TEST'] = stripe_secret_key
                else:
                    if stripe_publishable_key:
                        os.environ['STRIPE_PUBLISHABLE_KEY_LIVE'] = stripe_publishable_key
                    if stripe_secret_key:
                        os.environ['STRIPE_SECRET_KEY_LIVE'] = stripe_secret_key
                
                os.environ['STRIPE_MODE'] = stripe_mode
                os.environ['DEFAULT_PAYMENT_PROVIDER'] = default_payment_provider
                
                # プロバイダー設定変更時にキャッシュをクリア
                try:
                    from app import clear_cache
                    clear_cache()
                    logger.info("決済プロバイダー設定変更によりキャッシュをクリアしました")
                except ImportError:
                    logger.warning("キャッシュクリア機能をインポートできませんでした")
                except Exception as e:
                    logger.warning(f"キャッシュクリア中にエラー: {e}")
                
                # 常にJSONレスポンスを返す（フロントエンドでAjax処理のため）
                return jsonify({
                    'success': True,
                    'message': 'Stripe設定が正常に保存されました'
                }), 200
            else:
                logger.error("Stripe設定保存失敗")
                return jsonify({
                    'success': False,
                    'error': '設定の保存に失敗しました'
                }), 500
        else:
            return jsonify({
                'success': True,
                'message': '更新する設定がありませんでした'
            }), 200
        
    except Exception as e:
        logger.error(f"Stripe設定保存エラー: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'設定保存中にエラーが発生しました: {str(e)}'
        }), 500