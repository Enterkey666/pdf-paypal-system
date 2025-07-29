#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
エンタイトルメント管理モジュール
サブスクリプション状態の確認と機能アクセス制御
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from database import get_db_connection

# ロガーの設定
logger = logging.getLogger(__name__)

def has_active_subscription(user_id: int) -> bool:
    """
    ユーザーがアクティブなサブスクリプションを持っているかチェック
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        bool: アクティブなサブスクリプションがあるかどうか
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # アクティブなサブスクリプションをチェック
        cursor.execute("""
            SELECT status, current_period_end, cancel_at_period_end
            FROM subscriptions 
            WHERE user_id = ? 
            AND status IN ('active', 'trialing')
            ORDER BY created_at DESC 
            LIMIT 1
        """, (user_id,))
        
        subscription = cursor.fetchone()
        conn.close()
        
        if not subscription:
            logger.debug(f"アクティブなサブスクリプション無し: user_id={user_id}")
            return False
        
        # 期間終了日をチェック
        period_end = datetime.fromisoformat(subscription['current_period_end'].replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        
        if period_end <= now:
            logger.debug(f"サブスクリプション期間終了: user_id={user_id}, period_end={period_end}")
            return False
        
        # ステータスがアクティブまたはトライアル中
        is_active = subscription['status'] in ['active', 'trialing']
        
        logger.debug(f"サブスクリプション状態: user_id={user_id}, status={subscription['status']}, active={is_active}")
        return is_active
        
    except Exception as e:
        logger.error(f"サブスクリプション状態確認エラー: user_id={user_id}, error={str(e)}")
        return False

def get_user_subscription_status(user_id: int) -> Dict[str, Any]:
    """
    ユーザーのサブスクリプション詳細状態を取得
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        Dict[str, Any]: サブスクリプション状態の詳細情報
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT *
            FROM subscriptions 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (user_id,))
        
        subscription = cursor.fetchone()
        conn.close()
        
        if not subscription:
            return {
                'has_subscription': False,
                'status': None,
                'plan_id': None,
                'current_period_end': None,
                'cancel_at_period_end': False,
                'trial_end': None,
                'is_active': False
            }
        
        # 期間終了日をチェック
        period_end = datetime.fromisoformat(subscription['current_period_end'].replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        is_active = subscription['status'] in ['active', 'trialing'] and period_end > now
        
        return {
            'has_subscription': True,
            'status': subscription['status'],
            'plan_id': subscription['plan_id'],
            'current_period_end': subscription['current_period_end'],
            'cancel_at_period_end': bool(subscription['cancel_at_period_end']),
            'trial_end': subscription['trial_end'],
            'is_active': is_active,
            'stripe_subscription_id': subscription['stripe_subscription_id']
        }
        
    except Exception as e:
        logger.error(f"サブスクリプション詳細取得エラー: user_id={user_id}, error={str(e)}")
        return {
            'has_subscription': False,
            'status': 'error',
            'plan_id': None,
            'current_period_end': None,
            'cancel_at_period_end': False,
            'trial_end': None,
            'is_active': False,
            'error': str(e)
        }

def has_feature_access(user_id: int, feature: str) -> bool:
    """
    ユーザーが特定の機能にアクセス可能かチェック
    
    Args:
        user_id (int): ユーザーID
        feature (str): 機能名 (例: 'ocr_google', 'ocr_azure')
        
    Returns:
        bool: 機能アクセス可能かどうか
    """
    try:
        # まずアクティブなサブスクリプションをチェック
        if not has_active_subscription(user_id):
            logger.debug(f"機能アクセス拒否 (サブスクリプション無効): user_id={user_id}, feature={feature}")
            return False
        
        # エンタイトルメントテーブルをチェック
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT limit_value, expires_at
            FROM entitlements 
            WHERE user_id = ? AND feature = ?
        """, (user_id, feature))
        
        entitlement = cursor.fetchone()
        conn.close()
        
        if not entitlement:
            logger.debug(f"エンタイトルメント無し: user_id={user_id}, feature={feature}")
            return False
        
        # 有効期限をチェック
        if entitlement['expires_at']:
            expires_at = datetime.fromisoformat(entitlement['expires_at'].replace('Z', '+00:00'))
            if expires_at <= datetime.now(timezone.utc):
                logger.debug(f"エンタイトルメント期限切れ: user_id={user_id}, feature={feature}")
                return False
        
        # limit_valueをチェック ('ON', 'OFF', または数値)
        limit_value = entitlement['limit_value']
        access_granted = limit_value == 'ON' or (limit_value.isdigit() and int(limit_value) > 0)
        
        logger.debug(f"機能アクセス結果: user_id={user_id}, feature={feature}, access={access_granted}")
        return access_granted
        
    except Exception as e:
        logger.error(f"機能アクセスチェックエラー: user_id={user_id}, feature={feature}, error={str(e)}")
        return False

def grant_default_entitlements(user_id: int) -> bool:
    """
    新規ユーザーまたはサブスクリプション開始時にデフォルトエンタイトルメントを付与
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        bool: 付与成功
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # デフォルトエンタイトルメント一覧
        default_entitlements = [
            ('ocr_google', 'ON'),
            ('ocr_azure', 'ON')
        ]
        
        cursor.execute("BEGIN")
        
        for feature, limit_value in default_entitlements:
            cursor.execute("""
                INSERT OR REPLACE INTO entitlements (user_id, feature, limit_value)
                VALUES (?, ?, ?)
            """, (user_id, feature, limit_value))
        
        conn.commit()
        conn.close()
        
        logger.info(f"デフォルトエンタイトルメント付与完了: user_id={user_id}")
        return True
        
    except Exception as e:
        logger.error(f"エンタイトルメント付与エラー: user_id={user_id}, error={str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

def get_user_entitlements(user_id: int) -> List[Dict[str, Any]]:
    """
    ユーザーのエンタイトルメント一覧を取得
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        List[Dict[str, Any]]: エンタイトルメント一覧
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT feature, limit_value, reset_period, granted_at, expires_at
            FROM entitlements 
            WHERE user_id = ?
            ORDER BY feature
        """, (user_id,))
        
        entitlements = []
        for row in cursor.fetchall():
            entitlement = dict(row)
            # アクセス可能かどうかも含める
            entitlement['has_access'] = has_feature_access(user_id, entitlement['feature'])
            entitlements.append(entitlement)
        
        conn.close()
        return entitlements
        
    except Exception as e:
        logger.error(f"エンタイトルメント一覧取得エラー: user_id={user_id}, error={str(e)}")
        return []

def api_access_required(feature: str):
    """
    API機能アクセス制御デコレータ
    有料機能へのアクセスを制御する
    
    Args:
        feature (str): 必要な機能名
        
    Returns:
        decorator: Flask用デコレータ
    """
    from functools import wraps
    from flask import jsonify
    from flask_login import current_user
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # ログイン状態をチェック
            if not current_user or not current_user.is_authenticated:
                return jsonify({
                    'success': False,
                    'error': 'Authentication required',
                    'error_code': 'AUTH_REQUIRED'
                }), 401
            
            # 管理者は全機能アクセス可能
            if hasattr(current_user, 'is_admin') and current_user.is_admin:
                return f(*args, **kwargs)
            
            # 機能アクセス権をチェック
            if not has_feature_access(current_user.id, feature):
                logger.warning(f"API機能アクセス拒否: user_id={current_user.id}, feature={feature}")
                return jsonify({
                    'success': False,
                    'error': f'Access to {feature} requires an active subscription',
                    'error_code': 'SUBSCRIPTION_REQUIRED',
                    'feature': feature
                }), 402  # Payment Required
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def check_legacy_paid_member_status(user_id: int) -> bool:
    """
    既存のis_paid_memberフラグとの後方互換性チェック
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        bool: 有料会員かどうか（新旧システム統合判定）
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 新システム: アクティブなサブスクリプションをチェック
        if has_active_subscription(user_id):
            return True
        
        # 旧システム: is_paid_memberフラグをチェック (後方互換性)
        cursor.execute("SELECT is_paid_member FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user and hasattr(user, 'is_paid_member') and user['is_paid_member']:
            logger.debug(f"レガシー有料会員フラグでアクセス許可: user_id={user_id}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"有料会員状態チェックエラー: user_id={user_id}, error={str(e)}")
        return False

def sync_legacy_paid_members():
    """
    既存のis_paid_memberユーザーにデフォルトエンタイトルメントを付与
    マイグレーション用関数
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # is_paid_member=1のユーザーを取得
        cursor.execute("SELECT id FROM users WHERE is_paid_member = 1")
        paid_users = cursor.fetchall()
        
        for user in paid_users:
            user_id = user['id']
            
            # 既にエンタイトルメントがある場合はスキップ
            cursor.execute("SELECT COUNT(*) as count FROM entitlements WHERE user_id = ?", (user_id,))
            if cursor.fetchone()['count'] > 0:
                continue
            
            # デフォルトエンタイトルメントを付与
            grant_default_entitlements(user_id)
            logger.info(f"レガシー有料会員にエンタイトルメント付与: user_id={user_id}")
        
        conn.close()
        logger.info(f"レガシー有料会員同期完了: {len(paid_users)}ユーザー処理")
        
    except Exception as e:
        logger.error(f"レガシー有料会員同期エラー: {str(e)}")