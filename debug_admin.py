#!/usr/bin/env python3
"""
adminユーザーのデバッグと修正
"""

import os
import sys
import sqlite3

# データベースパス
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'pdf_paypal.db')

def debug_admin():
    """adminユーザーの詳細な状況を確認して修正"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # テーブル構造を確認
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        print("📋 usersテーブルの構造:")
        for col in columns:
            print(f"   {col[1]} ({col[2]}) - デフォルト: {col[4]}")
        
        # adminユーザーの生データを確認
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        admin = cursor.fetchone()
        
        if admin:
            print(f"\n🔍 adminユーザーの生データ:")
            column_names = [col[1] for col in columns]
            for i, col_name in enumerate(column_names):
                print(f"   {col_name}: {admin[i]}")
            
            # is_activeカラムの位置を確認
            is_active_index = None
            for i, col in enumerate(columns):
                if col[1] == 'is_active':
                    is_active_index = i
                    break
            
            if is_active_index is not None:
                current_is_active = admin[is_active_index]
                print(f"\n現在のis_active値: {current_is_active} (型: {type(current_is_active)})")
                
                # 強制的に1に設定
                cursor.execute("UPDATE users SET is_active = 1 WHERE username = 'admin'")
                conn.commit()
                print("✅ is_activeを1に強制設定しました")
                
                # 再確認
                cursor.execute("SELECT * FROM users WHERE username = 'admin'")
                admin_updated = cursor.fetchone()
                new_is_active = admin_updated[is_active_index]
                print(f"更新後のis_active値: {new_is_active} (型: {type(new_is_active)})")
            else:
                print("❌ is_activeカラムが見つかりません")
        else:
            print("❌ adminユーザーが見つかりません")
            
    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    debug_admin()