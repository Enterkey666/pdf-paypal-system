import logging
import time
import json
from payment_status_checker import check_payment_status
from database import update_payment_status, get_db_connection

logger = logging.getLogger(__name__)

def update_pending_payment_statuses():
    """
    データベースから未完了（PENDING）または状態不明の支払いを検索し、
    決済プロバイダー（PayPalまたはStripe）のAPIを使用して最新のステータスを取得して更新する
    
    Returns:
        tuple: (更新された件数, エラー件数)
    """
    logger.info("未完了の支払いステータス更新処理を開始")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 過去30日以内の処理履歴で、決済リンク（PayPalまたはStripe）があり、
        # ステータスがないか、PENDINGまたはUNKNOWNのものを検索
        thirty_days_ago = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() - 30*24*60*60))
        
        cursor.execute("""
            SELECT id, paypal_link, status, payment_provider 
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
                # 決済リンクを取得
                payment_link = payment['paypal_link']  # カラム名は変更されていないが、内容は決済リンク
                if not payment_link:
                    continue
                
                # 決済プロバイダーを取得
                provider = payment.get('payment_provider', None)
                
                # プロバイダーが指定されていない場合は、リンクから推測
                if not provider:
                    if 'stripe.com' in payment_link or '/stripe/' in payment_link:
                        provider = 'stripe'
                    else:
                        provider = 'paypal'  # デフォルトはPayPal
                
                # プロバイダーに応じてオーダーIDを抽出
                order_id = None
                if provider.lower() == 'stripe':
                    # Stripeの場合の抽出ロジック
                    if '/sessions/' in payment_link:
                        order_id = payment_link.split('/sessions/')[1].split('?')[0].split('#')[0]
                    elif '/payment_intents/' in payment_link:
                        order_id = payment_link.split('/payment_intents/')[1].split('?')[0].split('#')[0]
                    elif 'session_id=' in payment_link:
                        order_id = payment_link.split('session_id=')[1].split('&')[0]
                    elif 'payment_intent=' in payment_link:
                        order_id = payment_link.split('payment_intent=')[1].split('&')[0]
                    else:
                        logger.warning(f"StripeリンクからIDを抽出できません: {payment_link}")
                        continue
                else:
                    # PayPalの場合の抽出ロジック
                    if 'checkoutOrderId=' in payment_link:
                        order_id = payment_link.split('checkoutOrderId=')[1].split('&')[0]
                    elif '/checkout/orders/' in payment_link:
                        order_id = payment_link.split('/checkout/orders/')[1].split('?')[0].split('/')[0]
                    else:
                        logger.warning(f"PayPalリンクからオーダーIDを抽出できません: {payment_link}")
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
                
                # 決済プロバイダーのAPIで最新のステータスを取得
                logger.info(f"オーダーID {order_id} のステータスを確認中... (プロバイダー: {provider})")
                new_status = check_payment_status(order_id, provider)
                
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

def update_payment_status_by_order_id(order_id, provider=None):
    """
    特定の注文IDの支払いステータスを更新する
    
    Args:
        order_id (str): 決済プロバイダーの注文ID
        provider (str, optional): 決済プロバイダー名 ('paypal' または 'stripe')
        
    Returns:
        tuple: (成功したかどうか, 新しいステータス, メッセージ)
    """
    try:
        if not order_id or len(order_id) < 5:
            return False, None, "無効なオーダーID"
        
        logger.info(f"決済ステータス更新開始: オーダーID={order_id}, プロバイダー={provider or 'paypal'}")
            
        # 決済プロバイダーのAPIで最新のステータスを取得
        new_status = check_payment_status(order_id, provider)
        
        if new_status != "UNKNOWN":
            # ステータスを更新
            success, message = update_payment_status(order_id, new_status)
            logger.info(f"決済ステータス更新結果: 成功={success}, 新ステータス={new_status}")
            return success, new_status, message
        else:
            logger.warning(f"決済ステータス取得失敗: オーダーID={order_id}")
            return False, new_status, "ステータスを取得できませんでした"
            
    except Exception as e:
        logger.error(f"個別支払いステータス更新エラー: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False, None, str(e)
