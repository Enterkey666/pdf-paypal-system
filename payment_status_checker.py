import logging
import time
import json
import requests
from paypal_utils import get_api_base, get_paypal_access_token

logger = logging.getLogger(__name__)

def check_payment_status(order_id):
    """
    PayPal APIを使用して決済状態を確認する
    
    Args:
        order_id: PayPalのオーダーID
        
    Returns:
        状態文字列: 'COMPLETED', 'PENDING', 'FAILED', 'UNKNOWN'のいずれか
    """
    
    try:
        if not order_id or len(order_id) < 5:
            logger.warning(f"無効なオーダーID: {order_id}")
            return "UNKNOWN"
            
        logger.info(f"PayPal決済状態確認開始: オーダーID={order_id}")
            
        # アクセストークン取得
        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("PayPalアクセストークン取得失敗")
            return "UNKNOWN"
        
        # オーダー情報取得
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Cache-Control": "no-cache"
        }
        
        api_base = get_api_base()
        order_url = f"{api_base}/v2/checkout/orders/{order_id}"
        logger.info(f"PayPal API呼び出し: {order_url}")
        
        # キャッシュを使用しないようにするためのパラメータを追加
        params = {"_": int(time.time() * 1000)}
        response = requests.get(order_url, headers=headers, params=params)
        
        logger.info(f"PayPal APIレスポンス: ステータスコード={response.status_code}")
        
        if response.status_code == 200:
            order_data = response.json()
            status = order_data.get("status", "")
            logger.info(f"PayPal注文ステータス: {status}, 詳細: {json.dumps(order_data)[:200]}...")
            
            # 承認済みの場合はキャプチャを試みる
            if status == "APPROVED":
                logger.info(f"承認済み注文を検出: {order_id} - キャプチャを試みます")
                capture_url = f"{api_base}/v2/checkout/orders/{order_id}/capture"
                capture_response = requests.post(capture_url, headers=headers)
                
                if capture_response.status_code == 201:
                    capture_data = capture_response.json()
                    capture_status = capture_data.get("status", "")
                    logger.info(f"キャプチャ成功: 新ステータス={capture_status}")
                    if capture_status == "COMPLETED":
                        return "COMPLETED"  # キャプチャ成功、支払い完了
                else:
                    logger.error(f"キャプチャ失敗: {capture_response.status_code}, {capture_response.text}")
            
            # 状態に応じて返却
            if status == "COMPLETED":
                logger.info("支払い完了状態を返却: COMPLETED")
                return "COMPLETED"  # 支払い完了
            elif status == "APPROVED":
                logger.info("承認済み状態を返却: PENDING")
                return "PENDING"    # 承認済み（キャプチャ前）
            elif status == "CREATED":
                logger.info("作成済み状態を返却: PENDING")
                return "PENDING"    # 作成済み（支払い前）
            elif status == "VOIDED":
                logger.info("無効化状態を返却: FAILED")
                return "FAILED"     # 無効化された注文
            elif status == "PAYER_ACTION_REQUIRED":
                logger.info("アクション必要状態を返却: PENDING")
                return "PENDING"    # 支払い者のアクションが必要な状態
            else:
                logger.info(f"その他の状態を返却: {status}")
                return status        # その他の状態はそのまま返す
        else:
            logger.error(f"PayPal API エラー: {response.status_code}, {response.text}")
            return "UNKNOWN"
    except Exception as e:
        logger.error(f"PayPal決済状態確認中の例外: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return "UNKNOWN"
