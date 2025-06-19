#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Command-line tool for batch PDF export functionality
This script can be run directly to generate batch PDFs from history JSON files
"""

import os
import json
import uuid
import logging
import argparse
from datetime import datetime
from io import BytesIO
from xhtml2pdf import pisa
from PyPDF2 import PdfMerger
from jinja2 import Environment, FileSystemLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def render_template(template_name, **context):
    """
    Jinja2テンプレートをレンダリングする
    Flask関数のモックを含む
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    
    # Flaskの関数をモック
    def mock_url_for(endpoint, **kwargs):
        if endpoint == 'index':
            return '/'
        elif endpoint == 'static':
            return f"/static/{kwargs.get('filename', '')}"
        else:
            return f"/{endpoint}"
    
    # グローバル関数を追加
    env.globals['url_for'] = mock_url_for
    
    template = env.get_template(template_name)
    return template.render(**context)

def export_batch_pdf(filename, output_filename=None):
    """
    履歴ファイルから複数の決済結果をまとめてPDFでエクスポートする
    
    Args:
        filename: 履歴ファイル名
        output_filename: 出力ファイル名
        
    Returns:
        生成されたPDFファイルのパス
    """
    try:
        # セキュリティ対策としてファイル名を検証
        if '..' in filename or filename.startswith('/'):
            logger.warning(f"不正なファイルパス: {filename}")
            return None
            
        # ファイルパスの候補を作成
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path_candidates = [
            # 絶対パスとして指定された場合
            filename if os.path.isabs(filename) else None,
            # ベースディレクトリからの相対パス
            os.path.join(base_dir, filename),
            # resultsフォルダ内のファイル
            os.path.join(base_dir, 'results', filename),
            # カレントディレクトリからの相対パス
            os.path.join(os.getcwd(), filename),
            # カレントディレクトリのresultsフォルダ内のファイル
            os.path.join(os.getcwd(), 'results', filename),
        ]
        
        # Noneを除外
        path_candidates = [p for p in path_candidates if p]
        
        # ファイルが存在するパスを探す
        file_path = None
        for path in path_candidates:
            logger.info(f"ファイルパスを確認: {path}")
            if os.path.exists(path):
                file_path = path
                logger.info(f"ファイルが見つかりました: {file_path}")
                break
        
        if not file_path:
            logger.warning(f"履歴ファイルが見つかりません: {filename}")
            return None
        
        # ファイルの内容を読み込み
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
            logger.info(f"ファイル内容 (最初の200文字): {file_content[:200]}...")
            data = json.loads(file_content)
        
        # 日付を取得
        date_str = os.path.basename(filename).replace('payment_links_', '').replace('.json', '')
        if not date_str or not date_str[0].isdigit():
            date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # データ構造を確認して適切に処理
        logger.info(f"データ型: {type(data)}, キー: {list(data.keys()) if isinstance(data, dict) else 'リスト'}")
        
        if isinstance(data, dict) and 'results' in data:
            # 'results' キーがある場合はその中のリストを使用
            items = data['results']
            logger.info(f"'results'キーから{len(items)}件のアイテムを取得")
        elif isinstance(data, list):
            # データ自体がリストの場合はそのまま使用
            items = data
            logger.info(f"リストから{len(items)}件のアイテムを取得")
        else:
            # どちらでもない場合は空のリストとして扱う
            logger.warning(f"不正なデータ形式: {type(data)}")
            items = []
        
        # 完了した決済のみを抽出
        completed_payments = []
        for i, item in enumerate(items):
            # 辞書型かどうか確認
            if not isinstance(item, dict):
                logger.warning(f"不正なアイテム形式 (インデックス {i}): {type(item)}")
                continue
                
            # payment_statusフィールドを確認
            payment_status = item.get('payment_status')
            logger.info(f"アイテム {i}: payment_status = {payment_status}, キー = {list(item.keys())}")
            if payment_status == "COMPLETED":
                logger.info(f"完了した決済を追加: {item.get('customer') or item.get('顧客名', '不明')}")
                completed_payments.append(item)
        
        if not completed_payments:
            logger.warning(f"完了した決済が見つかりません: {filename}")
            return None
        
        # 複数のPDFを結合するためのPyPDF2のPdfMergerを作成
        merger = PdfMerger()
        
        # 各決済のPDFを生成して結合
        for payment in completed_payments:
            # 現在の日時を取得
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 決済情報を取得
            # 決済リンクからorder_idを抽出
            payment_link = payment.get('payment_link') or payment.get('決済リンク', '')
            if payment_link and 'token=' in payment_link:
                order_id = payment_link.split('token=')[1].split('&')[0]
            else:
                order_id = payment.get('order_id', f"ORDER-{uuid.uuid4().hex[:8].upper()}")
            
            # 顧客名と金額を取得（日本語と英語のフィールド名に対応）
            customer_name = payment.get('formatted_customer') or payment.get('customer') or payment.get('顧客名', '')
            amount = payment.get('formatted_amount') or payment.get('amount') or payment.get('金額', '')
            
            # HTMLテンプレートをレンダリング
            html_content = render_template('payment_result.html', 
                                          result="success", 
                                          status="COMPLETED", 
                                          order_id=order_id, 
                                          current_time=current_time,
                                          is_pdf_export=True,
                                          customer_name=customer_name,
                                          amount=amount)
            
            # PDFファイルを格納するメモリバッファを作成
            pdf_buffer = BytesIO()
            
            # HTMLからPDFを生成
            pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer)
            
            # PDF生成が成功したかチェック
            if pisa_status.err:
                logger.error(f"PDF生成中にエラーが発生しました: {pisa_status.err}")
                continue
            
            # バッファの先頭に移動
            pdf_buffer.seek(0)
            
            # PDFをマージャーに追加
            merger.append(pdf_buffer)
        
        # 出力ファイル名を決定
        if not output_filename:
            output_filename = f"payment-receipts-{date_str}.pdf"
        
        # 出力ディレクトリを作成
        output_dir = os.path.join(base_dir, 'exports')
        os.makedirs(output_dir, exist_ok=True)
        
        # 出力ファイルパスを作成
        output_path = os.path.join(output_dir, output_filename)
        
        # PDFを結合して保存
        with open(output_path, 'wb') as f:
            merger.write(f)
        merger.close()
        
        logger.info(f"バッチPDFエクスポートが完了しました: {output_path}, {len(completed_payments)}件")
        return output_path
        
    except Exception as e:
        logger.error(f"バッチPDFエクスポート中にエラーが発生しました: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def main():
    """
    コマンドラインからの実行用エントリーポイント
    """
    parser = argparse.ArgumentParser(description='履歴ファイルから複数の決済結果をまとめてPDFでエクスポートするツール')
    parser.add_argument('filename', help='履歴JSONファイル名')
    parser.add_argument('-o', '--output', help='出力ファイル名')
    args = parser.parse_args()
    
    output_path = export_batch_pdf(args.filename, args.output)
    if output_path:
        print(f"PDFファイルが生成されました: {output_path}")
    else:
        print("PDFファイルの生成に失敗しました")
        exit(1)

if __name__ == "__main__":
    main()
