import os
import pdfplumber
import requests
import json
import csv
from datetime import datetime
from dotenv import load_dotenv
from extractors import extract_amount_and_customer

PDF_DIR = "pdfs"
RESULTS_DIR = "results"

load_dotenv()
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")

# PayPal APIのベースURL（モードに応じて変更）
API_BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"

def extract_text_from_pdf(pdf_path: str) -> str:
    """PDFからテキストを抽出"""
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or '' for page in pdf.pages)

def get_paypal_access_token() -> str:
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

def create_paypal_payment_link(amount: int, currency: str = "JPY", description: str = "") -> str:
    """PayPalの決済リンクを作成"""
    access_token = get_paypal_access_token()
    url = f"{API_BASE}/v2/checkout/orders"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": currency,
                    "value": str(amount)
                },
                "description": description[:127] if description else "PDF Payment"
            }
        ],
        "application_context": {
            "return_url": "https://example.com/return",
            "cancel_url": "https://example.com/cancel"
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    response_data = response.json()
    
    # リンクを探す
    for link in response_data["links"]:
        if link["rel"] == "approve":
            return link["href"]
    
    # リンクが見つからない場合
    return "リンクを取得できませんでした"

def save_to_csv(results):
    """処理結果をCSVファイルに保存"""
    if not os.path.exists(RESULTS_DIR):
        os.makedirs(RESULTS_DIR)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(RESULTS_DIR, f"payment_links_{timestamp}.csv")
    
    with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
        fieldnames = ['ファイル名', '顧客名', '金額', '決済リンク', '処理日時']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(result)
    
    return filename

def main():
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        print("PayPalのAPIキーが設定されていません。.envファイルを確認してください。")
        return
        
    if not os.path.exists(PDF_DIR):
        print(f"{PDF_DIR} フォルダが存在しません。作成します。")
        os.makedirs(PDF_DIR)
        print(f"PDFファイルを {PDF_DIR} フォルダに配置してから再実行してください。")
        return
        
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("PDFファイルが見つかりません。")
        return
        
    results = []
    for pdf_file in pdf_files:
        pdf_path = os.path.join(PDF_DIR, pdf_file)
        print(f"\n--- 処理中: {pdf_file} ---")
        
        # PDFからテキスト抽出
        text = extract_text_from_pdf(pdf_path)
        print(f"テキスト抽出完了: {len(text)} 文字")
        
        # 金額と顧客名を抽出
        amount, customer_name = extract_amount_and_customer(text)
        
        if not amount:
            print("警告: 金額を自動検出できませんでした。デフォルト値を使用します。")
            amount = 1000  # デフォルト金額
        
        customer_display = customer_name if customer_name else "不明"
        print(f"顧客名: {customer_display}")
        print(f"金額: {amount}円")
        
        # 決済リンク作成
        description = f"{customer_display if customer_display != '不明' else ''} {pdf_file}".strip()
        try:
            payment_url = create_paypal_payment_link(amount, "JPY", description)
            print(f"決済リンク生成完了: {payment_url}")
            status = "成功"
        except Exception as e:
            payment_url = "エラー: " + str(e)
            print(f"決済リンク生成失敗: {str(e)}")
            status = "失敗"
        
        # 結果を記録
        results.append({
            'ファイル名': pdf_file,
            '顧客名': customer_display,
            '金額': amount,
            '決済リンク': payment_url,
            '処理日時': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    # 結果をCSVに保存
    if results:
        csv_path = save_to_csv(results)
        print(f"\n処理結果をCSVに保存しました: {csv_path}")
        print(f"処理済みPDF: {len(results)}件")

if __name__ == "__main__":
    main()
