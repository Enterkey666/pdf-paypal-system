import sqlite3
import os
import sys
from werkzeug.security import generate_password_hash

def reset_admin_with_werkzeug():
    """Werkzeugのgenerate_password_hashを使用してadminユーザーをリセットする"""
    try:
        # データベースファイルのパスを取得
        db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
        db_path = os.path.join(db_dir, 'pdf_paypal.db')
        
        if not os.path.exists(db_path):
            print(f"エラー: データベースファイルが見つかりません: {db_path}")
            return
        
        # データベース接続
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # adminユーザーを削除
        cursor.execute("DELETE FROM users WHERE username = 'admin'")
        
        # 新しいadminユーザーを作成 (パスワード: admin123)
        # Werkzeugのgenerate_password_hashを使用 - このアプリで実際に使用されている方法
        password_hash = generate_password_hash('admin123')
        cursor.execute(
            "INSERT INTO users (username, password_hash, is_admin, is_active) VALUES (?, ?, ?, ?)",
            ('admin', password_hash, 1, 1)
        )
        
        conn.commit()
        print(f"adminユーザーを正常にリセットしました。ユーザー名: admin, パスワード: admin123")
        print(f"使用したハッシュ: {password_hash}")
        
    except Exception as e:
        print(f"エラー発生: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    reset_admin_with_werkzeug()
