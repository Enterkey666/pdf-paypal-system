#!/usr/bin/env python3
"""
顧客マッピング設定ファイルを暗号化するスクリプト
"""
import os
import sys
import json
import logging
from utils.crypto_util import CryptoUtil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def encrypt_customer_mapping():
    """顧客マッピング設定ファイルを暗号化する"""
    try:
        # 設定ファイルのパス
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(base_dir, 'config')
        source_file = os.path.join(config_dir, 'customer_mapping.json')
        target_file = os.path.join(config_dir, 'customer_mapping.enc')
        
        # 設定ファイルが存在するか確認
        if not os.path.exists(source_file):
            logger.error(f"設定ファイルが見つかりません: {source_file}")
            return False
        
        # 設定ファイルを読み込む
        with open(source_file, 'r', encoding='utf-8') as f:
            customer_mapping = json.load(f)
        
        # 設定ファイルを暗号化
        encrypted_data = CryptoUtil.encrypt_data(customer_mapping)
        
        # 暗号化されたデータを保存
        with open(target_file, 'wb') as f:
            f.write(encrypted_data)
        
        logger.info(f"設定ファイルを暗号化しました: {target_file}")
        return True
    
    except Exception as e:
        logger.error(f"設定ファイルの暗号化中にエラーが発生しました: {e}")
        return False

def main():
    """メイン関数"""
    success = encrypt_customer_mapping()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
