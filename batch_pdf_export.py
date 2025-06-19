#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch PDF export functionality for PDF PayPal System
"""

import os
import json
import uuid
import logging
from datetime import datetime
from io import BytesIO
from xhtml2pdf import pisa
from PyPDF2 import PdfMerger
from flask import make_response, jsonify, render_template, abort

# Configure logging
logger = logging.getLogger(__name__)

def export_batch_pdf(app, filename):
    """
    履歴ファイルから複数の決済結果をまとめてPDFでエクスポートする
    
    Args:
        app: Flaskアプリケーションインスタンス
        filename: 履歴ファイル名
        
    Returns:
        PDFファイルのレスポンス
    """
    try:
        # セキュリティ対策としてファイル名を検証
        if '..' in filename or filename.startswith('/'):
            logger.warning(f"不正なファイルパス: {filename}")
            return jsonify({"error": "不正なファイルパス"}), 404
            
        # ベースディレクトリを取得
        base_dir = os.path.dirname(os.path.abspath(__file__))
        results_folder = os.path.join(base_dir, 'results')
        file_path = os.path.join(results_folder, filename)
        
        logger.info(f"ファイルパス: {file_path}")
        logger.info(f"ファイルが存在するか: {os.path.exists(file_path)}")
        
        if not os.path.exists(file_path):
            logger.warning(f"履歴ファイルが存在しません: {file_path}")
            return jsonify({"error": "履歴ファイルが存在しません"}), 404
        
        # ファイルの内容を読み込み
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
            logger.info(f"ファイル内容 (最初の200文字): {file_content[:200]}...")
            data = json.loads(file_content)
        
        # 日付を取得
        date = filename.replace('payment_links_', '').replace('.json', '')
        
        # データ構造を確認して適切に処理
        logger.info(f"データ型: {type(data)}, データ内容: {str(data)[:200]}...")
        
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
            return jsonify({"error": "完了した決済が見つかりません"}), 404
        
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
        
        # 結合したPDFを格納するメモリバッファを作成
        output_buffer = BytesIO()
        
        # PDFを結合
        merger.write(output_buffer)
        merger.close()
        
        # バッファの先頭に移動
        output_buffer.seek(0)
        
        # レスポンスを作成
        response = make_response(output_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=payment-receipts-{date}.pdf'
        
        logger.info(f"バッチPDFエクスポートが完了しました: {filename}, {len(completed_payments)}件")
        return response
        
    except Exception as e:
        logger.error(f"バッチPDFエクスポート中にエラーが発生しました: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Flask アプリケーションにルートを追加するヘルパー関数
def register_batch_export_route(app):
    @app.route('/batch_export/<filename>')
    def batch_export(filename):
        return export_batch_pdf(app, filename)
