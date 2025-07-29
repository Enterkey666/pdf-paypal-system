import os
import time
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ロガーの設定
logger = logging.getLogger(__name__)

# PayPalトークンキャッシュ
_paypal_token_cache = {
    "token": "",
    "expires_at": 0
}

def get_api_base():
    """
    PayPal APIのベースURLを取得する
    
    Returns:
        文字列: PayPal APIのベースURL
    """
    from config_manager import get_config
    
    try:
        # 設定からPayPalモードを取得
        config = get_config()
        paypal_mode = config.get('paypal_mode', 'sandbox')
        
        # モードの正規化
        if paypal_mode.lower() not in ['sandbox', 'live']:
            logger.warning(f"無効なPayPalモード: {paypal_mode}。sandboxを使用します。")
            paypal_mode = 'sandbox'
        else:
            paypal_mode = paypal_mode.lower()
        
        # モードに応じたベースURLを返す
        if paypal_mode == 'sandbox':
            return "https://api-m.sandbox.paypal.com"
        else:
            return "https://api-m.paypal.com"
    
    except Exception as e:
        # 例外が発生した場合はログに記録し、デフォルト値を返す
        logger.error(f"PayPal APIベースURL取得エラー: {str(e)}")
        return "https://api-m.sandbox.paypal.com"  # 安全なデフォルト値

def get_paypal_access_token(client_id=None, client_secret=None, paypal_mode=None):
    """
    PayPal APIのアクセストークンを取得する
    キャッシュ機能とリトライロジックを実装
    
    Args:
        client_id (str, optional): PayPal Client ID。指定されない場合は設定から取得
        client_secret (str, optional): PayPal Client Secret。指定されない場合は設定から取得
        paypal_mode (str, optional): PayPalモード ('sandbox' または 'live')。指定されない場合は設定から取得
    
    Returns:
        文字列: PayPalのアクセストークン、取得失敗時はNone
    """
    global _paypal_token_cache
    
    # 現在時刻を取得（常に取得して後で使用できるようにする）
    current_time = time.time()
    
    # 引数が指定されていない場合のみキャッシュを使用
    if client_id is None and client_secret is None:
        # キャッシュされたトークンがあり、有効期限内であれば再利用
        if _paypal_token_cache["token"] and current_time < _paypal_token_cache["expires_at"]:
            remaining_time = int(_paypal_token_cache["expires_at"] - current_time)
            logger.debug(f"キャッシュされたPayPalトークンを使用します。残り有効時間: {remaining_time}秒")
            return _paypal_token_cache["token"]
    
    # 引数で指定されていない場合は設定から認証情報を取得
    if client_id is None or client_secret is None:
        from config_manager import get_config
        config = get_config()
        if client_id is None:
            client_id = config.get('client_id', '')
            # 旧形式のキー名もチェック
            if not client_id:
                client_id = config.get('paypal_client_id', '')
        if client_secret is None:
            client_secret = config.get('client_secret', '')
            # 旧形式のキー名もチェック
            if not client_secret:
                client_secret = config.get('paypal_client_secret', '')
    
    if not client_id or not client_secret:
        logger.warning("PayPal Client IDまたはClient Secretが設定されていません")
        return None
    
    # APIベースURLを取得
    if paypal_mode:
        # 指定されたモードに基づいてAPIベースURLを決定
        if paypal_mode.lower() == 'sandbox':
            api_base = "https://api-m.sandbox.paypal.com"
        else:
            api_base = "https://api-m.paypal.com"
    else:
        # モードが指定されていない場合は設定から取得
        api_base = get_api_base()
    
    # リトライ設定
    max_retries = 3
    retry_count = 0
    retry_delay = 1  # 初期リトライ遅延（秒）
    
    while retry_count < max_retries:
        try:
            # アクセストークンを取得
            token_url = f"{api_base}/v1/oauth2/token"
            token_headers = {
                "Accept": "application/json",
                "Accept-Language": "en_US"
            }
            token_data = {"grant_type": "client_credentials"}
            
            logger.info(f"PayPalアクセストークン取得開始: {token_url} (試行: {retry_count + 1}/{max_retries})")
            
            # セッション設定（タイムアウト、リトライ）
            session = requests.Session()
            retry_strategy = Retry(
                total=2,  # 接続レベルでのリトライ
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            # トークン取得リクエスト
            token_response = session.post(
                token_url,
                auth=(client_id, client_secret),
                headers=token_headers,
                data=token_data,
                timeout=(5, 15)  # 接続タイムアウト5秒、読み取りタイムアウト15秒
            )
            
            # レスポンスコードをチェック
            if token_response.status_code == 200:
                try:
                    token_data = token_response.json()
                    if "access_token" in token_data:
                        access_token = token_data["access_token"]
                        # トークンの有効期限を計算（デフォルトは3600秒、バッファとして60秒引く）
                        expires_in = token_data.get("expires_in", 3600) - 60
                        
                        # キャッシュを更新
                        _paypal_token_cache = {
                            "token": access_token,
                            "expires_at": current_time + expires_in
                        }
                        
                        logger.info(f"PayPalアクセストークン取得成功。有効期間: {expires_in}秒")
                        return access_token
                    else:
                        logger.error(f"PayPalトークンレスポンスにaccess_tokenがありません: {token_data}")
                except json.JSONDecodeError as e:
                    logger.error(f"PayPalトークンレスポンスのJSON解析エラー: {str(e)}")
            else:
                # エラーの詳細をログに記録
                error_msg = f"PayPalトークン取得エラー: ステータス={token_response.status_code}"
                try:
                    error_details = token_response.json()
                    if 'error' in error_details:
                        error_msg += f", エラー: {error_details['error']}"
                    if 'error_description' in error_details:
                        error_msg += f", 詳細: {error_details['error_description']}"
                except:
                    error_msg += f", レスポンス: {token_response.text}"
                logger.error(error_msg)
            
            # リトライ
            retry_count += 1
            if retry_count < max_retries:
                # 指数バックオフ（リトライ間隔を徐々に増やす）
                wait_time = retry_delay * (2 ** (retry_count - 1))
                logger.info(f"PayPalトークン取得リトライ {retry_count}/{max_retries}。{wait_time}秒後に再試行します...")
                time.sleep(wait_time)
        
        except requests.exceptions.RequestException as e:
            logger.error(f"PayPalトークン取得中のネットワークエラー: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                wait_time = retry_delay * (2 ** (retry_count - 1))
                logger.info(f"PayPalトークン取得リトライ {retry_count}/{max_retries}。{wait_time}秒後に再試行します...")
                time.sleep(wait_time)
        except Exception as e:
            logger.error(f"PayPalトークン取得中の予期せぬエラー: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                wait_time = retry_delay * (2 ** (retry_count - 1))
                logger.info(f"PayPalトークン取得リトライ {retry_count}/{max_retries}。{wait_time}秒後に再試行します...")
                time.sleep(wait_time)
    
    logger.error(f"PayPalアクセストークン取得失敗: 最大リトライ回数({max_retries})を超過しました")
    return None

def cancel_paypal_order(api_base, order_id, headers):
    """
    PayPalの注文をキャンセルする関数
    
    Args:
        api_base: PayPal APIのベースURL
        order_id: キャンセルする注文のID
        headers: リクエストヘッダー（認証トークンを含む）
        
    Returns:
        bool: キャンセル成功時はTrue、失敗時はFalse
    """
    # 最大3回のリトライを設定
    max_retries = 3
    retry_count = 0
    cancel_success = False
    
    logger.info(f"PayPal注文キャンセルを実行します: {order_id}")
    
    # セッションを使用してHTTPリトライを設定
    session = requests.Session()
    retry_strategy = Retry(
        total=2,  # 接続レベルでのリトライ
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    while retry_count < max_retries and not cancel_success:
        try:
            # PayPalの注文をキャンセルするための正しいエンドポイントとメソッド
            # PayPal Orders API v2では、注文をキャンセルするにはPOSTメソッドでactions/voidを呼び出す
            cancel_url = f"{api_base}/v2/checkout/orders/{order_id}/void"
            # リクエストボディは不要
            cancel_response = session.post(cancel_url, headers=headers, timeout=15)
            
            if cancel_response.status_code in [200, 204]:
                logger.info(f"PayPal注文キャンセル成功: {order_id}")
                cancel_success = True
            elif cancel_response.status_code == 404:
                # 404エラーの詳細なログ出力
                logger.warning(f"PayPal注文が見つかりません (404): {order_id}")
                logger.debug(f"詳細レスポンス: {cancel_response.text}")
                # 404の場合はリトライしても意味がないので終了
                break
            elif cancel_response.status_code == 401:
                # 認証エラー
                logger.error(f"PayPal API認証エラー (401): アクセストークンが無効か期限切れ")
                # トークンの再取得が必要だが、ここでは単純に失敗として扱う
                break
            elif cancel_response.status_code == 422:
                # バリデーションエラー
                logger.error(f"PayPal注文キャンセル処理エラー (422): {order_id}")
                logger.debug(f"詳細レスポンス: {cancel_response.text}")
                # 注文の状態が既にキャンセル不可の状態（完了済みなど）
                break
            else:
                logger.error(f"PayPal注文キャンセルエラー: {order_id}, ステータス: {cancel_response.status_code}")
                logger.debug(f"レスポンス: {cancel_response.text[:500]}")
                
                retry_count += 1
                if retry_count < max_retries:
                    # 指数バックオフでリトライ（1秒、2秒、4秒...）
                    wait_time = 2 ** (retry_count - 1)
                    logger.info(f"リトライ {retry_count}/{max_retries} を {wait_time}秒後に実行します...")
                    time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            logger.error(f"PayPal API接続エラー: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                # 指数バックオフでリトライ
                wait_time = 2 ** (retry_count - 1)
                logger.info(f"リトライ {retry_count}/{max_retries} を {wait_time}秒後に実行します...")
                time.sleep(wait_time)
    
    return cancel_success

def check_order_status(api_base, order_id, headers):
    """
    PayPal注文の状態を確認する関数
    
    Args:
        api_base: PayPal APIのベースURL
        order_id: 確認する注文のID
        headers: リクエストヘッダー（認証トークンを含む）
        
    Returns:
        tuple: (成功したかどうか, 注文のステータス, レスポンス本文)
    """
    try:
        # セッションを使用してHTTPリトライを設定
        session = requests.Session()
        retry_strategy = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 注文情報を取得
        get_url = f"{api_base}/v2/checkout/orders/{order_id}"
        get_response = session.get(get_url, headers=headers, timeout=15)
        
        if get_response.status_code == 200:
            order_data = get_response.json()
            order_status = order_data.get('status', '')
            logger.info(f"PayPal注文状態: {order_id} = {order_status}")
            return True, order_status, get_response.text
        else:
            logger.error(f"PayPal注文情報取得エラー: {order_id}, ステータス: {get_response.status_code}")
            return False, None, get_response.text
    
    except requests.exceptions.RequestException as e:
        logger.error(f"PayPal API接続エラー: {str(e)}")
        return False, None, str(e)
    except Exception as e:
        logger.error(f"PayPal注文状態確認中の例外: {str(e)}")
        return False, None, str(e)
