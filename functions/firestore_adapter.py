"""
Firestore Database Adapter
SQLiteからFirestoreへの移行用アダプター
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

logger = logging.getLogger(__name__)

class FirestoreAdapter:
    """Firestore操作のためのアダプタークラス"""
    
    def __init__(self):
        self.db = firestore.client()
    
    # ユーザー管理
    def create_user(self, user_data: Dict[str, Any]) -> str:
        """新規ユーザー作成"""
        try:
            user_data['created_at'] = datetime.now()
            user_data['updated_at'] = datetime.now()
            doc_ref = self.db.collection('users').add(user_data)
            logger.info(f"User created: {doc_ref[1].id}")
            return doc_ref[1].id
        except Exception as e:
            logger.error(f"User creation error: {str(e)}")
            raise
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """ユーザー情報取得"""
        try:
            doc = self.db.collection('users').document(user_id).get()
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"User retrieval error: {str(e)}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """メールアドレスでユーザー検索"""
        try:
            query = self.db.collection('users').where('email', '==', email).limit(1)
            docs = query.stream()
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"User search error: {str(e)}")
            return None
    
    def update_user(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        """ユーザー情報更新"""
        try:
            update_data['updated_at'] = datetime.now()
            self.db.collection('users').document(user_id).update(update_data)
            logger.info(f"User updated: {user_id}")
            return True
        except Exception as e:
            logger.error(f"User update error: {str(e)}")
            return False
    
    def delete_user(self, user_id: str) -> bool:
        """ユーザー削除"""
        try:
            self.db.collection('users').document(user_id).delete()
            logger.info(f"User deleted: {user_id}")
            return True
        except Exception as e:
            logger.error(f"User deletion error: {str(e)}")
            return False
    
    # 決済管理
    def create_payment(self, payment_data: Dict[str, Any]) -> str:
        """新規決済記録作成"""
        try:
            payment_data['created_at'] = datetime.now()
            payment_data['updated_at'] = datetime.now()
            doc_ref = self.db.collection('payments').add(payment_data)
            logger.info(f"Payment created: {doc_ref[1].id}")
            return doc_ref[1].id
        except Exception as e:
            logger.error(f"Payment creation error: {str(e)}")
            raise
    
    def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """決済情報取得"""
        try:
            doc = self.db.collection('payments').document(payment_id).get()
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Payment retrieval error: {str(e)}")
            return None
    
    def get_user_payments(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """ユーザーの決済履歴取得"""
        try:
            query = (self.db.collection('payments')
                    .where('user_id', '==', user_id)
                    .order_by('created_at', direction=firestore.Query.DESCENDING)
                    .limit(limit))
            
            payments = []
            for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                payments.append(data)
            
            return payments
        except Exception as e:
            logger.error(f"User payments retrieval error: {str(e)}")
            return []
    
    def update_payment_status(self, payment_id: str, status: str, additional_data: Dict[str, Any] = None) -> bool:
        """決済ステータス更新"""
        try:
            update_data = {
                'status': status,
                'updated_at': datetime.now()
            }
            if additional_data:
                update_data.update(additional_data)
            
            self.db.collection('payments').document(payment_id).update(update_data)
            logger.info(f"Payment status updated: {payment_id} -> {status}")
            return True
        except Exception as e:
            logger.error(f"Payment status update error: {str(e)}")
            return False
    
    # PDF履歴管理
    def create_pdf_history(self, history_data: Dict[str, Any]) -> str:
        """PDF処理履歴作成"""
        try:
            history_data['created_at'] = datetime.now()
            history_data['updated_at'] = datetime.now()
            doc_ref = self.db.collection('pdf_history').add(history_data)
            logger.info(f"PDF history created: {doc_ref[1].id}")
            return doc_ref[1].id
        except Exception as e:
            logger.error(f"PDF history creation error: {str(e)}")
            raise
    
    def get_user_pdf_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """ユーザーのPDF処理履歴取得"""
        try:
            query = (self.db.collection('pdf_history')
                    .where('user_id', '==', user_id)
                    .order_by('created_at', direction=firestore.Query.DESCENDING)
                    .limit(limit))
            
            history = []
            for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                history.append(data)
            
            return history
        except Exception as e:
            logger.error(f"PDF history retrieval error: {str(e)}")
            return []
    
    def update_pdf_history(self, history_id: str, update_data: Dict[str, Any]) -> bool:
        """PDF履歴更新"""
        try:
            update_data['updated_at'] = datetime.now()
            self.db.collection('pdf_history').document(history_id).update(update_data)
            logger.info(f"PDF history updated: {history_id}")
            return True
        except Exception as e:
            logger.error(f"PDF history update error: {str(e)}")
            return False
    
    # 設定管理
    def get_user_settings(self, user_id: str) -> Dict[str, Any]:
        """ユーザー設定取得"""
        try:
            doc = self.db.collection('user_settings').document(user_id).get()
            if doc.exists:
                return doc.to_dict()
            return {}
        except Exception as e:
            logger.error(f"User settings retrieval error: {str(e)}")
            return {}
    
    def update_user_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """ユーザー設定更新"""
        try:
            settings['updated_at'] = datetime.now()
            self.db.collection('user_settings').document(user_id).set(settings, merge=True)
            logger.info(f"User settings updated: {user_id}")
            return True
        except Exception as e:
            logger.error(f"User settings update error: {str(e)}")
            return False
    
    # 管理者機能
    def get_all_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        """全ユーザー取得（管理者用）"""
        try:
            query = self.db.collection('users').limit(limit)
            users = []
            for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                users.append(data)
            return users
        except Exception as e:
            logger.error(f"All users retrieval error: {str(e)}")
            return []
    
    def get_payment_statistics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """決済統計取得"""
        try:
            query = (self.db.collection('payments')
                    .where('created_at', '>=', start_date)
                    .where('created_at', '<=', end_date))
            
            total_payments = 0
            total_amount = 0
            status_counts = {}
            
            for doc in query.stream():
                data = doc.to_dict()
                total_payments += 1
                total_amount += data.get('amount', 0)
                status = data.get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                'total_payments': total_payments,
                'total_amount': total_amount,
                'status_counts': status_counts,
                'period': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                }
            }
        except Exception as e:
            logger.error(f"Payment statistics error: {str(e)}")
            return {}

# グローバルインスタンス
firestore_adapter = FirestoreAdapter()