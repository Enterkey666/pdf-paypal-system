#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SaaS対応データベース管理モジュール
マルチテナント対応のデータベーススキーマとモデル
"""

import os
import json
import sqlite3
import logging
import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from enum import Enum

# ロガーの設定
logger = logging.getLogger(__name__)

# データベースのパス
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'saas_pdf_paypal.db')

class SubscriptionPlan(Enum):
    """サブスクリプションプラン"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class TenantStatus(Enum):
    """テナントステータス"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    EXPIRED = "expired"

def ensure_db_dir():
    """データベースディレクトリが存在することを確認"""
    db_dir = os.path.dirname(DB_PATH)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logger.info(f"データベースディレクトリを作成しました: {db_dir}")

def get_db_connection():
    """データベース接続を取得"""
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_saas_db():
    """SaaS対応データベースの初期化"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # テナント（組織）テーブル作成
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subdomain TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'trial',
            subscription_plan TEXT DEFAULT 'free',
            max_users INTEGER DEFAULT 5,
            max_monthly_files INTEGER DEFAULT 100,
            monthly_files_used INTEGER DEFAULT 0,
            storage_limit_gb INTEGER DEFAULT 1,
            storage_used_mb INTEGER DEFAULT 0,
            trial_end_date TIMESTAMP,
            subscription_start_date TIMESTAMP,
            subscription_end_date TIMESTAMP,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # ユーザーテーブル（マルチテナント対応）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            first_name TEXT,
            last_name TEXT,
            role TEXT DEFAULT 'member',
            is_tenant_admin BOOLEAN DEFAULT 0,
            is_super_admin BOOLEAN DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            email_verified BOOLEAN DEFAULT 0,
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id),
            UNIQUE(tenant_id, username)
        )
        ''')
        
        # PayPal設定テーブル（テナント単位）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tenant_paypal_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            client_id TEXT NOT NULL,
            client_secret TEXT NOT NULL,
            mode TEXT DEFAULT 'sandbox',
            default_currency TEXT DEFAULT 'JPY',
            webhook_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id)
        )
        ''')
        
        # 処理履歴テーブル（テナント・ユーザー単位）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS processing_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_size_mb REAL,
            customer_name TEXT,
            amount REAL,
            paypal_link TEXT,
            status TEXT,
            error_message TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        # API トークンテーブル
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            permissions TEXT,
            last_used TIMESTAMP,
            expires_at TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        # 使用量追跡テーブル
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS usage_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_id INTEGER,
            action_type TEXT NOT NULL,
            resource_type TEXT,
            quantity INTEGER DEFAULT 1,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        # サブスクリプション履歴テーブル
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscription_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            plan_name TEXT NOT NULL,
            status TEXT NOT NULL,
            stripe_subscription_id TEXT,
            amount REAL,
            currency TEXT DEFAULT 'JPY',
            period_start TIMESTAMP,
            period_end TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id)
        )
        ''')
        
        # 招待テーブル
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            invited_by INTEGER NOT NULL,
            email TEXT NOT NULL,
            role TEXT DEFAULT 'member',
            token TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending',
            expires_at TIMESTAMP,
            accepted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id),
            FOREIGN KEY (invited_by) REFERENCES users (id)
        )
        ''')
        
        conn.commit()
        logger.info("SaaS対応データベースを初期化しました")
        
        # デフォルトテナントとスーパー管理者の作成
        create_default_tenant_and_admin()
        
    except Exception as e:
        logger.error(f"SaaS データベース初期化エラー: {str(e)}")
    finally:
        conn.close()

def create_default_tenant_and_admin():
    """デフォルトテナントとスーパー管理者を作成"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # デフォルトテナントが存在するか確認
        cursor.execute("SELECT * FROM tenants WHERE subdomain = 'admin'")
        admin_tenant = cursor.fetchone()
        
        if not admin_tenant:
            # デフォルトテナントを作成
            cursor.execute(
                """INSERT INTO tenants 
                (name, subdomain, status, subscription_plan, max_users, max_monthly_files, storage_limit_gb)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ('System Admin', 'admin', 'active', 'enterprise', 10, 10000, 100)
            )
            tenant_id = cursor.lastrowid
            logger.info(f"デフォルトテナントを作成しました: ID {tenant_id}")
        else:
            tenant_id = admin_tenant['id']
        
        # スーパー管理者が存在するか確認
        cursor.execute("SELECT * FROM users WHERE is_super_admin = 1")
        super_admin = cursor.fetchone()
        
        if not super_admin:
            # スーパー管理者パスワードを環境変数または生成
            admin_password = os.environ.get('SUPER_ADMIN_PASSWORD', secrets.token_hex(12))
            admin_email = os.environ.get('SUPER_ADMIN_EMAIL', 'admin@system.local')
            
            # スーパー管理者を作成
            cursor.execute(
                """INSERT INTO users 
                (tenant_id, username, email, password_hash, first_name, last_name, 
                role, is_tenant_admin, is_super_admin, is_active, email_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tenant_id, 'superadmin', admin_email, generate_password_hash(admin_password), 
                'Super', 'Admin', 'admin', True, True, True, True)
            )
            conn.commit()
            
            logger.info(f"スーパー管理者を作成しました。Email: {admin_email}, Password: {admin_password}")
        else:
            logger.info("スーパー管理者は既に存在します")
            
    except Exception as e:
        logger.error(f"デフォルトテナント・管理者作成エラー: {str(e)}")
    finally:
        conn.close()

# SaaS対応ユーザークラス
class SaaSUser(UserMixin):
    def __init__(self, id, tenant_id, username, email, password_hash, 
                 first_name=None, last_name=None, role='member', 
                 is_tenant_admin=False, is_super_admin=False, is_active=True):
        self.id = id
        self.tenant_id = tenant_id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.is_tenant_admin = is_tenant_admin
        self.is_super_admin = is_super_admin
        self._is_active = is_active
    
    def get_id(self):
        return str(self.id)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_active(self):
        return self._is_active
    
    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username

def create_tenant(name, subdomain, admin_email, admin_password, plan='trial'):
    """新しいテナントを作成"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # サブドメインの重複確認
        cursor.execute("SELECT * FROM tenants WHERE subdomain = ?", (subdomain,))
        if cursor.fetchone():
            return False, "サブドメインは既に使用されています"
        
        # テナント作成
        trial_end = datetime.now() + timedelta(days=14)  # 14日間トライアル
        cursor.execute(
            """INSERT INTO tenants 
            (name, subdomain, status, subscription_plan, trial_end_date)
            VALUES (?, ?, ?, ?, ?)""",
            (name, subdomain, 'trial', plan, trial_end)
        )
        tenant_id = cursor.lastrowid
        
        # テナント管理者ユーザー作成
        cursor.execute(
            """INSERT INTO users 
            (tenant_id, username, email, password_hash, role, is_tenant_admin, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, subdomain + '_admin', admin_email, generate_password_hash(admin_password), 
            'admin', True, True)
        )
        
        conn.commit()
        logger.info(f"新しいテナントを作成しました: {name} ({subdomain})")
        return True, tenant_id
        
    except Exception as e:
        logger.error(f"テナント作成エラー: {str(e)}")
        return False, str(e)
    finally:
        conn.close()

def get_tenant_by_subdomain(subdomain):
    """サブドメインからテナント情報を取得"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM tenants WHERE subdomain = ?", (subdomain,))
        tenant = cursor.fetchone()
        
        return dict(tenant) if tenant else None
    except Exception as e:
        logger.error(f"テナント取得エラー: {str(e)}")
        return None
    finally:
        conn.close()

def check_tenant_limits(tenant_id, action_type):
    """テナントの使用量制限をチェック"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # テナント情報を取得
        cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
        tenant = cursor.fetchone()
        
        if not tenant:
            return False, "テナントが見つかりません"
        
        if action_type == 'file_processing':
            if tenant['monthly_files_used'] >= tenant['max_monthly_files']:
                return False, "月間ファイル処理数の上限に達しています"
        
        return True, "制限内です"
        
    except Exception as e:
        logger.error(f"制限チェックエラー: {str(e)}")
        return False, str(e)
    finally:
        conn.close()

def increment_usage(tenant_id, action_type, quantity=1, user_id=None, metadata=None):
    """使用量を増加"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 使用量追跡に記録
        cursor.execute(
            """INSERT INTO usage_tracking 
            (tenant_id, user_id, action_type, quantity, metadata)
            VALUES (?, ?, ?, ?, ?)""",
            (tenant_id, user_id, action_type, quantity, json.dumps(metadata) if metadata else None)
        )
        
        # テナントの使用量更新
        if action_type == 'file_processing':
            cursor.execute(
                "UPDATE tenants SET monthly_files_used = monthly_files_used + ? WHERE id = ?",
                (quantity, tenant_id)
            )
        
        conn.commit()
        return True
        
    except Exception as e:
        logger.error(f"使用量更新エラー: {str(e)}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    # ロガーの設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # SaaSデータベースの初期化
    init_saas_db()
    logger.info("SaaS データベースの初期化が完了しました")