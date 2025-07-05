#!/usr/bin/env python3
"""
adminユーザーを有効化するスクリプト
"""

import os
import sys
import sqlite3

# データベースパス
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'pdf_paypal.db')

def fix_admin():
    """adminユーザーを有効化"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # adminユーザーを有効化
        cursor.execute("UPDATE users SET is_active = 1 WHERE username = 'admin'")
        conn.commit()
        
        print("✅ adminユーザーを有効化しました")
        
        # 確認
        cursor.execute("SELECT username, is_admin, is_active FROM users WHERE username = 'admin'")
        admin = cursor.fetchone()
        
        if admin:
            print(f"確認: ユーザー名={admin[0]}, 管理者={bool(admin[1])}, アクティブ={bool(admin[2])}")
        
    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_admin()