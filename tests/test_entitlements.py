#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
エンタイトルメント機能のユニットテスト
"""

import unittest
import os
import tempfile
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# テスト対象のモジュールをインポート
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entitlements import (
    has_active_subscription,
    get_user_subscription_status,
    has_feature_access,
    grant_default_entitlements,
    get_user_entitlements,
    check_legacy_paid_member_status
)

class TestEntitlements(unittest.TestCase):
    
    def setUp(self):
        """テスト前の初期化"""
        # テスト用の一時データベースを作成
        self.test_db_fd, self.test_db_path = tempfile.mkstemp()
        
        # データベース接続をモック
        self.conn = sqlite3.connect(self.test_db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        
        # テスト用テーブルを作成
        self.cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                email TEXT,
                is_paid_member BOOLEAN DEFAULT 0,
                stripe_customer_id TEXT
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE subscriptions (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                stripe_subscription_id TEXT,
                plan_id TEXT,
                status TEXT,
                current_period_start TIMESTAMP,
                current_period_end TIMESTAMP,
                cancel_at_period_end BOOLEAN DEFAULT 0,
                trial_end TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE entitlements (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                feature TEXT,
                limit_value TEXT DEFAULT 'ON',
                reset_period TEXT DEFAULT 'monthly',
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        
        self.conn.commit()
        
        # database.get_db_connection をモック
        self.db_mock = patch('entitlements.get_db_connection')
        self.mock_get_db = self.db_mock.start()
        self.mock_get_db.return_value = self.conn
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.conn.close()
        os.close(self.test_db_fd)
        os.unlink(self.test_db_path)
        self.db_mock.stop()
    
    def create_test_user(self, user_id=1, is_paid_member=False):
        """テスト用ユーザーを作成"""
        self.cursor.execute(
            "INSERT INTO users (id, username, email, is_paid_member) VALUES (?, ?, ?, ?)",
            (user_id, f"user{user_id}", f"user{user_id}@example.com", is_paid_member)
        )
        self.conn.commit()
    
    def create_test_subscription(self, user_id=1, status='active', days_offset=30):
        """テスト用サブスクリプションを作成"""
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=1)
        period_end = now + timedelta(days=days_offset)
        
        self.cursor.execute("""
            INSERT INTO subscriptions (
                user_id, stripe_subscription_id, plan_id, status,
                current_period_start, current_period_end
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, f"sub_{user_id}", "Pro", status, period_start.isoformat(), period_end.isoformat()))
        self.conn.commit()
    
    def create_test_entitlement(self, user_id=1, feature='ocr_google', limit_value='ON'):
        """テスト用エンタイトルメントを作成"""
        self.cursor.execute(
            "INSERT INTO entitlements (user_id, feature, limit_value) VALUES (?, ?, ?)",
            (user_id, feature, limit_value)
        )
        self.conn.commit()
    
    def test_has_active_subscription_true(self):
        """アクティブなサブスクリプションありの場合"""
        self.create_test_user(1)
        self.create_test_subscription(1, 'active', 30)
        
        result = has_active_subscription(1)
        self.assertTrue(result)
    
    def test_has_active_subscription_false_no_subscription(self):
        """サブスクリプションなしの場合"""
        self.create_test_user(1)
        
        result = has_active_subscription(1)
        self.assertFalse(result)
    
    def test_has_active_subscription_false_expired(self):
        """期限切れサブスクリプションの場合"""
        self.create_test_user(1)
        self.create_test_subscription(1, 'active', -1)  # 昨日期限切れ
        
        result = has_active_subscription(1)
        self.assertFalse(result)
    
    def test_has_active_subscription_false_canceled(self):
        """キャンセル済みサブスクリプションの場合"""
        self.create_test_user(1)
        self.create_test_subscription(1, 'canceled', 30)
        
        result = has_active_subscription(1)
        self.assertFalse(result)
    
    def test_has_active_subscription_true_trialing(self):
        """トライアル中サブスクリプションの場合"""
        self.create_test_user(1)
        self.create_test_subscription(1, 'trialing', 30)
        
        result = has_active_subscription(1)
        self.assertTrue(result)
    
    def test_get_user_subscription_status_active(self):
        """アクティブなサブスクリプション状態取得"""
        self.create_test_user(1)
        self.create_test_subscription(1, 'active', 30)
        
        result = get_user_subscription_status(1)
        
        self.assertTrue(result['has_subscription'])
        self.assertEqual(result['status'], 'active')
        self.assertEqual(result['plan_id'], 'Pro')
        self.assertTrue(result['is_active'])
        self.assertFalse(result['cancel_at_period_end'])
    
    def test_get_user_subscription_status_no_subscription(self):
        """サブスクリプションなしの状態取得"""
        self.create_test_user(1)
        
        result = get_user_subscription_status(1)
        
        self.assertFalse(result['has_subscription'])
        self.assertIsNone(result['status'])
        self.assertFalse(result['is_active'])
    
    def test_has_feature_access_true(self):
        """機能アクセス可能な場合"""
        self.create_test_user(1)
        self.create_test_subscription(1, 'active', 30)
        self.create_test_entitlement(1, 'ocr_google', 'ON')
        
        result = has_feature_access(1, 'ocr_google')
        self.assertTrue(result)
    
    def test_has_feature_access_false_no_subscription(self):
        """サブスクリプションなしで機能アクセス不可"""
        self.create_test_user(1)
        self.create_test_entitlement(1, 'ocr_google', 'ON')
        
        result = has_feature_access(1, 'ocr_google')
        self.assertFalse(result)
    
    def test_has_feature_access_false_no_entitlement(self):
        """エンタイトルメントなしで機能アクセス不可"""
        self.create_test_user(1)
        self.create_test_subscription(1, 'active', 30)
        
        result = has_feature_access(1, 'ocr_google')
        self.assertFalse(result)
    
    def test_has_feature_access_false_limit_off(self):
        """エンタイトルメントOFFで機能アクセス不可"""
        self.create_test_user(1)
        self.create_test_subscription(1, 'active', 30)
        self.create_test_entitlement(1, 'ocr_google', 'OFF')
        
        result = has_feature_access(1, 'ocr_google')
        self.assertFalse(result)
    
    def test_grant_default_entitlements(self):
        """デフォルトエンタイトルメント付与"""
        self.create_test_user(1)
        
        result = grant_default_entitlements(1)
        self.assertTrue(result)
        
        # エンタイトルメントが作成されたかチェック
        self.cursor.execute("SELECT feature, limit_value FROM entitlements WHERE user_id = ?", (1,))
        entitlements = self.cursor.fetchall()
        
        self.assertEqual(len(entitlements), 2)
        features = {row['feature']: row['limit_value'] for row in entitlements}
        self.assertEqual(features['ocr_google'], 'ON')
        self.assertEqual(features['ocr_azure'], 'ON')
    
    def test_get_user_entitlements(self):
        """ユーザーエンタイトルメント一覧取得"""
        self.create_test_user(1)
        self.create_test_subscription(1, 'active', 30)
        self.create_test_entitlement(1, 'ocr_google', 'ON')
        self.create_test_entitlement(1, 'ocr_azure', 'OFF')
        
        result = get_user_entitlements(1)
        
        self.assertEqual(len(result), 2)
        
        # ocr_google は ON でアクセス可能
        ocr_google = next(e for e in result if e['feature'] == 'ocr_google')
        self.assertEqual(ocr_google['limit_value'], 'ON')
        self.assertTrue(ocr_google['has_access'])
        
        # ocr_azure は OFF でアクセス不可
        ocr_azure = next(e for e in result if e['feature'] == 'ocr_azure')
        self.assertEqual(ocr_azure['limit_value'], 'OFF')
        self.assertFalse(ocr_azure['has_access'])
    
    def test_check_legacy_paid_member_status_subscription(self):
        """新システム: サブスクリプションによる有料会員判定"""
        self.create_test_user(1, is_paid_member=False)
        self.create_test_subscription(1, 'active', 30)
        
        result = check_legacy_paid_member_status(1)
        self.assertTrue(result)
    
    def test_check_legacy_paid_member_status_legacy_flag(self):
        """旧システム: is_paid_memberフラグによる有料会員判定"""
        self.create_test_user(1, is_paid_member=True)
        
        result = check_legacy_paid_member_status(1)
        self.assertTrue(result)
    
    def test_check_legacy_paid_member_status_neither(self):
        """新旧システム共に有料会員でない場合"""
        self.create_test_user(1, is_paid_member=False)
        
        result = check_legacy_paid_member_status(1)
        self.assertFalse(result)
    
    @patch('entitlements.current_user')
    def test_api_access_required_decorator_success(self, mock_current_user):
        """API機能アクセス制御デコレータ: アクセス許可"""
        from entitlements import api_access_required
        
        # モックユーザー設定
        mock_current_user.is_authenticated = True
        mock_current_user.id = 1
        mock_current_user.is_admin = False
        
        # テストデータ準備
        self.create_test_user(1)
        self.create_test_subscription(1, 'active', 30)
        self.create_test_entitlement(1, 'ocr_google', 'ON')
        
        # テスト用関数にデコレータを適用
        @api_access_required('ocr_google')
        def test_function():\n            return {'success': True, 'message': 'Access granted'}\n        \n        result = test_function()\n        self.assertEqual(result['success'], True)\n    \n    @patch('entitlements.current_user')\n    def test_api_access_required_decorator_admin_access(self, mock_current_user):\n        \"\"\"API機能アクセス制御デコレータ: 管理者アクセス\"\"\"\n        from entitlements import api_access_required\n        \n        # 管理者ユーザー設定\n        mock_current_user.is_authenticated = True\n        mock_current_user.id = 1\n        mock_current_user.is_admin = True\n        \n        self.create_test_user(1)\n        # サブスクリプションやエンタイトルメントなしでも管理者はアクセス可能\n        \n        @api_access_required('ocr_google')\n        def test_function():\n            return {'success': True, 'message': 'Admin access'}\n        \n        result = test_function()\n        self.assertEqual(result['success'], True)\n    \n    @patch('entitlements.jsonify')\n    @patch('entitlements.current_user')\n    def test_api_access_required_decorator_no_subscription(self, mock_current_user, mock_jsonify):\n        \"\"\"API機能アクセス制御デコレータ: サブスクリプションなしでアクセス拒否\"\"\"\n        from entitlements import api_access_required\n        \n        # 非有料ユーザー設定\n        mock_current_user.is_authenticated = True\n        mock_current_user.id = 1\n        mock_current_user.is_admin = False\n        \n        # jsonifyのモック設定\n        mock_response = MagicMock()\n        mock_response.status_code = 402\n        mock_jsonify.return_value = mock_response\n        \n        self.create_test_user(1)\n        # サブスクリプションなし\n        \n        @api_access_required('ocr_google')\n        def test_function():\n            return {'success': True, 'message': 'Should not reach here'}\n        \n        result, status_code = test_function()\n        \n        # アクセス拒否されることを確認\n        self.assertEqual(status_code, 402)\n        mock_jsonify.assert_called_once()\n        call_args = mock_jsonify.call_args[0][0]\n        self.assertFalse(call_args['success'])\n        self.assertEqual(call_args['error_code'], 'SUBSCRIPTION_REQUIRED')\n\nclass TestEntitlementsIntegration(unittest.TestCase):\n    \"\"\"統合テスト\"\"\"\n    \n    def setUp(self):\n        \"\"\"テスト前の初期化\"\"\"\n        # テスト用の一時データベースを作成\n        self.test_db_fd, self.test_db_path = tempfile.mkstemp()\n        \n        # データベース接続をモック\n        self.conn = sqlite3.connect(self.test_db_path)\n        self.conn.row_factory = sqlite3.Row\n        self.cursor = self.conn.cursor()\n        \n        # マイグレーションSQLを実行\n        migration_sql = open(\n            os.path.join(os.path.dirname(__file__), '..', 'migrations', 'add_stripe_subscription_tables.sql')\n        ).read()\n        \n        # SQLを分割して実行（複数のCREATE文があるため）\n        statements = migration_sql.split(';')\n        for statement in statements:\n            statement = statement.strip()\n            if statement and not statement.startswith('--'):\n                try:\n                    self.cursor.execute(statement)\n                except sqlite3.Error as e:\n                    # INSERT文でエラーが出ても続行（テスト用データがないため）\n                    if not statement.upper().startswith('INSERT'):\n                        raise e\n        \n        self.conn.commit()\n        \n        # database.get_db_connection をモック\n        self.db_mock = patch('entitlements.get_db_connection')\n        self.mock_get_db = self.db_mock.start()\n        self.mock_get_db.return_value = self.conn\n    \n    def tearDown(self):\n        \"\"\"テスト後のクリーンアップ\"\"\"\n        self.conn.close()\n        os.close(self.test_db_fd)\n        os.unlink(self.test_db_path)\n        self.db_mock.stop()\n    \n    def test_full_subscription_lifecycle(self):\n        \"\"\"サブスクリプションのライフサイクル全体テスト\"\"\"\n        user_id = 1\n        \n        # 1. ユーザー作成\n        self.cursor.execute(\n            \"INSERT INTO users (id, username, email) VALUES (?, ?, ?)\",\n            (user_id, \"testuser\", \"test@example.com\")\n        )\n        self.conn.commit()\n        \n        # 2. 初期状態: サブスクリプションなし\n        self.assertFalse(has_active_subscription(user_id))\n        self.assertFalse(has_feature_access(user_id, 'ocr_google'))\n        \n        # 3. エンタイトルメント付与\n        self.assertTrue(grant_default_entitlements(user_id))\n        \n        # 4. サブスクリプションなしではまだアクセス不可\n        self.assertFalse(has_feature_access(user_id, 'ocr_google'))\n        \n        # 5. アクティブなサブスクリプション追加\n        now = datetime.now(timezone.utc)\n        period_end = now + timedelta(days=30)\n        self.cursor.execute(\"\"\"\n            INSERT INTO subscriptions (\n                user_id, stripe_subscription_id, plan_id, status,\n                current_period_start, current_period_end\n            ) VALUES (?, ?, ?, ?, ?, ?)\n        \"\"\", (user_id, \"sub_test\", \"Pro\", \"active\", now.isoformat(), period_end.isoformat()))\n        self.conn.commit()\n        \n        # 6. サブスクリプション有効でアクセス可能\n        self.assertTrue(has_active_subscription(user_id))\n        self.assertTrue(has_feature_access(user_id, 'ocr_google'))\n        self.assertTrue(has_feature_access(user_id, 'ocr_azure'))\n        \n        # 7. サブスクリプション状態確認\n        status = get_user_subscription_status(user_id)\n        self.assertTrue(status['is_active'])\n        self.assertEqual(status['status'], 'active')\n        self.assertEqual(status['plan_id'], 'Pro')\n        \n        # 8. エンタイトルメント一覧確認\n        entitlements = get_user_entitlements(user_id)\n        self.assertEqual(len(entitlements), 2)\n        for ent in entitlements:\n            self.assertTrue(ent['has_access'])\n\nif __name__ == '__main__':\n    unittest.main()