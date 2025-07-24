"""
PDF処理と抽出機能を提供するモジュール
PDFからのテキスト抽出、顧客名・金額の識別、決済リンク生成などの機能を提供
"""
import os
import logging
import PyPDF2
import pdfplumber
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any

# ExtractionResultクラスをインポート
from extractors import ExtractionResult

# ロギング設定
logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path):
    """
    PDFからテキストを抽出する関数
    複数の抽出方法を試し、最も良い結果を返す
    
    Args:
        pdf_path: PDFファイルのパス
        
    Returns:
        str: 抽出されたテキスト
    """
    try:
        # まずpdfplumberでテキスト抽出を試みる
        extracted_text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                extracted_text += page_text + "\n"
        
        # 抽出テキストがある場合はそのまま返す
        if extracted_text.strip():
            return extracted_text
        
        # PyPDF2でも試してみる
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            pdf_text = ""
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                pdf_text += page.extract_text() + "\n"
            
            if pdf_text.strip():
                return pdf_text
        
        # どちらも失敗した場合はAI OCR機能を試す
        try:
            from ai_ocr import process_pdf_with_ai_ocr
            result = process_pdf_with_ai_ocr(pdf_path)
            if result and (result.customer or result.amount):
                # 抽出されたデータがある場合は文字列として返す
                extracted_info = f"顧客名: {result.customer or '不明'}\n金額: {result.amount or '不明'}"
                return extracted_info
        except ImportError:
            logger.warning("ai_ocrモジュールをインポートできませんでした。OCR機能は使用できません。")
        
        return "テキスト抽出に失敗しました"
    
    except Exception as e:
        logger.error(f"PDFテキスト抽出エラー: {str(e)}")
        return f"エラー: {str(e)}"

def process_single_pdf(filepath, filename, request):
    """
    単一のPDFファイルを処理する
    テキストを抽出し、顧客情報と金額を識別し、PayPal決済リンクを生成する
    
    Args:
        filepath: PDFファイルのパス
        filename: ファイル名
        request: リクエストオブジェクト
        
    Returns:
        dict: 処理結果の辞書
    """
    try:
        # PDFからテキストを抽出
        extracted_text = extract_text_from_pdf(filepath)
        
        if not extracted_text or extracted_text == "テキスト抽出に失敗しました":
            logger.error(f"PDFからのテキスト抽出に失敗: {filename}")
            return {
                'filename': filename,
                'success': False,
                'error': 'テキスト抽出に失敗しました'
            }
        
        # 抽出テキストから顧客名と金額を抽出
        try:
            from extractors import extract_amount_and_customer
            extraction_result = extract_amount_and_customer(extracted_text)
            customer_name = extraction_result.customer
            amount = extraction_result.amount
        except Exception as e:
            logger.error(f"顧客名と金額の抽出エラー: {str(e)}")
            customer_name = None
            amount = None
        
        # 決済リンクを生成
        if customer_name and amount:
            try:
                # デフォルトの決済プロバイダーを使用して決済リンクを生成（統一ロジックで自動切り替え含む）
                from payment_utils import create_payment_link, get_default_payment_provider
                
                provider = get_default_payment_provider()
                logger.info(f"決済リンク生成: プロバイダー={provider}, 顧客名={customer_name}, 金額={amount}")
                
                # 決済リンクを生成（payment_utils.pyの統一ロジックが自動で利用可能性チェックと代替プロバイダー切り替えを行う）
                result = create_payment_link(
                    provider=provider,
                    amount=float(amount),
                    customer_name=customer_name,
                    description=filename
                )
                payment_link = result.get('payment_link')
                
                # 使用したプロバイダーをログに記録
                logger.info(f"決済リンク生成結果: プロバイダー={result.get('provider', provider)}, 成功={result.get('success', False)}")
                if not result.get('success', False):
                    logger.warning(f"決済リンク生成失敗: {result.get('message', '不明なエラー')}")
                
                
                # 処理結果を返す
                return {
                    'filename': filename,
                    'customer_name': customer_name,
                    'amount': amount,
                    'payment_link': payment_link,
                    'success': True
                }
            except Exception as e:
                logger.error(f"決済リンク生成エラー: {str(e)}")
                return {
                    'filename': filename,
                    'customer_name': customer_name,
                    'amount': amount,
                    'error': f"決済リンク生成エラー: {str(e)}",
                    'success': False
                }
        else:
            logger.warning(f"顧客名または金額が抽出できませんでした: {filename}")
            return {
                'filename': filename,
                'customer_name': customer_name,
                'amount': amount,
                'error': '顧客名または金額が抽出できませんでした',
                'success': False
            }
    
    except Exception as e:
        logger.error(f"PDF処理エラー: {str(e)}")
        return {
            'filename': filename,
            'error': str(e),
            'success': False
        }
