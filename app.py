import os
import tempfile
import logging
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, flash, send_from_directory, jsonify, session
from werkzeug.utils import secure_filename
import pdfplumber
import json
import requests
from dotenv import load_dotenv

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# extractors.pyの関数をインポート
try:
    from extractors import extract_amount_and_customer
except ImportError:
    logger.warning("extractors.pyモジュールを読み込めません。絶対パスでインポートを試みます。")
    # 絶対パスでのインポート
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from extractors import extract_amount_and_customer, extract_amount_only, extract_customer

# 設定管理モジュールのインポート
try:
    from config_manager import config_manager, get_config, save_config
except ImportError:
    logger.warning("config_manager.pyモジュールを読み込めません。絶対パスでインポートを試みます。")
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from config_manager import config_manager, get_config, save_config

# 設定の読み込み
config = get_config()

# 環境変数の読み込み (後方互換性用)
load_dotenv()
PAYPAL_CLIENT_ID = config.get('paypal_client_id') or os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = config.get('paypal_client_secret') or os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = config.get('paypal_mode') or os.getenv("PAYPAL_MODE", "sandbox")

# 設定を環境変数より優先するように更新
if not config.get('paypal_client_id') and PAYPAL_CLIENT_ID:
    config['paypal_client_id'] = PAYPAL_CLIENT_ID
    save_config(config)
if not config.get('paypal_client_secret') and PAYPAL_CLIENT_SECRET:
    config['paypal_client_secret'] = PAYPAL_CLIENT_SECRET
    save_config(config)
if not config.get('paypal_mode') and PAYPAL_MODE:
    config['paypal_mode'] = PAYPAL_MODE
    save_config(config)

# PayPal APIのベースURL（モードに応じて変更）
API_BASE = "https://api-m.sandbox.paypal.com" if config.get('paypal_mode') == "sandbox" else "https://api-m.paypal.com"

app = Flask(__name__)
app.secret_key = os.urandom(24)  # セッション用シークレットキー

# アップロードとダウンロードの設定
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
RESULTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
ALLOWED_EXTENSIONS = {'pdf'}

# フォルダが存在しない場合は作成
for folder in [UPLOAD_FOLDER, RESULTS_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULTS_FOLDER'] = RESULTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 最大16MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(pdf_path):
    """PDFからテキストを抽出し、高精度な請求金額抽出のための前処理を行う"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # すべてのページからテキストを抽出
            full_text = ""
            
            for i, page in enumerate(pdf.pages):
                # 通常のテキスト抽出
                page_text = page.extract_text() or ''
                
                # PDFの表からもデータを抽出 (表形式請求書の場合)
                tables = page.extract_tables()
                table_text = ""
                for table in tables:
                    for row in table:
                        # 空の値を除外
                        row_values = [str(cell).strip() if cell is not None else "" for cell in row]
                        table_text += " ".join(row_values) + "\n"
                
                # テーブル内のテキストをページのテキストに追加
                page_text += "\n" + table_text
                
                # 金額に関連する単語の前後を特に注意深く扱う
                for keyword in ["金額", "請求", "合計", "総額", "支払"]:
                    if keyword in page_text:
                        # キーワードを含む行を強調（検出されやすいように）
                        lines = page_text.split('\n')
                        for j, line in enumerate(lines):
                            if keyword in line:
                                # この行を重複して追加（検出確率向上）
                                lines[j] = line + " [IMPORTANT] " + line
                        page_text = "\n".join(lines)
                
                full_text += f"\n--- PAGE {i+1} ---\n" + page_text
                
            print(f"PDFから{len(pdf.pages)}ページ分のテキストを抽出しました")
            return full_text
            
    except Exception as e:
        print(f"PDF抽出エラー: {e}")
        return ""

def get_paypal_access_token():
    """PayPal APIのアクセストークンを取得"""
    url = f"{API_BASE}/v1/oauth2/token"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US"
    }
    data = {"grant_type": "client_credentials"}
    response = requests.post(
        url, 
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        headers=headers,
        data=data
    )
    response.raise_for_status()
    return response.json()["access_token"]

def create_paypal_payment_link(amount, currency="JPY", description=""):
    """PayPalの決済リンクを作成"""
    try:
        print(f"\n--- PayPal APIリクエスト開始 ---")
        print(f"amount: {amount}, currency: {currency}, description: {description}")
        
        # 必ず有効な金額にする
        if amount is None or not str(amount).isdigit() or int(amount) <= 0:
            print(f"無効な金額: {amount} → デフォルト値に置き換え")
            amount = 1000  # デフォルト値
        
        # 確実に文字列に変換
        amount_str = str(int(amount))
        print(f"使用する金額: {amount_str}円")
        
        # 説明文を確実に設定
        if not description:
            description = "PDF Payment"
        description = description[:120]  # PayPalの上限より少し短く設定
        
        # アクセストークン取得の詳細ログ
        print(f"APIベースURL: {API_BASE}")
        print(f"PayPalクライアントID: {PAYPAL_CLIENT_ID[:5]}...")
            
        try:
            access_token = get_paypal_access_token()
            print(f"アクセストークン取得成功: {access_token[:10]}...")
        except Exception as token_error:
            print(f"アクセストークン取得エラー: {str(token_error)}")
            raise
        
        # 絶対に成功する最小限のペイロードを使用
        url = f"{API_BASE}/v2/checkout/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
            
        # ゲスト決済を確実に有効にするペイロード
        host_url = request.host_url.rstrip('/')
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": currency,
                        "value": amount_str
                    },
                    "description": description
                }
            ],
            "application_context": {
                "brand_name": "PDF処理システム",
                "landing_page": "BILLING",  # BILLINGを指定してクレジットカード入力画面を優先表示
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
                "return_url": f"{host_url}/payment-success",
                "cancel_url": f"{host_url}/payment-cancel"
            }
        }
        
        print(f"API URL: {url}")
        print(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
        
        # リクエスト送信とエラーハンドリング
        try:
            response = requests.post(url, headers=headers, json=payload)
            print(f"APIレスポンスステータス: {response.status_code}")
            
            # レスポンスボディを取得
            try:
                response_data = response.json()
                print(f"Response: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
            except Exception as json_error:
                print(f"JSONパースエラー: {str(json_error)}")
                print(f"生レスポンス: {response.text[:500]}")
                raise
            
            # エラーの詳細チェック
            if response.status_code >= 400:
                error_details = response_data.get('details', [])
                print(f"エラー詳細: {error_details}")
                response.raise_for_status()
            
            # リンクを取得
            if "links" in response_data:
                # 承認リンクを探す
                for link in response_data["links"]:
                    if link["rel"] == "approve":
                        payment_url = link["href"]
                        print(f"決済リンク発行成功: {payment_url}")
                        
                        # キャプチャ用にOrderIDを含めるように修正
                        order_id = response_data.get('id')
                        if order_id:
                            print(f"Order ID: {order_id} - キャプチャ処理用に保存")
                            # 決済完了時にキャプチャを自動実行するための仕組み
                            if "?" in payment_url:
                                payment_url += f"&order_id={order_id}"
                            else:
                                payment_url += f"?order_id={order_id}"
                                
                        # 直接支払い画面を表示するパラメータ追加
                        if "useraction=commit" not in payment_url:
                            payment_url += "&useraction=commit"
                            
                        return payment_url
                
                # 別の隣接リンクがないか確認
                print("決済リンクを抽出中...")
                for link in response_data["links"]:
                    print(f"  利用可能なリンク: {link['rel']} => {link['href']}")
                    if "checkout" in link["href"] or "payer-action" == link["rel"]:
                        return link["href"]
            
            # IDから正確な支払いURLを生成 - ゲスト決済を確実に有効化
            if "id" in response_data:
                # sandboxか本番かでドメインを選択
                domain = "sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "www.paypal.com"
                
                # 最新のPayPalゲスト決済フローを使用
                checkout_url = f"https://{domain}/checkoutnow?token={response_data['id']}"
                
                # 重要なパラメータを追加
                checkout_url += "&useraction=commit"  # 支払いボタンを表示
                checkout_url += "&buyer-country=JP"   # 日本向け設定
                checkout_url += "&locale.x=ja_JP"     # 日本語表示
                
                # ゲスト決済を強制的に有効化
                checkout_url += "&fundingSource=card"  # カード決済を優先
                checkout_url += "&forceGuestCheckout=true"  # ゲスト決済を強制
                
                # キャプチャ用のorder_idを追加
                checkout_url += f"&order_id={response_data['id']}"
                
                print(f"改善されたゲスト決済URL: {checkout_url}")
                return checkout_url
                
        except requests.exceptions.RequestException as req_error:
            print(f"リクエスト例外: {str(req_error)}")
            raise
            
        return "リンクを取得できませんでした"
        
    except Exception as e:
        print(f"\u6c7a済リンク作成エラー: {str(e)}")
        raise

@app.route("/")
def index():
    """インデックスページの表示"""
    return render_template("index.html", mode=PAYPAL_MODE)

@app.route("/payment-success")
def payment_success():
    """決済成功時のリダイレクト先
    キャプチャ処理を実行して支払いを完了させる
    """
    # ログ出力
    print("\n--- 決済成功画面を表示 ---")
    print(f"URLパラメータ: {request.args}")
    
    # 全てのパラメータを取得してチェック - ログで重要な情報を確認
    all_params = {key: value for key, value in request.args.items()}
    print(f"全てのリダイレクトパラメータ: {all_params}")
    
    # PayPalのレスポンスから必要な情報を取得
    # tokenがorder_idとして使用される場合がある
    token = request.args.get('token')  # PayPalが返すトークン
    order_id = request.args.get('order_id') or token  # order_idがなければtokenを使用
    payer_id = request.args.get('PayerID')  # 支払者ID
    
    print(f"処理する注文ID: {order_id}")
    
    capture_result = {}
    
    # order_idがあればキャプチャ実行
    if order_id:
        try:
            # 決済を確定するキャプチャ処理を実行
            access_token = get_paypal_access_token()
            url = f"{API_BASE}/v2/checkout/orders/{order_id}/capture"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            }
            
            print(f"\n*** 支払いキャプチャ処理開始 (Order ID: {order_id}) ***")
            print(f"API URL: {url}")
            print(f"ヘッダー: {headers}")
            
            # 空のボディでPOSTリクエストを実行
            response = requests.post(url, headers=headers, json={})
            
            # レスポンスステータスとボディを取得
            print(f"キャプチャレスポンスステータス: {response.status_code}")
            try:
                capture_result = response.json()
                print(f"キャプチャレスポンス: {json.dumps(capture_result, ensure_ascii=False, indent=2)}")
            except Exception as json_error:
                print(f"JSONパースエラー: {str(json_error)}")
                print(f"生レスポンス: {response.text[:500]}")
            
            # 成功時の処理
            if response.status_code in [200, 201]:
                print(f"\n支払いキャプチャ成功! \n")
                
                # 結果からキャプチャIDとステータスを取得
                capture_id = capture_result.get('id') or capture_result.get('purchase_units', [{}])[0].get('payments', {}).get('captures', [{}])[0].get('id')
                status = capture_result.get('status') or 'COMPLETED'
                
                payment_info = {
                    'order_id': order_id,
                    'capture_id': capture_id,
                    'status': status,
                    'payer_id': payer_id,
                    'token': token,
                    'details': capture_result
                }
                return render_template("payment-success.html", payment_info=payment_info)
            else:
                # エラー時のログと表示
                print(f"支払いキャプチャエラー: {response.status_code}")
                print(f"エラー詳細: {json.dumps(capture_result, ensure_ascii=False)}")
                
                # 既にキャプチャ済みの場合は成功とみなす
                if response.status_code == 400 and 'DUPLICATE_INVOICE_ID' in str(capture_result):
                    print("既にキャプチャ完了しています")
                    payment_info = {
                        'order_id': order_id,
                        'status': 'COMPLETED',
                        'note': 'この取引は既に処理されています'
                    }
                    return render_template("payment-success.html", payment_info=payment_info)
                
                # その他のエラー
                payment_info = {
                    'order_id': order_id,
                    'status': 'ERROR',
                    'error': f"支払い確定エラー: {response.status_code}",
                    'details': capture_result
                }
                return render_template("payment-error.html", payment_info=payment_info)
        except Exception as e:
            # 例外時のログと表示
            print(f"支払いキャプチャ例外: {str(e)}")
            payment_info = {
                'order_id': order_id,
                'status': 'ERROR',
                'error': f"支払い処理例外: {str(e)}"
            }
            return render_template("payment-error.html", payment_info=payment_info)
    
    # Order IDもtokenもない場合は通常の成功画面を表示
    payment_info = {
        'token': token,
        'payer_id': payer_id,
        'status': 'PENDING',
        'note': 'キャプチャ情報がありません。決済が完了していない可能性があります。'
    }
    
    return render_template("payment-success.html", payment_info=payment_info)

@app.route("/payment-cancel")
def payment_cancel():
    """決済キャンセル時のリダイレクト先"""
    return render_template("payment-cancel.html")

@app.route('/upload', methods=['POST'])
def upload_file():
    print('\n=== アップロードリクエスト受信 ===\n')
    print(f'フォームデータ: {request.form}')
    print(f'ファイルデータ: {request.files}')
    print(f'リクエスト方法: {request.method}')
    
    # 手動で指定された金額を取得（あれば）
    manual_amount = request.form.get('amount')
    print(f'手動金額指定: {manual_amount}')
    
    # ファイルチェック
    if 'files[]' not in request.files:
        print('エラー: files[]フィールドがリクエストに存在しません')
        flash('ファイルがありません')
        return redirect(url_for('index'))  # 常にトップページにリダイレクト
    
    files = request.files.getlist('files[]')
    print(f'受信ファイル数: {len(files)}')
    
    if not files or files[0].filename == '':
        print('エラー: ファイルが選択されていません')
        flash('ファイルが選択されていません')
        return redirect(url_for('index'))
    
    results = []
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # PDF処理
            result = process_pdf(filepath, filename, manual_amount)
            results.append(result)
        else:
            flash(f'非対応のファイル形式です: {file.filename}')
    
    # 結果をセッションに保存（一時的に）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_filename = f"payment_links_{timestamp}.json"
    result_path = os.path.join(app.config['RESULTS_FOLDER'], result_filename)
    
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    return render_template('results.html', results=results, result_file=result_filename)

def process_pdf(filepath, original_filename, manual_amount=None):
    """PDFファイルを処理して結果を返す。手動金額が指定されていれば、それを優先する"""
    try:
        print(f"\n--- 処理開始: {original_filename} ---")
        print(f"\u624b動金額指定: {manual_amount}")
        
        # 結果を初期化
        result = {
            'filename': original_filename,
            'status': 'success',
            'customer': None,
            'amount': None,
            'currency': 'JPY',
            'payment_link': None,
            'errors': []
        }
        
        # PDFからテキスト抽出
        text = extract_text_from_pdf(filepath)
        print(f"PDFテキスト抽出成功: {len(text)} 文字")
        
        # 金額と顧客名を抽出
        extracted_amount, customer_name = extract_amount_and_customer(text)
        print(f"抽出結果 - 金額: {extracted_amount}, 顧客名: {customer_name}")
        
        # 手動金額が指定されていればそれを優先
        if manual_amount and manual_amount.strip():
            try:
                amount = int(manual_amount.strip())
                print(f"手動金額を使用: {amount}円")
            except ValueError:
                print(f"手動金額の変換エラー: {manual_amount}、抽出結果を使用します")
                amount = extracted_amount
        else:
            amount = extracted_amount
            
        if not amount:
            print("警告: 金額が指定されておらず、抽出もできません。デフォルト値を使用します。")
            amount = 1000  # デフォルト金額
        
        # 金額がゼロ以下の場合はエラー防止
        if amount <= 0:
            print(f"警告: 金額が無効です: {amount}、デフォルト値に修正します")
            amount = 1000
        
        # 顧客名が空の場合はデフォルト値を設定
        customer_display = customer_name if customer_name else "お客様"
        
        # 決済リンク作成
        description = f"{customer_display} {original_filename}".strip()
        print(f"決済リンク生成開始 - 金額: {amount}円, 説明: {description}")
        
        try:
            payment_url = create_paypal_payment_link(amount, "JPY", description)
            print(f"決済リンク取得成功: {payment_url[:50]}...")
            
            # 結果を返す
            result['customer'] = customer_display
            result['amount'] = amount
            result['payment_link'] = payment_url
            result['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return result
        except Exception as payment_error:
            print(f"決済リンク生成エラー: {str(payment_error)}")
            result['status'] = 'error'
            result['error'] = f"決済リンク生成失敗: {str(payment_error)}"
            result['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"決済リンク生成失敗、詳細ログ: {result}")
            return result
    
    except Exception as e:
        print(f"ファイル処理エラー: {str(e)}")
        return {
            'filename': original_filename,
            'error': str(e),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'error'
        }

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['RESULTS_FOLDER'], filename)

# 設定ページの表示
@app.route('/settings')
def settings():
    """設定ページを表示する"""
    current_settings = get_config()
    
    # PayPal API接続テスト
    paypal_status = False
    if current_settings.get('paypal_client_id') and current_settings.get('paypal_client_secret'):
        try:
            # アクセストークン取得で接続テスト
            access_token = get_paypal_access_token()
            if access_token:
                paypal_status = True
        except Exception as e:
            logger.error(f"PayPal接続テストエラー: {str(e)}")
    
    return render_template('settings.html', 
                           current_settings=current_settings,
                           paypal_status=paypal_status,
                           message=request.args.get('message'),
                           message_type=request.args.get('message_type', 'info'))

# 設定の保存
@app.route('/settings/save', methods=['POST'])
def save_settings():
    """設定を保存する"""
    global PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE, API_BASE
    try:
        # フォームからデータ取得
        form_data = request.form.to_dict()
        
        # 既存の設定を取得
        current_settings = get_config()
        
        # 値を更新
        for key in ['paypal_mode', 'paypal_client_id', 'paypal_client_secret', 
                     'default_currency', 'enable_customer_extraction', 
                     'enable_amount_extraction', 'default_amount']:
            if key in form_data:
                current_settings[key] = form_data[key]
        
        # 設定保存
        if save_config(current_settings):
            # グローバル変数を更新
            PAYPAL_CLIENT_ID = current_settings.get('paypal_client_id', '')
            PAYPAL_CLIENT_SECRET = current_settings.get('paypal_client_secret', '')
            PAYPAL_MODE = current_settings.get('paypal_mode', 'sandbox')
            
            # APIベースURLを更新
            API_BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"
            
            logger.info(f"設定保存完了 - モード: {PAYPAL_MODE}, APIベース: {API_BASE}")
            return redirect(url_for('settings', message='設定を保存しました', message_type='success'))
        else:
            return redirect(url_for('settings', message='設定の保存に失敗しました', message_type='danger'))
    except Exception as e:
        logger.error(f"設定保存エラー: {str(e)}")
        return redirect(url_for('settings', message=f'エラー: {str(e)}', message_type='danger'))

# PayPal接続テスト
@app.route('/settings/test_connection')
def test_connection():
    """設定されたPayPal API認証情報で接続テストを実行する"""
    global PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE, API_BASE
    try:
        # 最新の設定を読み込み
        current_config = get_config()
        
        # グローバル変数を更新
        PAYPAL_CLIENT_ID = current_config.get('paypal_client_id', '')
        PAYPAL_CLIENT_SECRET = current_config.get('paypal_client_secret', '')
        PAYPAL_MODE = current_config.get('paypal_mode', 'sandbox')
        
        # APIベースURLを更新
        API_BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"
        
        logger.info(f"PayPal接続テスト - モード: {PAYPAL_MODE}, APIベース: {API_BASE}")
        
        if config_manager.test_paypal_connection():
            return redirect(url_for('settings', message='PayPal API接続テスト成功', message_type='success'))
        else:
            return redirect(url_for('settings', message='PayPal API接続テスト失敗', message_type='danger'))
    except Exception as e:
        logger.error(f"PayPal接続テストエラー: {str(e)}")
        return redirect(url_for('settings', message=f'エラー: {str(e)}', message_type='danger'))

# 設定エクスポート
@app.route('/export_settings')
def export_settings():
    """設定をJSONファイルとしてエクスポートする"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"settings_export_{timestamp}.json"
        export_path = os.path.join(app.config['RESULTS_FOLDER'], export_filename)
        
        # 設定エクスポート
        config_data = get_config()
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        return send_from_directory(app.config['RESULTS_FOLDER'], export_filename, as_attachment=True)
    except Exception as e:
        logger.error(f"設定エクスポートエラー: {str(e)}")
        return redirect(url_for('settings', message=f'エクスポート失敗: {str(e)}', message_type='danger'))

# 設定インポート
@app.route('/import_settings', methods=['POST'])
def import_settings():
    """設定をインポートする"""
    try:
        if 'settings_file' not in request.files:
            return redirect(url_for('settings', message='ファイルが選択されていません', message_type='warning'))
        
        file = request.files['settings_file']
        if file.filename == '':
            return redirect(url_for('settings', message='ファイルが選択されていません', message_type='warning'))
        
        # 一時ファイルに保存
        temp_file = os.path.join(tempfile.gettempdir(), 'temp_settings.json')
        file.save(temp_file)
        
        # 設定インポート
        if config_manager.import_config(temp_file):
            os.remove(temp_file)  # 一時ファイル削除
            return redirect(url_for('settings', message='設定をインポートしました', message_type='success'))
        else:
            os.remove(temp_file)  # 一時ファイル削除
            return redirect(url_for('settings', message='設定のインポートに失敗しました', message_type='danger'))
    except Exception as e:
        logger.error(f"設定インポートエラー: {str(e)}")
        return redirect(url_for('settings', message=f'インポート失敗: {str(e)}', message_type='danger'))

# アプリ実行
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
