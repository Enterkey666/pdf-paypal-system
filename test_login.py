#!/usr/bin/env python3
"""
ログイン機能のテスト
"""

import os
import sys

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def test_login():
    """ログイン機能をテスト"""
    try:
        import database
        
        print("🔍 adminユーザーの認証テスト")
        
        # ユーザー名でユーザーを取得
        user = database.get_user_by_username("admin")
        
        if user:
            print(f"✅ ユーザー取得成功:")
            print(f"   ID: {user.id}")
            print(f"   ユーザー名: {user.username}")
            print(f"   管理者: {user.is_admin}")
            print(f"   アクティブ: {user.is_active}")
            print(f"   認証済み: {user.is_authenticated}")
            
            # パスワード確認
            if user.check_password("admin123"):
                print("✅ パスワード認証成功")
            else:
                print("❌ パスワード認証失敗")
                
            # Flask-Loginの要件確認
            print(f"\n🔑 Flask-Login要件チェック:")
            print(f"   get_id(): {user.get_id()}")
            print(f"   is_authenticated: {user.is_authenticated}")
            print(f"   is_active: {user.is_active}")
            print(f"   is_anonymous: {getattr(user, 'is_anonymous', 'N/A')}")
        else:
            print("❌ adminユーザーが見つかりません")
            
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_login()