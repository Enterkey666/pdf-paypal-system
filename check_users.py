#!/usr/bin/env python3
"""
ユーザー情報確認スクリプト
"""

import os
import sys
import sqlite3

# データベースパス
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'pdf_paypal.db')

def check_users():
    """データベース内のユーザー情報を確認"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # usersテーブルの存在確認
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        if not cursor.fetchone():
            print("❌ usersテーブルが存在しません")
            return
        
        print("✅ usersテーブルが存在します")
        
        # すべてのユーザーを取得
        cursor.execute("SELECT id, username, email, is_admin, is_active, created_at FROM users")
        users = cursor.fetchall()
        
        print(f"\n📊 登録ユーザー数: {len(users)}")
        
        for user in users:
            print(f"ID: {user[0]}, ユーザー名: {user[1]}, メール: {user[2]}, 管理者: {bool(user[3])}, アクティブ: {bool(user[4])}, 作成日: {user[5]}")
        
        # adminユーザーの詳細確認
        cursor.execute("SELECT id, username, password_hash, email, created_at, last_login, is_admin, is_active FROM users WHERE username = 'admin'")
        admin = cursor.fetchone()
        
        if admin:
            print(f"\n🔑 adminユーザーが見つかりました:")
            print(f"   ID: {admin[0]}")
            print(f"   ユーザー名: {admin[1]}")
            print(f"   パスワードハッシュ: {admin[2][:20]}...")
            print(f"   メール: {admin[3]}")
            print(f"   管理者: {bool(admin[6])}")
            print(f"   アクティブ: {bool(admin[7])}")
        else:
            print("\n❌ adminユーザーが見つかりません")
            
    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_users()