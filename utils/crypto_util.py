import os
import base64
import json
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

class CryptoUtil:
    """暗号化ユーティリティクラス - 設定ファイルの暗号化/復号化を担当"""
    
    @staticmethod
    def get_key(password_file=None):
        """暗号化キーを取得する。
        指定されたパスワードファイルから読み込むか、環境変数から取得する。
        どちらも存在しない場合はデフォルトキーを使用（本番環境では使用しないこと）。
        """
        try:
            # 1. パスワードファイルからキーを取得
            if password_file and os.path.exists(password_file):
                with open(password_file, 'rb') as f:
                    key = f.read().strip()
                return key
            
            # 2. 環境変数からキーを取得
            env_key = os.environ.get('PDF_PAYPAL_CRYPTO_KEY')
            if env_key:
                return base64.urlsafe_b64decode(env_key)
            
            # 3. デフォルトキー（開発環境のみ）
            logger.warning("暗号化キーが見つかりません。デフォルトキーを使用します（本番環境では使用しないでください）")
            salt = b'pdf_paypal_system_salt'
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(b'default_development_only'))
            return key
        except Exception as e:
            logger.error(f"暗号化キーの取得中にエラーが発生しました: {e}")
            raise

    @staticmethod
    def encrypt_data(data, key=None):
        """データを暗号化する"""
        try:
            if key is None:
                key = CryptoUtil.get_key()
            
            fernet = Fernet(key)
            if isinstance(data, dict):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            elif isinstance(data, str):
                data = data.encode('utf-8')
            
            encrypted_data = fernet.encrypt(data)
            return encrypted_data
        except Exception as e:
            logger.error(f"データの暗号化中にエラーが発生しました: {e}")
            raise

    @staticmethod
    def decrypt_data(encrypted_data, key=None):
        """暗号化されたデータを復号化する"""
        try:
            if key is None:
                key = CryptoUtil.get_key()
            
            fernet = Fernet(key)
            decrypted_data = fernet.decrypt(encrypted_data)
            
            # JSONとして解析を試みる
            try:
                return json.loads(decrypted_data.decode('utf-8'))
            except json.JSONDecodeError:
                # 通常のテキストとして返す
                return decrypted_data.decode('utf-8')
        except Exception as e:
            logger.error(f"データの復号化中にエラーが発生しました: {e}")
            raise

    @staticmethod
    def encrypt_file(input_file, output_file=None, key=None):
        """ファイルを暗号化する"""
        if output_file is None:
            output_file = input_file + '.enc'
        
        try:
            with open(input_file, 'rb') as f:
                data = f.read()
            
            encrypted_data = CryptoUtil.encrypt_data(data, key)
            
            with open(output_file, 'wb') as f:
                f.write(encrypted_data)
            
            return output_file
        except Exception as e:
            logger.error(f"ファイルの暗号化中にエラーが発生しました: {e}")
            raise

    @staticmethod
    def decrypt_file(input_file, output_file=None, key=None):
        """暗号化されたファイルを復号化する"""
        if output_file is None:
            output_file = input_file.replace('.enc', '') if input_file.endswith('.enc') else input_file + '.dec'
        
        try:
            with open(input_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = CryptoUtil.decrypt_data(encrypted_data, key)
            
            if isinstance(decrypted_data, (dict, list)):
                # JSONオブジェクトの場合
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(decrypted_data, f, ensure_ascii=False, indent=2)
            else:
                # バイナリデータの場合
                with open(output_file, 'wb') as f:
                    if isinstance(decrypted_data, str):
                        f.write(decrypted_data.encode('utf-8'))
                    else:
                        f.write(decrypted_data)
            
            return output_file
        except Exception as e:
            logger.error(f"ファイルの復号化中にエラーが発生しました: {e}")
            raise
