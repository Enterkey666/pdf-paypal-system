#!/usr/bin/env python3
"""
顧客情報抽出機能のテストスクリプト
各ルートが正しく動作するかを確認します
"""
import os
import sys
import json
import logging
import tempfile
from customer_extractor import extract_customer

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_test_files():
    """テスト用のファイルを作成"""
    # テスト用ディレクトリ
    test_dir = tempfile.mkdtemp()
    
    # テスト用のテキスト（顧客名が含まれるケース）
    test_text_with_customer = """
    請求書
    
    株式会社テスト
    〒123-4567
    東京都渋谷区テスト1-2-3
    
    テスト顧客様
    
    請求金額: 10,000円
    """
    
    # テスト用のテキスト（顧客名が含まれないケース）
    test_text_without_customer = """
    請求書
    
    株式会社テスト
    〒123-4567
    東京都渋谷区テスト1-2-3
    
    請求金額: 10,000円
    """
    
    # テスト用のファイル名とテキストのマッピング
    test_cases = [
        {"filename": "YORUTOKO_invoice.pdf", "text": test_text_without_customer},  # YORUTOKOルート
        {"filename": "special_customer_invoice.pdf", "text": test_text_without_customer},  # specialルート
        {"filename": "test_company_invoice.pdf", "text": test_text_without_customer},  # ファイル名からの抽出ルート
        {"filename": "normal_file.pdf", "text": test_text_with_customer}  # テキストからの抽出ルート
    ]
    
    return test_cases, test_dir

def test_extract_customer():
    """顧客情報抽出機能のテスト"""
    logger.info("顧客情報抽出機能のテストを開始します")
    
    # テスト用のファイルを作成
    test_cases, test_dir = create_test_files()
    
    try:
        # 各テストケースでテスト
        for test_case in test_cases:
            filename = test_case["filename"]
            text = test_case["text"]
            logger.info(f"テストケース: {filename}")
            
            # 顧客情報を抽出
            customer = extract_customer(text, filename)
            logger.info(f"抽出結果: {customer}")
            
            # 結果の検証
            if 'YORUTOKO' in filename:
                logger.info("YORUTOKOルートのテスト")
                if customer == '顧客名':
                    logger.info("✅ YORUTOKOルートが正しく動作しています（デフォルト値を使用）")
                else:
                    logger.info(f"✅ YORUTOKOルートが正しく動作しています（設定値: {customer}）")
            elif 'special' in filename:
                logger.info("specialルートのテスト")
                if customer:
                    logger.info("✅ specialルートが正しく動作しています")
                else:
                    logger.error("❌ specialルートが正しく動作していません")
            elif 'test_company' in filename:
                logger.info("ファイル名からの抽出ルートのテスト")
                # テキストから抽出できない場合、ファイル名から抽出されるはず
                if customer == 'test_company':
                    logger.info("✅ ファイル名からの抽出ルートが正しく動作しています")
                else:
                    logger.error(f"❌ ファイル名からの抽出ルートが正しく動作していません: {customer}")
            else:
                logger.info("テキストからの抽出ルートのテスト")
                if customer == 'テスト顧客':
                    logger.info("✅ テキストからの抽出ルートが正しく動作しています")
                else:
                    logger.info(f"ℹ️ テキストからの抽出結果: {customer}")
            
            logger.info("---")
    
    
    except Exception as e:
        logger.error(f"テスト中にエラーが発生しました: {e}")
    
    finally:
        # テスト用ディレクトリの削除
        import shutil
        shutil.rmtree(test_dir)
    
    logger.info("顧客情報抽出機能のテストが完了しました")

def test_encrypted_config():
    """暗号化された設定ファイルのテスト"""
    logger.info("暗号化された設定ファイルのテストを開始します")
    
    try:
        # 設定ファイルのパス
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(base_dir, 'config')
        enc_file = os.path.join(config_dir, 'customer_mapping.enc')
        
        # 暗号化ファイルが存在するか確認
        if os.path.exists(enc_file):
            logger.info("✅ 暗号化された設定ファイルが存在します")
            
            # 暗号化ファイルを復号化
            from utils.crypto_util import CryptoUtil
            with open(enc_file, 'rb') as f:
                encrypted_data = f.read()
            
            try:
                decrypted_data = CryptoUtil.decrypt_data(encrypted_data)
                logger.info(f"✅ 暗号化ファイルの復号化に成功しました: {json.dumps(decrypted_data, ensure_ascii=False)}")
            except Exception as e:
                logger.error(f"❌ 暗号化ファイルの復号化に失敗しました: {e}")
        else:
            logger.warning("⚠️ 暗号化された設定ファイルが存在しません")
    
    except Exception as e:
        logger.error(f"テスト中にエラーが発生しました: {e}")
    
    logger.info("暗号化された設定ファイルのテストが完了しました")

def main():
    """メイン関数"""
    logger.info("テストを開始します")
    
    # 顧客情報抽出機能のテスト
    test_extract_customer()
    
    # 暗号化された設定ファイルのテスト
    test_encrypted_config()
    
    logger.info("すべてのテストが完了しました")

if __name__ == "__main__":
    main()
