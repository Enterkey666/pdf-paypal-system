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

# AI OCRモジュールのインポート
try:
    # パスを確実に追加
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    from ai_ocr import AIOCR, process_pdf_with_ai_ocr
    logger.info("AI OCRモジュールを正常に読み込みました。")
    AI_OCR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"AI OCRモジュールを読み込めません: {str(e)}")
    logger.warning("従来の抽出方法を使用します。")
    AI_OCR_AVAILABLE = False
    process_pdf_with_ai_ocr = None

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

# PayPal APIのベースURLは各関数で最新の設定から取得するように変更
# これにより、設定変更時に全ての機能が正しく動作する
# API_BASE = "https://api-m.sandbox.paypal.com" if config.get('paypal_mode') == "sandbox" else "https://api-m.paypal.com"

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
    # 最新の設定を取得
    config = get_config()
    paypal_mode = config.get('paypal_mode', 'sandbox')
    client_id = config.get('paypal_client_id', '')
    client_secret = config.get('paypal_client_secret', '')
    
    # モードに応じたAPIベースURLを設定
    api_base = "https://api-m.sandbox.paypal.com" if paypal_mode == "sandbox" else "https://api-m.paypal.com"
    
    url = f"{api_base}/v1/oauth2/token"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US"
    }
    data = {"grant_type": "client_credentials"}
    
    print(f"PayPal API接続試行: モード={paypal_mode}, API URL={api_base}")
    
    response = requests.post(
        url, 
        auth=(client_id, client_secret),
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
        
        # 最新の設定を取得
        config = get_config()
        paypal_mode = config.get('paypal_mode', 'sandbox')
        
        # モードに応じたAPIベースURLを設定
        api_base = "https://api-m.sandbox.paypal.com" if paypal_mode == "sandbox" else "https://api-m.paypal.com"
        
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
        print(f"APIベースURL: {api_base}")
        print(f"PayPalモード: {paypal_mode}")
            
        try:
            access_token = get_paypal_access_token()
            print(f"アクセストークン取得成功: {access_token[:10]}...")
        except Exception as token_error:
            print(f"アクセストークン取得エラー: {str(token_error)}")
            raise
        
        # 絶対に成功する最小限のペイロードを使用
        url = f"{api_base}/v2/checkout/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
            
        # 最小限のペイロードで確実に成功させる
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
                "return_url": f"{host_url}/payment-success",
                "cancel_url": f"{host_url}/payment-cancel",
                "brand_name": "PDF処理システム",
                "landing_page": "BILLING",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW"
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
            
            # IDから正確な支払いURLを直接生成 - 必ずチェックアウト画面が表示されるように
            if "id" in response_data:
                # sandboxか本番かでドメインを選択
                domain = "sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "www.paypal.com"
                # 支払い画面を直接開くための正しいURL形式
                # checkout_url = f"https://www.{domain}/checkoutnow?token={response_data['id']}"
                checkout_url = f"https://www.{domain}/webapps/hermes?token={response_data['id']}&useraction=commit"
                print(f"手動作成した決済URL: {checkout_url}")
                # order_idパラメータを追加して自動キャプチャができるように
                checkout_url += f"&order_id={response_data['id']}"
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
    # 最新の設定を取得
    config = get_config()
    paypal_mode = config.get('paypal_mode', 'sandbox')
    return render_template("index.html", mode=paypal_mode, paypal_mode=paypal_mode)

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
    print(f'ファイルデータのキー: {list(request.files.keys())}')
    print(f'リクエスト方法: {request.method}')
    
    # 手動で指定された金額を取得（あれば）
    manual_amount = request.form.get('amount')
    print(f'手動金額指定: {manual_amount}')
    
    # ファイルチェック - 複数の可能性のあるキー名をチェック
    file_keys = ['files[]', 'file', 'files']
    found_key = None
    
    for key in file_keys:
        if key in request.files:
            found_key = key
            print(f'ファイルフィールドを検出: {key}')
            break
    
    if not found_key:
        print('エラー: ファイルフィールドがリクエストに存在しません')
        print(f'利用可能なキー: {list(request.files.keys())}')
        flash('ファイルがありません')
        return redirect(url_for('index'))  # 常にトップページにリダイレクト
    
    files = request.files.getlist(found_key)
    print(f'受信ファイル数: {len(files)}')
    print(f'ファイル名: {[f.filename for f in files]}')
    
    if not files or files[0].filename == '':
        print('エラー: ファイルが選択されていません')
        flash('ファイルが選択されていません')
        return redirect(url_for('index'))
    
    results = []
    
    for file in files:
        print(f'処理中のファイル: {file.filename}, MIME: {file.content_type}')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            print(f'ファイル保存完了: {filepath}')
            
            # PDF処理
            try:
                print(f'PDF処理開始: {filepath}')
                result = process_pdf(filepath, filename, manual_amount)
                print(f'PDF処理完了: {result}')
                
                # 処理結果のステータスを確認
                if isinstance(result, dict) and 'status' in result:
                    if result['status'] == 'error':
                        print(f'PDF処理エラー: {result.get("error", "")}')
                        flash(f'ファイル処理中にエラーが発生しました: {file.filename} - {result.get("error", "")}')
                    elif result['status'] == 'warning':
                        print(f'PDF処理警告: {result.get("error", "")}')
                        flash(result.get("error", ""), 'warning')
                        # 金額が抽出できなかった場合はホームページにリダイレクト
                        if 'PDFから金額を抽出できませんでした' in result.get("error", ""):
                            # 結果をセッションに保存しておく
                            return redirect(url_for('index'))
                
                # 正常な結果を追加
                results.append(result)
            except Exception as e:
                print(f'PDF処理例外: {str(e)}')
                flash(f'ファイル処理中に例外が発生しました: {file.filename} - {str(e)}')
                # エラー情報を結果に追加
                error_result = {
                    'filename': filename,
                    'status': 'error',
                    'error': str(e),
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                results.append(error_result)
        else:
            print(f'非対応のファイル形式: {file.filename}')
            flash(f'非対応のファイル形式です: {file.filename}')
    
    # 結果が空の場合はホームページにリダイレクト
    if not results:
        flash('処理可能な結果がありませんでした。別のPDFファイルを試してください。', 'warning')
        return redirect(url_for('index'))
    
    # 結果をJSONファイルに保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_filename = f"payment_links_{timestamp}.json"
    result_path = os.path.join(app.config['RESULTS_FOLDER'], result_filename)
    
    try:
        # 結果をJSON形式で保存
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        return render_template('results.html', results=results, result_file=result_filename)
    except Exception as e:
        print(f'JSON保存エラー: {str(e)}')
        # JSON化できないオブジェクトがある場合のデバッグ
        for i, result in enumerate(results):
            print(f'Result {i}: {type(result)}')
            if not isinstance(result, dict):
                print(f'  Non-dict result: {result}')
                # 辞書に変換して置き換え
                results[i] = {
                    'filename': f'unknown_{i}',
                    'status': 'error',
                    'error': f'不正な結果タイプ: {type(result)}',
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
        
        # 再試行
        try:
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            return render_template('results.html', results=results, result_file=result_filename)
        except Exception as e2:
            print(f'再試行も失敗: {str(e2)}')
            flash('結果の保存中にエラーが発生しました。管理者にお問い合わせください。', 'error')
            return redirect(url_for('index'))

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
        
        # 手動金額が指定されている場合
        if manual_amount is not None and manual_amount.strip():
            try:
                # 手動入力された金額を使用
                amount = int(manual_amount.strip())
                # PDFからテキスト抽出
                text = extract_text_from_pdf(filepath)
                # 顧客名のみを抽出
                customer = extract_customer(text)
                logger.info(f"手動金額を使用: {amount}円, 顧客名: {customer}")
            except ValueError:
                logger.error('手動入力された金額が無効です')
                return {
                    'filename': original_filename,
                    'status': 'error',
                    'error': '手動入力された金額が無効です。数値を入力してください。',
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
        else:
            # AI OCRを使用して金額と顧客名を抽出
            use_ai_ocr = get_config().get('use_ai_ocr', False)
            
            if use_ai_ocr and 'AI_OCR_AVAILABLE' in globals() and AI_OCR_AVAILABLE:
                # AI OCR設定
                ocr_config = {
                    'ocr_method': get_config().get('ocr_method', 'tesseract'),
                    'api_key': get_config().get('ocr_api_key', ''),
                    'endpoint': get_config().get('ocr_endpoint', '')
                }
                
                # AI OCRで処理
                logger.info(f"AI OCRを使用してPDFを処理します: {original_filename}")
                amount, customer = process_pdf_with_ai_ocr(filepath, ocr_config)
                logger.info(f"AI OCR抽出結果: 金額={amount}円, 顧客名={customer}")
            else:
                # 従来の方法で処理
                logger.info(f"従来の方法でPDFを処理します: {original_filename}")
                text = extract_text_from_pdf(filepath)
                amount, customer = extract_amount_and_customer(text)
            
        if not amount:
            logger.warning('PDFから金額を抽出できませんでした')
            # セッションに情報を保存しておく
            session['last_uploaded_file'] = filepath
            session['original_filename'] = original_filename
            
            return {
                'filename': original_filename,
                'status': 'warning',
                'error': 'PDFから金額を抽出できませんでした。手動で金額を入力してください。',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        # 顧客名が空の場合はデフォルト値を設定
        customer_display = customer if customer else "お客様"
        
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
@app.route('/settings', methods=['GET'])
def settings():
    """設定ページを表示する"""
    # 現在の設定を取得
    config = get_config()
    
    # PayPal設定
    paypal_client_id = config.get('paypal_client_id', '')
    paypal_client_secret = config.get('paypal_client_secret', '')
    paypal_mode = config.get('paypal_mode', 'sandbox')
    
    # OCR設定
    use_ai_ocr = config.get('use_ai_ocr', False)
    ocr_method = config.get('ocr_method', 'tesseract')
    ocr_api_key = config.get('ocr_api_key', '')
    ocr_endpoint = config.get('ocr_endpoint', '')
    
    # マスク処理（セキュリティのため）
    masked_client_secret = "*" * 8
    if paypal_client_secret:
        masked_client_secret = paypal_client_secret[:4] + "*" * (len(paypal_client_secret) - 8) + paypal_client_secret[-4:]
    
    masked_ocr_api_key = "*" * 8
    if ocr_api_key:
        masked_ocr_api_key = ocr_api_key[:4] + "*" * (len(ocr_api_key) - 8) + ocr_api_key[-4:] if len(ocr_api_key) > 8 else "*" * len(ocr_api_key)
    
    # テンプレートで使用するcurrent_settings変数を追加
    current_settings = {
        'paypal_client_id': paypal_client_id,
        'paypal_client_secret': paypal_client_secret,
        'paypal_mode': paypal_mode,
        'use_ai_ocr': use_ai_ocr,
        'ocr_method': ocr_method,
        'ocr_api_key': ocr_api_key,
        'ocr_endpoint': ocr_endpoint,
        'enable_customer_extraction': config.get('enable_customer_extraction', '1'),
        'enable_amount_extraction': config.get('enable_amount_extraction', '1'),
        'default_currency': config.get('default_currency', 'JPY')
    }
    
    # PayPal接続状態の確認
    paypal_status = False
    if paypal_client_id and paypal_client_secret:
        try:
            print(f"PayPal接続確認中... モード: {paypal_mode}")
            token = get_paypal_access_token()
            paypal_status = token is not None
            print(f"PayPal接続確認結果: {paypal_status}")
        except Exception as e:
            print(f"PayPal接続確認エラー: {str(e)}")
            paypal_status = False
    
    return render_template('settings.html', 
                           current_settings=current_settings,
                           paypal_client_id=paypal_client_id,
                           paypal_client_secret=masked_client_secret,
                           paypal_mode=paypal_mode,
                           use_ai_ocr=use_ai_ocr,
                           ocr_method=ocr_method,
                           ocr_api_key=masked_ocr_api_key,
                           ocr_endpoint=ocr_endpoint,
                           paypal_status=paypal_status)

# 設定の保存
@app.route('/settings/save', methods=['POST'])
def save_settings():
    """設定を保存する"""
    try:
        # 現在の設定を取得
        config = get_config()
        
        # フォームから値を取得
        paypal_client_id = request.form.get('paypal_client_id', '')
        paypal_client_secret = request.form.get('paypal_client_secret', '')
        paypal_mode = request.form.get('paypal_mode', 'sandbox')
        
        # OCR設定を取得
        use_ai_ocr = request.form.get('use_ai_ocr') == 'on'
        ocr_method = request.form.get('ocr_method', 'tesseract')
        ocr_api_key = request.form.get('ocr_api_key', '')
        ocr_endpoint = request.form.get('ocr_endpoint', '')
        
        # 設定を更新
        if paypal_client_id:
            config['paypal_client_id'] = paypal_client_id
        
        # クライアントシークレットが変更された場合のみ更新（マスク処理対応）
        if paypal_client_secret and '*' not in paypal_client_secret:
            config['paypal_client_secret'] = paypal_client_secret
        
        config['paypal_mode'] = paypal_mode
        
        # OCR設定を更新
        config['use_ai_ocr'] = use_ai_ocr
        config['ocr_method'] = ocr_method
        
        # APIキーが変更された場合のみ更新（マスク処理対応）
        if ocr_api_key and '*' not in ocr_api_key:
            config['ocr_api_key'] = ocr_api_key
            
        config['ocr_endpoint'] = ocr_endpoint
        
        # 設定を保存
        save_config(config)
        
        # グローバル変数の更新は行わず、各関数で最新の設定を取得するようにした
        # これにより、設定変更時に全ての機能が正しく動作する
        
        # 接続確認を再実行して状態を更新
        try:
            token = get_paypal_access_token()
            print(f"PayPal接続確認結果: {token is not None}")
        except Exception as e:
            print(f"PayPal接続確認エラー: {str(e)}")
        
        flash('設定を保存しました。', 'success')
    except Exception as e:
        logger.error(f"設定保存エラー: {str(e)}")
        flash(f'設定の保存に失敗しました: {str(e)}', 'error')
    
    return redirect(url_for('settings'))

# PayPal接続テスト
@app.route('/settings/test_connection', methods=['POST'])
def test_connection():
    """Provides PayPal API credentials from the request to test the connection."""
    try:
        data = request.get_json()
        client_id = data.get('paypal_client_id')
        client_secret = data.get('paypal_client_secret')
        mode = data.get('paypal_mode')

        if not client_id or not client_secret or not mode:
            return jsonify({'success': False, 'message': '必要な認証情報 (Client ID, Client Secret, Mode) が不足しています。'}), 400

        success, message = config_manager.test_paypal_connection(client_id, client_secret, mode)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"PayPal接続テスト中に予期せぬエラーが発生しました: {str(e)}")
        return jsonify({'success': False, 'message': f'サーバーエラーが発生しました: {str(e)}'}), 500

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

# 履歴一覧ページ
@app.route('/history')
def history():
    history_data = []
    try:
        results_folder = app.config['RESULTS_FOLDER']
        files = [f for f in os.listdir(results_folder) if f.startswith('payment_links_') and f.endswith('.json')]
        files.sort(reverse=True)
        
        # 各ファイルの内容を読み込み、顧客名情報を取得
        for file in files:
            file_path = os.path.join(results_folder, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 日付をファイル名から抽出
                    date_str = file.replace('payment_links_', '').replace('.json', '')
                    # YYYYMMDD_HHMMSS形式を読みやすい形式に変換
                    try:
                        date_obj = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                        formatted_date = date_obj.strftime("%Y年%m月%d日 %H:%M")
                    except:
                        formatted_date = date_str
                    
                    # 顧客名を取得
                    customers = []
                    for item in data:
                        customer = item.get('customer') or item.get('顧客名')
                        if customer and customer not in customers:
                            customers.append(customer)
                    
                    # 結果を追加
                    history_data.append({
                        'filename': file,
                        'date': formatted_date,
                        'customers': customers,
                        'count': len(data)
                    })
            except Exception as e:
                logger.error(f"履歴ファイル読み込みエラー ({file}): {str(e)}")
                # エラーがあってもファイル名だけは表示
                history_data.append({
                    'filename': file,
                    'date': file.replace('payment_links_', '').replace('.json', ''),
                    'customers': [],
                    'count': 0
                })
    except Exception as e:
        logger.error(f"履歴ファイル一覧取得エラー: {str(e)}")
    return render_template('history.html', history_data=history_data)

# PayPal決済状態の確認
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
            return "UNKNOWN"
            
        # アクセストークン取得
        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("PayPalアクセストークン取得失敗")
            return "UNKNOWN"
        
        # オーダー情報取得
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        order_url = f"{API_BASE}/v2/checkout/orders/{order_id}"
        response = requests.get(order_url, headers=headers)
        
        if response.status_code == 200:
            order_data = response.json()
            status = order_data.get("status", "")
            
            # 状態に応じて返却
            if status == "COMPLETED":
                return "COMPLETED"  # 支払い完了
            elif status == "APPROVED":
                return "PENDING"    # 承認済み（キャプチャ前）
            elif status == "CREATED":
                return "PENDING"    # 作成済み（支払い前）
            elif status == "VOIDED" or status == "PAYER_ACTION_REQUIRED":
                return "FAILED"     # 無効化または支払い操作必要
            else:
                return status        # その他の状態はそのまま返す
        else:
            logger.error(f"PayPal API エラー: {response.status_code}, {response.text}")
            return "UNKNOWN"
    except Exception as e:
        logger.error(f"決済状態確認エラー: {str(e)}")
        return "UNKNOWN"

# 履歴詳細ページ
@app.route('/history/<filename>')
def history_detail(filename):
    results = []
    try:
        results_folder = app.config['RESULTS_FOLDER']
        file_path = os.path.join(results_folder, filename)
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                results = json.load(f)
                
            # 各決済リンクの状態を確認
            for item in results:
                payment_link = item.get('payment_link') or item.get('決済リンク', '')
                # PayPalのURLからオーダーIDを抽出
                order_id = None
                if payment_link and 'token=' in payment_link:
                    order_id = payment_link.split('token=')[-1].split('&')[0]
                
                # 決済状態を確認して追加
                if order_id:
                    status = check_payment_status(order_id)
                    item['payment_status'] = status
                else:
                    item['payment_status'] = "UNKNOWN"
                    
    except Exception as e:
        logger.error(f"履歴詳細読み込みエラー: {str(e)}")
    return render_template('history_detail.html', filename=filename, results=results)

# アプリ実行
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
