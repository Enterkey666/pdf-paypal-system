import logging
import time
import json
from payment_status_checker import check_payment_status
from database import update_payment_status, get_db_connection

logger = logging.getLogger(__name__)

def update_pending_payment_statuses():
    """
    データベースから未完了（PENDING）または状態不明の支払いを検索し、
    PayPal APIを使用して最新のステータスを取得して更新する
    
    Returns:
        tuple: (更新された件数, エラー件数)
    """
    logger.info("未完了の支払いステータス更新処理を開始")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 過去30日以内の処理履歴で、PayPal注文IDがあり、
        # ステータスがないか、PENDINGまたはUNKNOWNのものを検索
        thirty_days_ago = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() - 30*24*60*60))
        
        cursor.execute("""
            SELECT id, paypal_link, status 
            FROM processing_history 
            WHERE timestamp > ? 
            AND paypal_link IS NOT NULL 
            AND paypal_link != '' 
            AND (status IS NULL OR status = '' OR status LIKE '%PENDING%' OR status LIKE '%UNKNOWN%')
            ORDER BY timestamp DESC
        """, (thirty_days_ago,))
        
        pending_payments = cursor.fetchall()
        logger.info(f"更新対象の支払い: {len(pending_payments)}件")
        
        updated_count = 0
        error_count = 0
        
        for payment in pending_payments:
            try:
                # PayPal注文IDを抽出
                paypal_link = payment['paypal_link']
                if not paypal_link:
                    continue
                    
                # リンクからオーダーIDを抽出
                if 'checkoutOrderId=' in paypal_link:
                    order_id = paypal_link.split('checkoutOrderId=')[1].split('&')[0]
                elif '/checkout/orders/' in paypal_link:
                    order_id = paypal_link.split('/checkout/orders/')[1].split('?')[0].split('/')[0]
                else:
                    logger.warning(f"PayPalリンクからオーダーIDを抽出できません: {paypal_link}")
                    continue
                
                # 現在のステータスを確認
                current_status = None
                if payment['status'] and payment['status'].startswith('{'):
                    try:
                        status_data = json.loads(payment['status'])
                        current_status = status_data.get('status')
                    except:
                        pass
                
                # すでにCOMPLETEDなら更新しない
                if current_status == "COMPLETED":
                    continue
                
                # PayPal APIで最新のステータスを取得
                logger.info(f"オーダーID {order_id} のステータスを確認中...")
                new_status = check_payment_status(order_id)
                
                if new_status != "UNKNOWN" and (current_status != new_status):
                    # ステータスが変更されていれば更新
                    success, message = update_payment_status(order_id, new_status)
                    if success:
                        updated_count += 1
                        logger.info(f"支払いステータスを更新しました: オーダーID={order_id}, 新ステータス={new_status}")
                    else:
                        error_count += 1
                        logger.error(f"支払いステータス更新エラー: {message}")
                else:
                    logger.info(f"ステータスに変更なし: オーダーID={order_id}, ステータス={new_status}")
                    
                # APIレート制限を避けるため少し待機
                time.sleep(0.5)
                
            except Exception as e:
                error_count += 1
                logger.error(f"支払いステータス更新処理エラー: {str(e)}")
                continue
        
        logger.info(f"支払いステータス更新完了: 更新={updated_count}件, エラー={error_count}件")
        return updated_count, error_count
        
    except Exception as e:
        logger.error(f"支払いステータス一括更新エラー: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return 0, 1
    finally:
        if conn:
            conn.close()

def update_payment_status_by_order_id(order_id):
    """
    特定の注文IDの支払いステータスを更新する
    
    Args:
        order_id (str): PayPal注文ID
        
    Returns:
        tuple: (成功したかどうか, 新しいステータス, メッセージ)
    """
    try:
        if not order_id or len(order_id) < 5:
            return False, None, "無効なオーダーID"
            
        # PayPal APIで最新のステータスを取得
        new_status = check_payment_status(order_id)
        
        if new_status != "UNKNOWN":
            # ステータスを更新
            success, message = update_payment_status(order_id, new_status)
            return success, new_status, message
        else:
            return False, new_status, "ステータスを取得できませんでした"
            
    except Exception as e:
        logger.error(f"個別支払いステータス更新エラー: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False, None, str(e)
