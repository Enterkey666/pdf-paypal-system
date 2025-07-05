#!/usr/bin/env python3
"""
adminユーザーのパスワード確認・リセット
"""

import os
import sys
import sqlite3
import hashlib
import secrets

# データベースパス
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'pdf_paypal.db')

def reset_admin_password():
    """adminユーザーのパスワードを簡単なものにリセット"""
    try:
        # Werkzeugがない場合のフォールバック - 単純なハッシュ化
        new_password = "admin123"
        simple_hash = hashlib.sha256(new_password.encode()).hexdigest()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 現在のパスワードハッシュを確認
        cursor.execute("SELECT username, password_hash FROM users WHERE username = 'admin'")
        admin = cursor.fetchone()
        
        if admin:
            print(f"現在のハッシュ: {admin[1][:50]}...")
            
            # 新しいパスワードハッシュに更新（簡易版）
            cursor.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'", (f"simple:{simple_hash}",))
            conn.commit()
            
            print(f"✅ adminパスワードを {new_password} にリセットしました")
            print(f"新しいハッシュ: simple:{simple_hash[:20]}...")
        else:
            print("❌ adminユーザーが見つかりません")
            
    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        conn.close()

def create_simple_admin():
    """簡単な認証を使う新しいadminユーザーを作成"""
    try:
        password = "admin123"
        simple_hash = hashlib.sha256(password.encode()).hexdigest()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 既存のadminユーザーを削除
        cursor.execute("DELETE FROM users WHERE username = 'admin'")
        
        # 新しいadminユーザーを作成
        cursor.execute(
            "INSERT INTO users (username, password_hash, is_admin, is_active) VALUES (?, ?, ?, ?)",
            ('admin', f'simple:{simple_hash}', 1, 1)
        )
        conn.commit()
        
        print(f"✅ 新しいadminユーザーを作成しました")
        print(f"   ユーザー名: admin")
        print(f"   パスワード: {password}")
        
    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("1. パスワードリセット")
    print("2. 新しいadminユーザー作成")
    
    # 新しいadminユーザーを作成
    create_simple_admin()