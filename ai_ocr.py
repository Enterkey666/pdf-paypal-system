"""
AI搭載OCR機能 - 請求書からの情報抽出精度向上モジュール
"""
import os
import io
import re
import json
import requests
from typing import Dict, List, Optional, Tuple, Any
from PIL import Image
import pdfplumber
import numpy as np

# Google Cloud Vision APIを使用する場合（APIキーが必要）
try:
    from google.cloud import vision
    from google.cloud.vision_v1 import types
    GOOGLE_VISION_AVAILABLE = True
except ImportError:
    GOOGLE_VISION_AVAILABLE = False

# Azure Form Recognizerを使用する場合（APIキーが必要）
try:
    from azure.ai.formrecognizer import DocumentAnalysisClient
    from azure.core.credentials import AzureKeyCredential
    AZURE_FORM_RECOGNIZER_AVAILABLE = True
except ImportError:
    AZURE_FORM_RECOGNIZER_AVAILABLE = False

# Tesseractを使用する場合（ローカル実行、APIキー不要）
try:
    import pytesseract
    # Tesseractが実際にインストールされているか確認
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
    print("Tesseract OCRが利用可能です。バージョン:", pytesseract.get_tesseract_version())
except (ImportError, pytesseract.TesseractNotFoundError):
    TESSERACT_AVAILABLE = False
    print("Tesseract OCRが利用できません。従来の抽出方法を使用します。")


class AIOCR:
    """AI搭載OCR機能クラス"""
    
    def __init__(self, config: Dict = None):
        """
        初期化
        Args:
            config: 設定情報
        """
        self.config = config or {}
        self.ocr_method = self.config.get('ocr_method', 'tesseract')
        self.api_key = self.config.get('api_key', '')
        self.endpoint = self.config.get('endpoint', '')
        
        # OCRエンジンの初期化
        if self.ocr_method == 'google_vision' and GOOGLE_VISION_AVAILABLE:
            self.client = vision.ImageAnnotatorClient()
        elif self.ocr_method == 'azure_form_recognizer' and AZURE_FORM_RECOGNIZER_AVAILABLE:
            self.client = DocumentAnalysisClient(
                endpoint=self.endpoint, 
                credential=AzureKeyCredential(self.api_key)
            )
    
    def extract_from_pdf(self, pdf_path: str) -> Tuple[Optional[int], Optional[str]]:
        """
        PDFから金額と顧客名を抽出
        Args:
            pdf_path: PDFファイルのパス
        Returns:
            (金額, 顧客名)のタプル
        """
        # OCR方式に応じて処理
        if self.ocr_method == 'google_vision' and GOOGLE_VISION_AVAILABLE:
            return self._extract_with_google_vision(pdf_path)
        elif self.ocr_method == 'azure_form_recognizer' and AZURE_FORM_RECOGNIZER_AVAILABLE:
            return self._extract_with_azure_form_recognizer(pdf_path)
        elif self.ocr_method == 'tesseract' and TESSERACT_AVAILABLE:
            return self._extract_with_tesseract(pdf_path)
        else:
            # デフォルトはpdfplumberを使用した既存の方式
            return self._extract_with_pdfplumber(pdf_path)
    
    def _extract_with_google_vision(self, pdf_path: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Google Cloud Vision APIを使用して抽出
        """
        from pdf2image import convert_from_path
        
        # PDFを画像に変換
        images = convert_from_path(pdf_path, dpi=300, first_page=1, last_page=1)
        
        if not images:
            return None, None
        
        # 最初のページを処理
        img = images[0]
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        content = img_byte_arr.getvalue()
        
        # Vision APIでOCR実行
        image = vision.Image(content=content)
        response = self.client.document_text_detection(image=image)
        
        if response.error.message:
            print(f"Google Vision APIエラー: {response.error.message}")
            return None, None
        
        # 全テキスト
        full_text = response.full_text_annotation.text
        
        # 請求書解析AI処理
        amount = self._extract_amount_with_ai(full_text)
        customer = self._extract_customer_with_ai(full_text)
        
        return amount, customer
    
    def _extract_with_azure_form_recognizer(self, pdf_path: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Azure Form Recognizerを使用して抽出
        """
        with open(pdf_path, "rb") as f:
            poller = self.client.begin_analyze_document("prebuilt-invoice", f)
            invoices = poller.result()
        
        if not invoices.documents:
            return None, None
        
        invoice = invoices.documents[0]
        
        # 請求額の抽出
        amount = None
        if invoice.fields.get("TotalAmount"):
            amount_str = invoice.fields.get("TotalAmount").value
            try:
                # カンマや通貨記号を除去
                amount_str = re.sub(r'[^\d.]', '', str(amount_str))
                amount = int(float(amount_str))
            except (ValueError, TypeError):
                pass
        
        # 顧客名の抽出
        customer = None
        if invoice.fields.get("CustomerName"):
            customer = invoice.fields.get("CustomerName").value
            # 「様」が含まれていない場合は追加
            if customer and "様" not in customer:
                customer += "様"
        
        return amount, customer
    
    def _extract_with_tesseract(self, pdf_path: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Tesseract OCRを使用して抽出
        """
        from pdf2image import convert_from_path
        
        # PDFを画像に変換
        images = convert_from_path(pdf_path, dpi=300, first_page=1, last_page=1)
        
        if not images:
            return None, None
        
        # 最初のページを処理
        img = images[0]
        
        # Tesseractで日本語OCR実行
        text = pytesseract.image_to_string(img, lang='jpn')
        
        # 請求書解析AI処理
        amount = self._extract_amount_with_ai(text)
        customer = self._extract_customer_with_ai(text)
        
        return amount, customer
    
    def _extract_with_pdfplumber(self, pdf_path: str) -> Tuple[Optional[int], Optional[str]]:
        """
        pdfplumberを使用して抽出（既存の方式）
        """
        from extractors import extract_amount_and_customer
        
        # PDFからテキスト抽出
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        # 既存の抽出関数を使用
        return extract_amount_and_customer(text)
    
    def _extract_amount_with_ai(self, text: str) -> Optional[int]:
        """
        AIを使用して金額を抽出
        """
        # 「ご請求額」パターンを優先的に検索
        amount_patterns = [
            r'ご\s*請\s*求\s*額[^\n]*?([0-9,.]+)(?:\s*円|\s*$)',
            r'ご\s*請\s*求\s*額[^\n]*?[¥\u00a5]\s*([0-9,.]+)',
            r'請\s*求\s*額[^\n]*?([0-9,.]+)(?:\s*円|\s*$)',
            r'合\s*計\s*金\s*額[^\n]*?([0-9,.]+)(?:\s*円|\s*$)',
            r'\b合\s*計\b[^\n]*?([0-9,.]+)(?:\s*円|\s*$)',
            r'([0-9,.]+)\s*円'
        ]
        
        # 配列にパターンマッチ結果を保存（優先度、金額、コンテキスト）
        found_amounts = []
        
        # テキスト全体を探索
        for priority, pattern in enumerate(amount_patterns):
            matches = re.finditer(pattern, text, re.MULTILINE)
            for match in matches:
                try:
                    # カンマや空白を除去して整数変換
                    amount_str = match.group(1).replace(',', '').replace(' ', '').replace('¥', '')
                    amt = int(amount_str)
                    if 100 <= amt < 10000000:  # 妥当な金額範囲のみ取得
                        context = text[max(0, match.start() - 40):min(len(text), match.end() + 40)]
                        # 優先度を計算
                        weight = len(amount_patterns) - priority
                        
                        # 「ご請求額」が含まれる場合は優先度を大幅に上げる
                        if 'ご請求額' in context:
                            weight += 10
                        elif '請求額' in context:
                            weight += 5
                        elif '合計' in context:
                            weight += 3
                            
                        found_amounts.append((weight, amt, context))
                except ValueError:
                    continue
        
        if found_amounts:
            # 優先度でソート（降順）
            found_amounts.sort(key=lambda x: (-x[0], -x[1]))
            return found_amounts[0][1]
        
        return None
    
    def _extract_customer_with_ai(self, text: str) -> Optional[str]:
        """
        AIを使用して顧客名を抽出
        """
        # 「様」を含む行を特別に記録
        sama_lines = []
        for i, line in enumerate(text.split('\n')[:30]):
            line = line.strip()
            if '様' in line:
                sama_lines.append((i, line))
        
        # 「様」を含む行から顧客名を優先的に抽出
        if sama_lines:
            for i, line in sama_lines:
                # 「様」の前にある名前を抽出
                sama_pattern = r'([^\s]{2,20}[^\d\s])\s*様'
                match = re.search(sama_pattern, line)
                if match:
                    customer = match.group(1).strip()
                    return f"{customer}様"
        
        # 顧客名抽出のより詳細なパターン
        name_patterns = [
            r'([^\s]{2,20}[^\d\s])\s*様',
            r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+\s*[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+)\s*(?:\(\s*[^\)]+\))?\s*様',
            r'(?:請求先|客様名|顧客名|氏名|名称|宛名|\b宛\b)[^\n:]*[:|：|\s]\s*([^\n\d]{2,30}?)(?:\s|$|様)'
        ]
        
        # 全文検索（最初の500文字を優先）
        found_names = []
        
        for pattern in name_patterns:
            # 最初の500文字を優先的に検索
            priority_text = text[:500]
            matches = re.finditer(pattern, priority_text, re.MULTILINE)
            for match in matches:
                try:
                    name = match.group(1).strip().replace('\n', '').replace('\r', '')
                    if len(name) > 1 and any(c.isalpha() for c in name):
                        context = priority_text[max(0, match.start() - 30):min(len(priority_text), match.end() + 30)]
                        weight = 5  # 最初の500文字は重要度高
                        
                        # 「様」が含まれている場合は重要度を大幅に上げる
                        if "様" in name or match.group(0).endswith("様"):
                            weight += 5
                        
                        found_names.append((name, weight, context))
                except IndexError:
                    continue
        
        if found_names:
            # 重要度に基づいて顧客名をソート
            found_names.sort(key=lambda x: -x[1])
            customer = found_names[0][0]
            
            # 「様」が含まれていない場合は追加
            if "様" not in customer:
                customer += "様"
                
            return customer
        
        return None


# 使用例
def process_pdf_with_ai_ocr(pdf_path: str, config: Dict = None) -> Tuple[Optional[int], Optional[str]]:
    """
    AI OCRを使用してPDFを処理する便利関数
    様々なPDF形式に対応し、複数の抽出方法を試行
    Args:
        pdf_path: PDFファイルのパス
        config: 設定情報
    Returns:
        (金額, 顧客名)のタプル
    """
    print(f"PDF処理開始: {pdf_path}")
    
    # 抽出結果を格納する変数
    amount = None
    customer = None
    extracted_text = ""
    all_extracted_texts = []  # 複数の方法で抽出したテキストを保存
    
    # 方法１: AI OCRを使用
    try:
        print("AI OCRでの抽出を試行中...")
        ai_ocr = AIOCR(config)
        amount, customer = ai_ocr.extract_from_pdf(pdf_path)
        if amount is not None and customer is not None:
            print(f"AI OCRで成功: 金額={amount}, 顧客名={customer}")
            return amount, customer
    except Exception as e:
        print(f"AI OCR処理エラー: {str(e)}")
    
    # 方法２: pdfplumberを使用
    pdfplumber_text = ""
    try:
        print("pdfplumberでの抽出を試行中...")
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                pdfplumber_text += page_text
        
        if pdfplumber_text.strip():
            print(f"pdfplumberでテキスト抽出成功: {len(pdfplumber_text)}文字")
            extracted_text = pdfplumber_text
            all_extracted_texts.append(pdfplumber_text)
    except Exception as e:
        print(f"pdfplumber処理エラー: {str(e)}")
    
    # 方法３: PyPDF2を使用
    pypdf2_text = ""
    try:
        print("PyPDF2での抽出を試行中...")
        import PyPDF2
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                page_text = page.extract_text() or ""
                pypdf2_text += page_text
        
        if pypdf2_text.strip():
            print(f"PyPDF2でテキスト抽出成功: {len(pypdf2_text)}文字")
            if not extracted_text.strip():
                extracted_text = pypdf2_text
            all_extracted_texts.append(pypdf2_text)
    except Exception as e:
        print(f"PyPDF2処理エラー: {str(e)}")
    
    # 方法４: pdf2image + pytesseractを使用
    tesseract_text = ""
    try:
        print("pdf2image + pytesseractでの抽出を試行中...")
        if TESSERACT_AVAILABLE:
            from pdf2image import convert_from_path
            images = convert_from_path(pdf_path)
            for i, image in enumerate(images):
                page_text = pytesseract.image_to_string(image, lang='jpn')
                tesseract_text += page_text or ""
            
            if tesseract_text.strip():
                print(f"pdf2image + pytesseractでテキスト抽出成功: {len(tesseract_text)}文字")
                if not extracted_text.strip():
                    extracted_text = tesseract_text
                all_extracted_texts.append(tesseract_text)
    except Exception as e:
        print(f"pdf2image + pytesseract処理エラー: {str(e)}")
        
    # 方法５: pdfminer.sixを使用（文字化け対策）
    pdfminer_text = ""
    try:
        print("pdfminer.sixでの抽出を試行中...")
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        pdfminer_text = pdfminer_extract_text(pdf_path)
        
        if pdfminer_text.strip():
            print(f"pdfminer.sixでテキスト抽出成功: {len(pdfminer_text)}文字")
            if not extracted_text.strip():
                extracted_text = pdfminer_text
            all_extracted_texts.append(pdfminer_text)
    except Exception as e:
        print(f"pdfminer.six処理エラー: {str(e)}")
    
    # 抽出したテキストから金額と顧客名を抽出
    if extracted_text.strip():
        try:
            from extractors import extract_amount_and_customer, extract_amount_only, extract_customer
            
            # 最初に主要なテキストから抽出を試みる
            amount, customer = extract_amount_and_customer(extracted_text)
            
            # すべての抽出テキストを試す（金額または顧客名が見つからない場合）
            if amount is None or customer is None:
                print("複数の抽出テキストから金額と顧客名を検索中...")
                for i, text in enumerate(all_extracted_texts):
                    if text != extracted_text:  # 既に処理したテキストはスキップ
                        print(f"抽出テキスト {i+1} を処理中...")
                        if amount is None:
                            amount = extract_amount_only(text)
                            if amount is not None:
                                print(f"追加テキストから金額を抽出: {amount}円")
                        
                        if customer is None:
                            customer = extract_customer(text)
                            if customer is not None:
                                print(f"追加テキストから顧客名を抽出: {customer}")
                        
                        # 両方見つかったら終了
                        if amount is not None and customer is not None:
                            break
            
            print(f"最終抽出結果: 金額={amount}, 顧客名={customer}")
            return amount, customer
        except Exception as e:
            print(f"金額と顧客名の抽出エラー: {str(e)}")
    
    print("PDFからテキストを抽出できませんでした")
    return None, None
