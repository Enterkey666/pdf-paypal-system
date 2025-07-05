#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ファイル存在確認スクリプト
Cloud Runコンテナ内で必要なファイルが存在するか確認します
"""

import os
import sys

def verify_required_files():
    """必要なファイルの存在確認"""
    print("🔍 Required Files Verification")
    print("=" * 50)
    
    required_files = [
        'app.py',
        'payment_status_checker.py',
        'payment_status_updater.py',
        'paypal_utils.py',
        'database.py',
        'config_manager.py',
        'requirements.txt',
        'Dockerfile'
    ]
    
    missing_files = []
    
    for file_name in required_files:
        if os.path.exists(file_name):
            file_size = os.path.getsize(file_name)
            print(f"✓ {file_name} ({file_size:,} bytes)")
        else:
            print(f"✗ {file_name} - NOT FOUND")
            missing_files.append(file_name)
    
    return missing_files

def check_python_path():
    """PYTHONPATHの確認"""
    print("\n🐍 Python Path Check")
    print("=" * 50)
    
    print("Current working directory:", os.getcwd())
    print("Python path:")
    for i, path in enumerate(sys.path):
        print(f"  {i}: {path}")
    
    # 環境変数PYTHONPATHの確認
    pythonpath = os.environ.get('PYTHONPATH', 'Not set')
    print(f"PYTHONPATH environment variable: {pythonpath}")

def test_imports():
    """インポートテスト"""
    print("\n📦 Import Test")
    print("=" * 50)
    
    import_tests = [
        ('flask', 'Flask'),
        ('payment_status_checker', 'check_payment_status'),
        ('paypal_utils', 'get_paypal_access_token'),
    ]
    
    results = []
    
    for module_name, item_name in import_tests:
        try:
            module = __import__(module_name)
            if hasattr(module, item_name):
                print(f"✓ {module_name}.{item_name}")
                results.append(True)
            else:
                print(f"⚠ {module_name} imported but {item_name} not found")
                results.append(False)
        except ImportError as e:
            print(f"✗ {module_name} - Import failed: {e}")
            results.append(False)
    
    return results

def generate_diagnostic_info():
    """診断情報の生成"""
    print("\n🩺 Diagnostic Information")
    print("=" * 50)
    
    # Python情報
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")
    
    # 環境変数
    env_vars = ['PORT', 'PYTHONPATH', 'PATH']
    for var in env_vars:
        value = os.environ.get(var, 'Not set')
        print(f"{var}: {value}")
    
    # ディレクトリ内容
    print("\nCurrent directory contents:")
    try:
        files = os.listdir('.')
        python_files = [f for f in files if f.endswith('.py')]
        print(f"Total files: {len(files)}")
        print(f"Python files: {len(python_files)}")
        
        if python_files:
            print("Python files found:")
            for i, py_file in enumerate(sorted(python_files)[:10]):  # 最初の10個のみ表示
                print(f"  {i+1}: {py_file}")
            if len(python_files) > 10:
                print(f"  ... and {len(python_files) - 10} more")
    except Exception as e:
        print(f"Error listing directory: {e}")

def main():
    """メイン実行"""
    print("🧪 Cloud Run File Verification")
    print("=" * 70)
    
    # ファイル存在確認
    missing_files = verify_required_files()
    
    # PYTHONPATHチェック
    check_python_path()
    
    # インポートテスト
    import_results = test_imports()
    
    # 診断情報
    generate_diagnostic_info()
    
    # 結果サマリー
    print("\n" + "=" * 70)
    print("📊 Summary")
    print("-" * 30)
    
    if missing_files:
        print(f"❌ Missing files: {', '.join(missing_files)}")
    else:
        print("✅ All required files found")
    
    successful_imports = sum(import_results)
    total_imports = len(import_results)
    print(f"📦 Import tests: {successful_imports}/{total_imports} passed")
    
    if missing_files or successful_imports < total_imports:
        print("\n⚠️  Issues detected. Check the output above for details.")
        return False
    else:
        print("\n✅ All checks passed!")
        return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)