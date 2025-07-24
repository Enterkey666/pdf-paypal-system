"""
Cloud Storage Adapter
ローカルファイルシステムからCloud Storageへの移行用アダプター
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from firebase_admin import storage
from google.cloud import storage as gcs
import tempfile

logger = logging.getLogger(__name__)

class CloudStorageAdapter:
    """Cloud Storage操作のためのアダプタークラス"""
    
    def __init__(self, bucket_name: Optional[str] = None):
        self.bucket = storage.bucket(bucket_name)
        self.client = gcs.Client()
    
    def upload_file(self, file_obj, file_path: str, content_type: str = None) -> str:
        """ファイルをCloud Storageにアップロード"""
        try:
            blob = self.bucket.blob(file_path)
            
            if content_type:
                blob.content_type = content_type
            
            # ファイルオブジェクトからアップロード
            if hasattr(file_obj, 'read'):
                blob.upload_from_file(file_obj)
            else:
                # バイナリデータの場合
                blob.upload_from_string(file_obj)
            
            logger.info(f"File uploaded: {file_path}")
            return blob.public_url
            
        except Exception as e:
            logger.error(f"File upload error: {str(e)}")
            raise
    
    def upload_pdf(self, user_id: str, file_obj, filename: str) -> Dict[str, str]:
        """PDFファイルをアップロード"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = f"uploads/{user_id}/{timestamp}_{filename}"
            
            url = self.upload_file(file_obj, file_path, 'application/pdf')
            
            return {
                'file_path': file_path,
                'url': url,
                'filename': filename,
                'timestamp': timestamp
            }
            
        except Exception as e:
            logger.error(f"PDF upload error: {str(e)}")
            raise
    
    def download_file(self, file_path: str) -> bytes:
        """ファイルをダウンロード"""
        try:
            blob = self.bucket.blob(file_path)
            return blob.download_as_bytes()
        except Exception as e:
            logger.error(f"File download error: {str(e)}")
            raise
    
    def download_to_temp_file(self, file_path: str) -> str:
        """ファイルを一時ファイルにダウンロード"""
        try:
            blob = self.bucket.blob(file_path)
            
            # 一時ファイル作成
            temp_file = tempfile.NamedTemporaryFile(delete=False, 
                                                  suffix=os.path.splitext(file_path)[1])
            blob.download_to_filename(temp_file.name)
            
            logger.info(f"File downloaded to temp: {temp_file.name}")
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Temp file download error: {str(e)}")
            raise
    
    def delete_file(self, file_path: str) -> bool:
        """ファイルを削除"""
        try:
            blob = self.bucket.blob(file_path)
            blob.delete()
            logger.info(f"File deleted: {file_path}")
            return True
        except Exception as e:
            logger.error(f"File deletion error: {str(e)}")
            return False
    
    def list_user_files(self, user_id: str, prefix: str = "") -> List[Dict[str, Any]]:
        """ユーザーのファイル一覧取得"""
        try:
            folder_prefix = f"uploads/{user_id}/"
            if prefix:
                folder_prefix += prefix
            
            blobs = self.bucket.list_blobs(prefix=folder_prefix)
            files = []
            
            for blob in blobs:
                files.append({
                    'name': blob.name,
                    'size': blob.size,
                    'created': blob.time_created,
                    'updated': blob.updated,
                    'content_type': blob.content_type,
                    'url': blob.public_url
                })
            
            return files
            
        except Exception as e:
            logger.error(f"File listing error: {str(e)}")
            return []
    
    def generate_signed_url(self, file_path: str, expiration_hours: int = 1) -> str:
        """署名付きURLを生成（一時的なアクセス用）"""
        try:
            blob = self.bucket.blob(file_path)
            expiration = datetime.now() + timedelta(hours=expiration_hours)
            
            url = blob.generate_signed_url(expiration=expiration, method='GET')
            logger.info(f"Signed URL generated for: {file_path}")
            return url
            
        except Exception as e:
            logger.error(f"Signed URL generation error: {str(e)}")
            raise
    
    def copy_file(self, source_path: str, destination_path: str) -> bool:
        """ファイルをコピー"""
        try:
            source_blob = self.bucket.blob(source_path)
            destination_blob = self.bucket.blob(destination_path)
            
            destination_blob.upload_from_string(
                source_blob.download_as_bytes(),
                content_type=source_blob.content_type
            )
            
            logger.info(f"File copied: {source_path} -> {destination_path}")
            return True
            
        except Exception as e:
            logger.error(f"File copy error: {str(e)}")
            return False
    
    def move_file(self, source_path: str, destination_path: str) -> bool:
        """ファイルを移動"""
        try:
            if self.copy_file(source_path, destination_path):
                return self.delete_file(source_path)
            return False
        except Exception as e:
            logger.error(f"File move error: {str(e)}")
            return False
    
    def create_export_file(self, user_id: str, content: bytes, filename: str, 
                          content_type: str = 'application/pdf') -> Dict[str, str]:
        """エクスポートファイルを作成"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = f"exports/{user_id}/{timestamp}_{filename}"
            
            blob = self.bucket.blob(file_path)
            blob.content_type = content_type
            blob.upload_from_string(content)
            
            # 署名付きURL生成（24時間有効）
            signed_url = self.generate_signed_url(file_path, 24)
            
            return {
                'file_path': file_path,
                'url': blob.public_url,
                'signed_url': signed_url,
                'filename': filename,
                'timestamp': timestamp,
                'expires_at': (datetime.now() + timedelta(hours=24)).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Export file creation error: {str(e)}")
            raise
    
    def cleanup_old_files(self, days_old: int = 30) -> int:
        """古いファイルを削除"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            deleted_count = 0
            
            # アップロードファイルの清理
            upload_blobs = self.bucket.list_blobs(prefix="uploads/")
            for blob in upload_blobs:
                if blob.time_created < cutoff_date:
                    blob.delete()
                    deleted_count += 1
            
            # エクスポートファイルの清理（7日以上古い）
            export_cutoff = datetime.now() - timedelta(days=7)
            export_blobs = self.bucket.list_blobs(prefix="exports/")
            for blob in export_blobs:
                if blob.time_created < export_cutoff:
                    blob.delete()
                    deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old files")
            return deleted_count
            
        except Exception as e:
            logger.error(f"File cleanup error: {str(e)}")
            return 0
    
    def get_file_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """ファイルのメタデータを取得"""
        try:
            blob = self.bucket.blob(file_path)
            if blob.exists():
                return {
                    'name': blob.name,
                    'size': blob.size,
                    'created': blob.time_created.isoformat() if blob.time_created else None,
                    'updated': blob.updated.isoformat() if blob.updated else None,
                    'content_type': blob.content_type,
                    'md5_hash': blob.md5_hash,
                    'etag': blob.etag
                }
            return None
        except Exception as e:
            logger.error(f"Metadata retrieval error: {str(e)}")
            return None

# グローバルインスタンス
storage_adapter = CloudStorageAdapter()