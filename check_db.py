import sqlite3
import os
import sys

def print_users():
    """データベース内のすべてのユーザーを表示する"""
    try:
        # データベースファイルのパスを取得
        db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
        db_path = os.path.join(db_dir, 'pdf_paypal.db')
        
        print(f"データベースパス: {db_path}")
        
        if not os.path.exists(db_path):
            print(f"エラー: データベースファイルが見つかりません: {db_path}")
            return
        
        # データベース接続
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # テーブル存在確認
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            print("エラー: usersテーブルが存在しません")
            return
            
        # ユーザー情報を取得
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        
        # カラム名を取得
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        print(f"\nカラム: {columns}")
        print("\nユーザー一覧:")
        if not users:
            print("ユーザーが存在しません")
        else:
            for user in users:
                print("--------------------")
                for i, value in enumerate(user):
                    print(f"{columns[i]}: {value}")
        
        # adminユーザーを再作成するクエリ
        print("\n管理者ユーザーを再作成するSQL:")
        print("DELETE FROM users WHERE username = 'admin';")
        print("INSERT INTO users (username, password, is_admin) VALUES ('admin', 'pbkdf2:sha256:260000$aCcfeAbNzNtJewaT$d9b513b1a9d36f7e92b143f089d88587bc30d9b47f468b1d34d0bbcdefd3d8ff', 1);")
        
    except Exception as e:
        print(f"エラー発生: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

def reset_admin():
    """adminユーザーをリセットする"""
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
        cursor.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
            ('admin', 'pbkdf2:sha256:260000$aCcfeAbNzNtJewaT$d9b513b1a9d36f7e92b143f089d88587bc30d9b47f468b1d34d0bbcdefd3d8ff', 1)
        )
        
        conn.commit()
        print("adminユーザーを正常にリセットしました。ユーザー名: admin, パスワード: admin123")
        
    except Exception as e:
        print(f"エラー発生: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        reset_admin()
    else:
        print_users()
        print("\n管理者ユーザーをリセットするには: python check_db.py --reset")
