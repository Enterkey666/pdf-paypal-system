from flask import Blueprint, jsonify, session, request
import os
import json
import logging
from paypal_utils import cancel_order
from flask import current_app

# ログ設定
logger = logging.getLogger(__name__)

# Blueprintを作成
history_bp = Blueprint('history', __name__)

@history_bp.route('/delete_all_with_paypal', methods=['POST'])
def delete_all_with_paypal():
    """
    全ての履歴ファイルとそれに関連したPayPal注文情報を削除するエンドポイント
    管理者または有料会員のみがアクセス可能
    """
    try:
        # 管理者権限チェック
        is_admin = session.get('admin_logged_in', False)
        is_paid_member = session.get('is_paid_member', False)
        
        if not (is_admin or is_paid_member):
            logger.warning(f"権限のないユーザーが全履歴削除を試みました: {session.get('user_id', 'unknown')}")
            return jsonify({"success": False, "error": "この操作を実行する権限がありません。管理者または有料会員のみがアクセスできます。"}), 403
        
        # 履歴ファイルの保存ディレクトリ
        app = current_app
        base_dir = os.path.dirname(os.path.abspath(__file__))
        results_folder = app.config.get('RESULTS_FOLDER', os.path.join(base_dir, 'results'))
        
        # 履歴ディレクトリからすべてのJSONファイルを検索
        deleted_files = []
        paypal_orders = []
        
        # ディレクトリが存在するか確認
        if os.path.exists(results_folder) and os.path.isdir(results_folder):
            for filename in os.listdir(results_folder):
                if filename.endswith('.json'):
                    file_path = os.path.join(results_folder, filename)
                    
                    # PayPal注文IDを収集
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            for entry in data:
                                if isinstance(entry, dict) and 'paypal_order_id' in entry and entry['paypal_order_id']:
                                    paypal_orders.append(entry['paypal_order_id'])
                    except Exception as e:
                        logger.error(f"履歴ファイル読み込みエラー: {str(e)}, ファイル: {file_path}")
                    
                    # ファイルを削除
                    try:
                        os.remove(file_path)
                        deleted_files.append(filename)
                        logger.info(f"履歴ファイルを削除しました: {file_path}")
                    except Exception as e:
                        logger.error(f"履歴ファイル削除エラー: {str(e)}, ファイル: {file_path}")
        
        # PayPal注文のキャンセルを試みる
        cancelled_orders = []
        for order_id in paypal_orders:
            try:
                # ユーザーID取得
                user_id = 'admin' if session.get('admin_logged_in', False) else session.get('user_id', session.sid)
                
                # 注文をキャンセル
                success = cancel_order(order_id, user_id=user_id)
                if success:
                    cancelled_orders.append(order_id)
                    logger.info(f"PayPal注文をキャンセルしました: {order_id}")
                else:
                    logger.warning(f"PayPal注文のキャンセルに失敗: {order_id}")
            except Exception as e:
                logger.error(f"PayPal注文キャンセルエラー: {str(e)}, 注文ID: {order_id}")
        
        # 結果を返す
        return jsonify({
            "success": True,
            "deleted_files": deleted_files,
            "deleted_files_count": len(deleted_files),
            "cancelled_orders": cancelled_orders,
            "cancelled_orders_count": len(cancelled_orders),
            "failed_orders_count": len(paypal_orders) - len(cancelled_orders)
        })
        
    except Exception as e:
        logger.error(f"全履歴削除処理中にエラーが発生: {str(e)}")
        return jsonify({"success": False, "error": f"処理中にエラーが発生しました: {str(e)}"}), 500
