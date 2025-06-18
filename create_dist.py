#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配布用パッケージ作成スクリプト
PDF処理 & PayPal決済リンク発行システム

このスクリプトは、アプリケーションを配布用のZIPファイルにパッケージングします。
必要なファイルのみを含め、ドキュメントと簡単なインストール手順も同梱します。
"""

import os
import sys
import shutil
import zipfile
import logging
from datetime import datetime

# ロガー設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# バージョン情報
VERSION = "1.0.0"

# 作成日
BUILD_DATE = datetime.now().strftime("%Y-%m-%d")

# 配布物に含めるファイルとディレクトリのリスト
INCLUDE_FILES = [
    "app.py",
    "extractors.py",
    "config_manager.py",
    "requirements.txt",
    "README.md",
    ".env.example",
    "start_app.bat",
    "create_shortcut.bat",
]

# 含めるディレクトリ
INCLUDE_DIRS = [
    "templates",
    "static",
]

# 除外するファイル/ディレクトリのパターン
EXCLUDE_PATTERNS = [
    "__pycache__",
    ".git",
    ".vscode",
    ".env",
    "*.pyc",
    "*.log",
    "uploads/*",
    "results/*",
    "dist",
]

def should_exclude(path):
    """
    除外すべきファイル/ディレクトリかどうかを判定
    
    Args:
        path: 対象パス
        
    Returns:
        除外すべき場合はTrue、そうでない場合はFalse
    """
    for pattern in EXCLUDE_PATTERNS:
        if pattern.endswith("*"):
            base_pattern = pattern[:-1]
            if path.startswith(base_pattern):
                return True
        elif pattern in path:
            return True
    return False

def create_empty_directories(zip_path):
    """
    空のディレクトリを作成
    
    Args:
        zip_path: 出力先のZIPファイルパス
    """
    required_empty_dirs = ["uploads", "results"]
    
    for empty_dir in required_empty_dirs:
        if not os.path.exists(empty_dir):
            os.makedirs(empty_dir)
        
        # ディレクトリを空にするためのdummyファイルを作成
        dummy_file = os.path.join(empty_dir, ".keep")
        with open(dummy_file, "w") as f:
            f.write("# このファイルは空のディレクトリを維持するためのものです。削除しないでください。")
        
        # ZIPに追加
        zip_path.write(dummy_file, os.path.join(empty_dir, ".keep"))

def create_install_guide():
    """
    インストールガイドを作成
    
    Returns:
        作成したファイルのパス
    """
    install_guide = "INSTALL.md"
    
    with open(install_guide, "w", encoding="utf-8") as f:
        f.write(f"""# PDF処理 & PayPal決済リンク発行システム インストールガイド

バージョン: {VERSION}
ビルド日: {BUILD_DATE}

## システム要件

- Python 3.8以上
- インターネット接続
- PayPalデベロッパーアカウント（APIキー取得用）

## インストール手順

1. Pythonがインストールされていることを確認してください。
   - コマンドプロンプトで `python --version` を実行して確認できます。
   - ダウンロード: https://www.python.org/downloads/

2. ZIP内の全ファイルを任意のフォルダに展開してください。

3. コマンドプロンプト(CMD)またはPowerShellを開き、展開したフォルダに移動します。
   ```
   cd 展開先のフォルダパス
   ```

4. 必要なライブラリをインストールします。
   ```
   pip install -r requirements.txt
   ```

5. アプリケーションを起動します。
   ```
   python app.py
   ```

6. ブラウザで以下のURLにアクセスします。
   ```
   http://localhost:5000
   ```

7. 初回起動時は「設定」画面からPayPal API認証情報を設定してください。

## PayPal API設定方法

1. PayPalデベロッパーアカウントを作成またはログインします。
   - https://developer.paypal.com/

2. 「Dashboard」から「My Apps & Credentials」を選択します。

3. 「Create App」ボタンをクリックし、アプリを作成します。
   - アプリ名: 任意の名前（例: PDF処理システム）
   - アプリタイプ: Merchant

4. 作成したアプリの詳細画面から以下の情報を取得します。
   - Client ID
   - Secret

5. アプリケーションの「設定」画面で取得した情報を入力します。
   - 環境モード: テスト中は「Sandbox」、本番環境では「Live」
   - PayPal Client ID: 取得したClient ID
   - PayPal Client Secret: 取得したSecret

6. 「接続テスト」ボタンをクリックして設定が正しいか確認してください。

## サポート

問題が発生した場合は、以下をご確認ください。
- ログファイル「app.log」でエラー内容を確認
- requirementsが正しくインストールされているか確認
- PayPal API認証情報が正しいか確認

## ライセンス

このソフトウェアは、プライベートでの使用に限定されます。再配布や商用利用については開発者にお問い合わせください。
""")
    
    return install_guide

def create_distribution_zip():
    """
    配布用ZIPファイルを作成
    
    Returns:
        作成したZIPファイルのパス
    """
    # 現在のディレクトリを取得
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 配布用ディレクトリの作成
    dist_dir = os.path.join(current_dir, "dist")
    if not os.path.exists(dist_dir):
        os.makedirs(dist_dir)
    
    # タイムスタンプ付きのZIPファイル名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"pdf_paypal_system_v{VERSION}_{timestamp}.zip"
    zip_path = os.path.join(dist_dir, zip_filename)
    
    # インストールガイドを作成
    install_guide = create_install_guide()
    
    # ZIPファイル作成
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # 個別ファイルの追加
        for file in INCLUDE_FILES:
            file_path = os.path.join(current_dir, file)
            if os.path.exists(file_path):
                zipf.write(file_path, file)
                logger.info(f"追加: {file}")
            else:
                logger.warning(f"警告: {file}が見つかりません。スキップします。")
        
        # ディレクトリの追加（再帰的に）
        for directory in INCLUDE_DIRS:
            dir_path = os.path.join(current_dir, directory)
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                for root, dirs, files in os.walk(dir_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, current_dir)
                        if not should_exclude(rel_path):
                            zipf.write(file_path, rel_path)
                            logger.info(f"追加: {rel_path}")
            else:
                logger.warning(f"警告: ディレクトリ{directory}が見つかりません。スキップします。")
        
        # 空のディレクトリを追加
        create_empty_directories(zipf)
        
        # インストールガイドを追加
        zipf.write(install_guide, os.path.basename(install_guide))
        logger.info(f"追加: {os.path.basename(install_guide)}")
    
    # インストールガイドを削除
    os.remove(install_guide)
    
    logger.info(f"\n配布用ZIPファイルを作成しました: {zip_path}")
    logger.info(f"ファイルサイズ: {os.path.getsize(zip_path) / 1024:.2f} KB")
    
    return zip_path

def main():
    """
    メイン処理
    """
    logger.info("=== PDF処理 & PayPal決済リンク発行システム 配布パッケージ作成 ===")
    logger.info(f"バージョン: {VERSION}")
    logger.info(f"ビルド日: {BUILD_DATE}")
    logger.info("作成を開始します...\n")
    
    try:
        zip_path = create_distribution_zip()
        logger.info("\n正常に完了しました！")
        return 0
    except Exception as e:
        logger.error(f"\nエラーが発生しました: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
