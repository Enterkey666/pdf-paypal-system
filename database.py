#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
データベース管理モジュール
ユーザーアカウントとPayPal設定を管理するためのSQLiteデータベース
"""

import os
import json
import sqlite3
import logging
import secrets
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# ロガーの設定
logger = logging.getLogger(__name__)

# データベースのパス
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'pdf_paypal.db')

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

def init_db():
    """データベースの初期化"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # ユーザーテーブル作成
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_admin BOOLEAN DEFAULT 0,
            is_active BOOLEAN DEFAULT 1
        )
        ''')
        
        # PayPal設定テーブル作成
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS paypal_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            client_id TEXT NOT NULL,
            client_secret TEXT NOT NULL,
            mode TEXT DEFAULT 'sandbox',
            default_currency TEXT DEFAULT 'JPY',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        # 処理履歴テーブル作成
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS processing_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            customer_name TEXT,
            amount REAL,
            paypal_link TEXT,
            status TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        conn.commit()
        logger.info("データベースを初期化しました")
        
        # デフォルト管理者ユーザーの作成
        create_default_admin()
        
    except Exception as e:
        logger.error(f"データベース初期化エラー: {str(e)}")
    finally:
        conn.close()

def create_default_admin():
    """デフォルトの管理者ユーザーを作成"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 管理者ユーザーが存在するか確認
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        admin = cursor.fetchone()
        
        if not admin:
            # 環境変数から管理者パスワードを取得、または安全なパスワードを生成
            admin_password = os.environ.get('ADMIN_PASSWORD', secrets.token_hex(8))
            
            # 管理者ユーザーを作成
            cursor.execute(
                "INSERT INTO users (username, password_hash, is_admin, is_active) VALUES (?, ?, ?, ?)",
                ('admin', generate_password_hash(admin_password), True, True)
            )
            conn.commit()
            
            logger.info(f"デフォルト管理者ユーザーを作成しました。パスワード: {admin_password}")
        else:
            logger.info("管理者ユーザーは既に存在します")
            
    except Exception as e:
        logger.error(f"管理者ユーザー作成エラー: {str(e)}")
    finally:
        conn.close()

# ユーザー管理関数
def create_user(username, password, email=None, is_admin=False):
    """新しいユーザーを作成"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ユーザー名が既に存在するか確認
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return False, "ユーザー名は既に使用されています"
        
        # メールアドレスが既に存在するか確認（メールアドレスが提供された場合）
        if email:
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                return False, "メールアドレスは既に使用されています"
        
        # ユーザーを作成
        cursor.execute(
            "INSERT INTO users (username, password_hash, email, is_admin) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), email, is_admin)
        )
        conn.commit()
        
        user_id = cursor.lastrowid
        logger.info(f"新しいユーザーを作成しました: {username} (ID: {user_id})")
        
        return True, user_id
    except Exception as e:
        logger.error(f"ユーザー作成エラー: {str(e)}")
        return False, str(e)
    finally:
        conn.close()

def authenticate_user(username, password):
    """ユーザー認証"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ユーザーを検索
        cursor.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,))
        user = cursor.fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            # 最終ログイン時間を更新
            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (user['id'],)
            )
            conn.commit()
            
            # ユーザー情報を辞書に変換
            user_dict = dict(user)
            logger.info(f"ユーザー認証成功: {username}")
            return True, user_dict
        else:
            logger.warning(f"ユーザー認証失敗: {username}")
            return False, "ユーザー名またはパスワードが正しくありません"
    except Exception as e:
        logger.error(f"認証エラー: {str(e)}")
        return False, str(e)
    finally:
        conn.close()

def get_user(user_id):
    """ユーザー情報を取得"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
        if user:
            return dict(user)
        else:
            return None
    except Exception as e:
        logger.error(f"ユーザー取得エラー: {str(e)}")
        return None
    finally:
        conn.close()

def admin_user_exists():
    """管理者権限を持つユーザーが存在するか確認
    
    Returns:
        bool: 管理者権限を持つユーザーが存在すればTrue、それ以外はフォールFalse
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        count = cursor.fetchone()[0]
        return count > 0
    finally:
        cursor.close()
        conn.close()

# ユーザー認証関連の関数
def get_user_by_username(username):
    """ユーザー名からユーザー情報を取得する
    
    Args:
        username (str): ユーザー名
        
    Returns:
        dict or None: ユーザー情報、ユーザーが見つからない場合はNone
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, username, password_hash, is_admin, created_at FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if user:
            return {
                'id': user[0],
                'username': user[1],
                'password_hash': user[2],
                'is_admin': bool(user[3]),
                'created_at': user[4]
            }
        return None
    finally:
        cursor.close()
        conn.close()
        
def get_user_by_id(user_id):
    """ユーザーIDからユーザー情報を取得する
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        dict or None: ユーザー情報、ユーザーが見つからない場合はNone
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, username, password_hash, is_admin, created_at FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if user:
            return {
                'id': user[0],
                'username': user[1],
                'password_hash': user[2],
                'is_admin': bool(user[3]),
                'created_at': user[4]
            }
        return None
    finally:
        cursor.close()
        conn.close()

def create_user(username, password_hash, is_admin=False):
    """新規ユーザーを作成する
    
    Args:
        username (str): ユーザー名
        password_hash (str): パスワードハッシュ
        is_admin (bool): 管理者権限フラグ
        
    Returns:
        int: 作成されたユーザーID
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)',
            (username, password_hash, 1 if is_admin else 0, now)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()

def update_user_password(user_id, new_password_hash):
    """ユーザーのパスワードを更新する
    
    Args:
        user_id (int): ユーザーID
        new_password_hash (str): 新しいパスワードのハッシュ
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_password_hash, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def delete_user(user_id):
    """ユーザーを削除する
    
    Args:
        user_id (int): 削除するユーザーのID
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
        
def get_or_create_google_user(email, name, picture):
    """メールアドレスからGoogleユーザーを取得または作成する
    
    Args:
        email (str): ユーザーのメールアドレス
        name (str): ユーザーの表示名
        picture (str): ユーザーのプロフィール画像のURL
        
    Returns:
        dict or None: ユーザー情報、作成に失敗した場合はNone
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # メールアドレスでユーザーを検索
        cursor.execute('SELECT id, username, is_admin, created_at FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        if user:
            # 既存ユーザーの場合、情報を更新
            user_id = user[0]
            cursor.execute('UPDATE users SET picture_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                         (picture, user_id))
            conn.commit()
            
            return {
                'id': user[0],
                'username': user[1],
                'is_admin': bool(user[2]),
                'created_at': user[3],
                'email': email,
                'picture': picture
            }
        else:
            # 新規ユーザー作成
            username = email.split('@')[0]  # メールアドレスの@前をユーザー名として使用
            
            # 新しいユーザーを登録
            is_admin = False
            
            # ドメインが指定の場合、管理者権限を付与
            admin_domains = os.environ.get('ADMIN_DOMAINS', '').split(',')
            if any(email.lower().endswith(f'@{domain.strip().lower()}') for domain in admin_domains if domain.strip()):
                is_admin = True
                logger.info(f"管理者ドメインに一致したため管理者権限を付与しました: {email}")
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                'INSERT INTO users (username, email, oauth_provider, picture_url, is_admin, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                (username, email, 'google', picture, 1 if is_admin else 0, now)
            )
            conn.commit()
            
            # 新規作成したユーザー情報を取得
            user_id = cursor.lastrowid
            return {
                'id': user_id,
                'username': username,
                'is_admin': is_admin,
                'created_at': now,
                'email': email,
                'picture': picture
            }
    except Exception as e:
        logger.error(f"Googleユーザー取得/作成エラー: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()
        
def ensure_google_user_table():
    """ユーザーテーブルにGoogle認証関連のカラムがあるか確認し、なければ追加する
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # ユーザーテーブルのカラム情報を取得
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 必要なカラムを追加
        if 'email' not in column_names:
            cursor.execute('ALTER TABLE users ADD COLUMN email TEXT')
            logger.info("usersテーブルにemailカラムを追加しました")
            
        if 'oauth_provider' not in column_names:
            cursor.execute('ALTER TABLE users ADD COLUMN oauth_provider TEXT')
            logger.info("usersテーブルにoauth_providerカラムを追加しました")
            
        if 'picture_url' not in column_names:
            cursor.execute('ALTER TABLE users ADD COLUMN picture_url TEXT')
            logger.info("usersテーブルにpicture_urlカラムを追加しました")
            
        if 'updated_at' not in column_names:
            cursor.execute('ALTER TABLE users ADD COLUMN updated_at TEXT')
            logger.info("usersテーブルにupdated_atカラムを追加しました")
            
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Googleユーザーテーブル更新エラー: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()

# PayPal設定管理関数
def save_paypal_settings(user_id, settings):
    """ユーザーのPayPal設定を保存
    
    Args:
        user_id (int): ユーザーID
        settings (dict): PayPal設定辞書 {'client_id': '...', 'client_secret': '...', 'mode': '...', 'currency': '...'}
    
    Returns:
        tuple: (成功したかフラグ, メッセージ)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 設定値を取得
        client_id = settings.get('client_id', '')
        client_secret = settings.get('client_secret', '')
        mode = settings.get('mode', 'sandbox')
        default_currency = settings.get('currency', 'JPY')
        
        # 既存の設定を確認
        cursor.execute("SELECT * FROM paypal_settings WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            # 既存の設定を更新
            cursor.execute(
                """UPDATE paypal_settings 
                SET client_id = ?, client_secret = ?, mode = ?, default_currency = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?""",
                (client_id, client_secret, mode, default_currency, user_id)
            )
        else:
            # 新しい設定を作成
            cursor.execute(
                """INSERT INTO paypal_settings 
                (user_id, client_id, client_secret, mode, default_currency)
                VALUES (?, ?, ?, ?, ?)""",
                (user_id, client_id, client_secret, mode, default_currency)
            )
        
        conn.commit()
        logger.info(f"PayPal設定を保存しました: ユーザーID {user_id}")
        return True, "PayPal設定を保存しました"
    except Exception as e:
        logger.error(f"PayPal設定保存エラー: {str(e)}")
        return False, str(e)
    finally:
        conn.close()

def get_paypal_settings(user_id):
    """ユーザーのPayPal設定を取得
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        dict or None: PayPal設定辞書、設定がない場合はNone
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # カラム名を照会するためにクエリを変更
        cursor.execute("SELECT user_id, client_id, client_secret, mode, default_currency, created_at, updated_at FROM paypal_settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if row:
            # カラム名で辞書を作成
            column_names = ['user_id', 'client_id', 'client_secret', 'mode', 'default_currency', 'created_at', 'updated_at']
            settings = {}
            for i, col_name in enumerate(column_names):
                # currencyキーをクライアント側の使用から含む
                if col_name == 'default_currency':
                    settings['currency'] = row[i]
                else:
                    settings[col_name] = row[i]
            return settings
        else:
            return None
    except Exception as e:
        logger.error(f"PayPal設定取得エラー: {str(e)}")
        return None
    finally:
        conn.close()

# 処理履歴管理関数
def save_processing_history(user_id, filename, customer_name, amount, paypal_link, status):
    """処理履歴を保存"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """INSERT INTO processing_history 
            (user_id, filename, customer_name, amount, paypal_link, status)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, filename, customer_name, amount, paypal_link, status)
        )
        
        conn.commit()
        logger.info(f"処理履歴を保存しました: ユーザーID {user_id}, ファイル {filename}")
        return True
    except Exception as e:
        logger.error(f"処理履歴保存エラー: {str(e)}")
        return False
    finally:
        conn.close()

def get_user_processing_history(user_id, limit=50):
    """ユーザーの処理履歴を取得"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM processing_history WHERE user_id = ? ORDER BY processed_at DESC LIMIT ?",
            (user_id, limit)
        )
        history = cursor.fetchall()
        
        return [dict(item) for item in history]
    except Exception as e:
        logger.error(f"処理履歴取得エラー: {str(e)}")
        return []
    finally:
        conn.close()

def update_payment_status(order_id, status, payment_id=None, user_id=None):
    """
    処理履歴のPayPal注文ステータスを更新する
    
    Args:
        order_id (str): PayPal注文ID
        status (str): 新しいステータス (APPROVED, COMPLETED, DENIED など)
        payment_id (str, optional): PayPal支払いID
        user_id (int, optional): ユーザーID
        
    Returns:
        tuple: (成功したかどうか, メッセージ)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # order_idに一致する処理履歴を検索
        if user_id:
            # 特定ユーザーの履歴のみ検索
            cursor.execute(
                "SELECT * FROM processing_history WHERE paypal_link LIKE ? AND user_id = ?",
                (f"%{order_id}%", user_id)
            )
        else:
            # 全ユーザーの履歴を検索
            cursor.execute(
                "SELECT * FROM processing_history WHERE paypal_link LIKE ?",
                (f"%{order_id}%",)
            )
        
        history = cursor.fetchone()
        
        if history:
            # ステータス更新
            payment_info = {
                'status': status,
                'updated_at': datetime.now().isoformat()
            }
            
            if payment_id:
                payment_info['payment_id'] = payment_id
                
            # 既存のJSONデータがあれば更新
            current_status = history['status']
            if current_status and current_status.startswith('{'): 
                try:
                    status_data = json.loads(current_status)
                    status_data.update(payment_info)
                    new_status = json.dumps(status_data)
                except:
                    new_status = json.dumps(payment_info)
            else:
                new_status = json.dumps(payment_info)
                
            # データベース更新
            cursor.execute(
                "UPDATE processing_history SET status = ? WHERE id = ?",
                (new_status, history['id'])
            )
            
            conn.commit()
            logger.info(f"支払いステータス更新: 注文ID {order_id}, 新ステータス: {status}")
            return True, f"支払いステータスを更新しました: {status}"
        else:
            logger.warning(f"注文ID {order_id} に一致する処理履歴が見つかりませんでした")
            return False, "対象の処理履歴が見つかりません"
            
    except Exception as e:
        logger.error(f"支払いステータス更新エラー: {str(e)}")
        return False, str(e)
    finally:
        conn.close()


def get_payment_status_by_order_id(order_id, user_id=None):
    """
    注文IDに対応する支払いステータスを取得する
    
    Args:
        order_id (str): PayPal注文ID
        user_id (int, optional): ユーザーID
        
    Returns:
        dict: 支払いステータス情報
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # order_idに一致する処理履歴を検索
        if user_id:
            # 特定ユーザーの履歴のみ検索
            cursor.execute(
                "SELECT * FROM processing_history WHERE paypal_link LIKE ? AND user_id = ?",
                (f"%{order_id}%", user_id)
            )
        else:
            # 全ユーザーの履歴を検索
            cursor.execute(
                "SELECT * FROM processing_history WHERE paypal_link LIKE ?",
                (f"%{order_id}%",)
            )
        
        history = cursor.fetchone()
        
        if history:
            history_dict = dict(history)
            
            # ステータスがJSON形式の場合はパース
            if history_dict['status'] and history_dict['status'].startswith('{'): 
                try:
                    history_dict['status'] = json.loads(history_dict['status'])
                except:
                    pass
                    
            return {'success': True, 'data': history_dict}
        else:
            return {'success': False, 'error': '対象の処理履歴が見つかりません'}
            
    except Exception as e:
        logger.error(f"支払いステータス取得エラー: {str(e)}")
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()

# データベースの初期化（モジュールインポート時に実行）
if __name__ == "__main__":
    # ロガーの設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # データベースの初期化
    init_db()
    logger.info("データベースの初期化が完了しました")
