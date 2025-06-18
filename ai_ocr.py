"""
AI搭載OCR機能 - 請求書からの情報抽出精度向上モジュール
"""
import os
import io
import re
import json
import requests
import logging
from typing import Dict, List, Optional, Tuple, Any
from extractors import ExtractionResult
from PIL import Image
import pdfplumber
import numpy as np

# ロガーの設定
logger = logging.getLogger(__name__)

# Google Cloud Vision APIを使用する場合（APIキーが必要）
try:
    from google.cloud import vision
    from google.oauth2 import service_account
    GOOGLE_VISION_AVAILABLE = True
except ImportError:
    GOOGLE_VISION_AVAILABLE = False
    logger.warning("Google Cloud Vision APIが利用できません。必要なライブラリをインストールしてください: pip install google-cloud-vision")

try:
    from azure.ai.formrecognizer import DocumentAnalysisClient
    from azure.core.credentials import AzureKeyCredential
    AZURE_FORM_RECOGNIZER_AVAILABLE = True
except ImportError:
    AZURE_FORM_RECOGNIZER_AVAILABLE = False
    logger.warning("Azure Form Recognizerが利用できません。必要なライブラリをインストールしてください: pip install azure-ai-formrecognizer")

# Tesseractを使用する場合（ローカル実行、APIキー不要）
try:
    import pytesseract
    # Tesseractが実際にインストールされているか確認
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
    logger.info(f"Tesseract OCRが利用可能です。バージョン: {pytesseract.get_tesseract_version()}")
except (ImportError, pytesseract.TesseractNotFoundError):
    TESSERACT_AVAILABLE = False
    logger.warning("Tesseract OCRが利用できません。従来の抽出方法を使用します。")


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
        self.api_key = self.config.get('ocr_api_key', '')
        self.endpoint = self.config.get('ocr_endpoint', '')
        
        # OCRエンジンの初期化
        if self.ocr_method == 'google_vision' and GOOGLE_VISION_AVAILABLE:
            try:
                if self.api_key:
                    # APIキーから認証情報を作成（JSONキーの内容をAPIキーとして使用）
                    try:
                        # APIキーがJSON形式の場合
                        import json
                        credentials_info = json.loads(self.api_key)
                        credentials = service_account.Credentials.from_service_account_info(credentials_info)
                        self.client = vision.ImageAnnotatorClient(credentials=credentials)
                        logger.info("Google Cloud Vision API: JSONキーから認証情報を作成しました")
                    except json.JSONDecodeError:
                        # APIキーがJSONでない場合、環境変数を使用
                        import os
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.api_key
                        self.client = vision.ImageAnnotatorClient()
                        logger.info("Google Cloud Vision API: 環境変数から認証情報を作成しました")
                else:
                    # APIキーがない場合、デフォルトの認証情報を使用
                    self.client = vision.ImageAnnotatorClient()
                    logger.info("Google Cloud Vision API: デフォルトの認証情報を使用します")
            except Exception as e:
                logger.error(f"Google Cloud Vision APIの初期化エラー: {str(e)}")
                self.ocr_method = 'tesseract'
                
        elif self.ocr_method == 'azure_form_recognizer' and AZURE_FORM_RECOGNIZER_AVAILABLE:
            try:
                if not self.api_key:
                    logger.warning("Azure Form RecognizerのAPIキーが設定されていません")
                    self.ocr_method = 'tesseract'
                    return
                    
                if not self.endpoint:
                    # エンドポイントが指定されていない場合、デフォルトのエンドポイントを使用
                    self.endpoint = "https://api.cognitive.microsofttranslator.com/"
                    logger.warning(f"Azure Form Recognizerのエンドポイントが指定されていないため、デフォルト値を使用します: {self.endpoint}")
                    
                self.client = DocumentAnalysisClient(
                    endpoint=self.endpoint, 
                    credential=AzureKeyCredential(self.api_key)
                )
                logger.info("Azure Form Recognizer: クライアントを初期化しました")
            except Exception as e:
                logger.error(f"Azure Form Recognizerの初期化エラー: {str(e)}")
                self.ocr_method = 'tesseract'
                
    def extract_from_pdf(self, pdf_path: str) -> ExtractionResult:
        """
        PDFから顧客名と金額を抽出
        Args:
            pdf_path: PDFファイルのパス
        Returns:
            (顧客名, 金額)のタプル
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
    
    def _extract_with_google_vision(self, pdf_path: str) -> ExtractionResult:
        """
        Google Cloud Vision APIを使用して抽出
        """
        try:
            from pdf2image import convert_from_path
            
            logger.info(f"Google Cloud Vision APIでPDFを処理: {pdf_path}")
            
            # PDFを画像に変換
            images = convert_from_path(pdf_path, dpi=300, first_page=1, last_page=1)
            
            if not images:
                logger.warning("PDFから画像への変換に失敗しました")
                return ExtractionResult(customer=None, amount=None)
            
            # 最初のページを処理
            img = images[0]
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            content = img_byte_arr.getvalue()
            
            # Vision APIでOCR実行
            image = vision.Image(content=content)
            
            try:
                response = self.client.document_text_detection(image=image)
                
                if hasattr(response, 'error') and response.error and response.error.message:
                    logger.error(f"Google Vision APIエラー: {response.error.message}")
                    return ExtractionResult(customer=None, amount=None)
                
                # 全テキスト
                if hasattr(response, 'full_text_annotation') and response.full_text_annotation:
                    full_text = response.full_text_annotation.text
                    logger.info(f"Google Cloud Vision APIでテキスト抽出成功: {len(full_text)}文字")
                    
                    # 請求書解析AI処理
                    amount = self._extract_amount_with_ai(full_text)
                    customer = self._extract_customer_with_ai(full_text)
                    
                    logger.info(f"抽出結果: 顧客名={customer}, 金額={amount}")
                    return ExtractionResult(customer=customer, amount=amount)
                else:
                    logger.warning("Google Cloud Vision APIからテキストを取得できませんでした")
                    return ExtractionResult(customer=None, amount=None)
                    
            except Exception as e:
                logger.error(f"Google Cloud Vision API呼び出しエラー: {str(e)}")
                return ExtractionResult(customer=None, amount=None)
                
        except Exception as e:
            logger.error(f"Google Cloud Vision API処理エラー: {str(e)}")
            return ExtractionResult(customer=None, amount=None)
    
    def _extract_with_azure_form_recognizer(self, pdf_path: str) -> ExtractionResult:
        """
        Azure Form Recognizerを使用して抽出
        """
        try:
            logger.info(f"Azure Form RecognizerでPDFを処理: {pdf_path}")
            
            if not self.api_key or not self.endpoint:
                logger.error("Azure Form RecognizerのAPIキーまたはエンドポイントが設定されていません")
                return ExtractionResult(customer=None, amount=None)
            
            # クライアントが初期化されていない場合は再初期化
            if not hasattr(self, 'client') or self.client is None:
                try:
                    self.client = DocumentAnalysisClient(
                        endpoint=self.endpoint, 
                        credential=AzureKeyCredential(self.api_key)
                    )
                    logger.info("Azure Form Recognizerクライアントを初期化しました")
                except Exception as e:
                    logger.error(f"Azure Form Recognizerクライアントの初期化エラー: {str(e)}")
                    return ExtractionResult(customer=None, amount=None)
            
            # PDFファイルを開いて解析
            try:
                with open(pdf_path, "rb") as f:
                    # 請求書分析を開始
                    poller = self.client.begin_analyze_document("prebuilt-invoice", f)
                    # 結果を取得（非同期処理）
                    invoices = poller.result()
                    
                    logger.info(f"Azure Form Recognizerの分析結果: {len(invoices.documents) if hasattr(invoices, 'documents') else 0}件の請求書を検出")
                    
                    if not hasattr(invoices, 'documents') or not invoices.documents:
                        logger.warning("Azure Form Recognizerは請求書を検出できませんでした")
                        return ExtractionResult(customer=None, amount=None)
                    
                    # 最初の請求書を処理
                    invoice = invoices.documents[0]
                    
                    # 請求額の抽出
                    amount = None
                    if invoice.fields.get("TotalAmount"):
                        amount_str = invoice.fields.get("TotalAmount").value
                        try:
                            # カンマや通貨記号を除去
                            amount_str = re.sub(r'[^\d.]', '', str(amount_str))
                            amount = int(float(amount_str))
                            logger.info(f"Azure Form Recognizerから金額を抽出: {amount}")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"金額の変換エラー: {str(e)}")
                    
                    # 顧客名の抽出
                    customer = None
                    if invoice.fields.get("CustomerName"):
                        customer = invoice.fields.get("CustomerName").value
                        # 「様」が含まれていない場合は追加
                        if customer and "様" not in customer:
                            customer += "様"
                        logger.info(f"Azure Form Recognizerから顧客名を抽出: {customer}")
                    
                    logger.info(f"Azure Form Recognizerの抽出結果: 顧客名={customer}, 金額={amount}")
                    return ExtractionResult(customer=customer, amount=amount)
                    
            except Exception as e:
                logger.error(f"Azure Form Recognizerの文書分析エラー: {str(e)}")
                return ExtractionResult(customer=None, amount=None)
                
        except Exception as e:
            logger.error(f"Azure Form Recognizer処理エラー: {str(e)}")
            return ExtractionResult(customer=None, amount=None)
    
    def _extract_with_tesseract(self, pdf_path: str) -> ExtractionResult:
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
        
        return ExtractionResult(customer=customer, amount=amount)
    
    def _extract_with_pdfplumber(self, pdf_path: str) -> ExtractionResult:
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
                        # context変数を必ず定義
                        context = priority_text[max(0, match.start() - 30):min(len(priority_text), match.end() + 30)]
                        weight = 5  # 最初の500文字は重要度高
                        
                        # 「様」が含まれている場合は重要度を大幅に上げる
                        if "様" in name or match.group(0).endswith("様"):
                            weight += 5
                        
                        found_names.append((name, weight, context))
                except IndexError:
                    # エラーが発生した場合はスキップ
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
def process_pdf_with_ai_ocr(pdf_path: str, config: Dict = None) -> ExtractionResult:
    """
    AI OCRを使用してPDFを処理する便利関数
    様々なPDF形式に対応し、複数の抽出方法を試行
    Args:
        pdf_path: PDFファイルのパス
        config: 設定情報
    Returns:
        (顧客名, 金額)のタプル
    """
    logger.info(f"PDF処理開始: {pdf_path}")
    
    # 抽出結果を格納する変数
    amount = None
    customer = None
    extracted_text = ""
    all_extracted_texts = []  # 複数の方法で抽出したテキストを保存
    
    # 方法１: AI OCRを使用
    try:
        logger.info("AI OCRでの抽出を試行中...")
        ai_ocr = AIOCR(config)
        customer, amount = ai_ocr.extract_from_pdf(pdf_path)
        if amount is not None and customer is not None:
            logger.info(f"AI OCRで成功: 顧客名={customer}, 金額={amount}")
            return ExtractionResult(customer=customer, amount=amount)
    except Exception as e:
        logger.error(f"AI OCR処理エラー: {str(e)}")
    
    # 方法２: pdfplumberを使用
    pdfplumber_text = ""
    try:
        logger.info("pdfplumberでの抽出を試行中...")
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                pdfplumber_text += page_text
        
        if pdfplumber_text.strip():
            logger.info(f"pdfplumberでテキスト抽出成功: {len(pdfplumber_text)}文字")
            extracted_text = pdfplumber_text
            all_extracted_texts.append(pdfplumber_text)
    except Exception as e:
        logger.error(f"pdfplumber処理エラー: {str(e)}")
    
    # 方法３: PyPDF2を使用
    pypdf2_text = ""
    try:
        logger.info("PyPDF2での抽出を試行中...")
        import PyPDF2
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                page_text = page.extract_text() or ""
                pypdf2_text += page_text
        
        if pypdf2_text.strip():
            logger.info(f"PyPDF2でテキスト抽出成功: {len(pypdf2_text)}文字")
            if not extracted_text.strip():
                extracted_text = pypdf2_text
            all_extracted_texts.append(pypdf2_text)
    except Exception as e:
        logger.error(f"PyPDF2処理エラー: {str(e)}")
    
    # 方法４: pdf2image + pytesseractを使用
    tesseract_text = ""
    try:
        logger.info("pdf2image + pytesseractでの抽出を試行中...")
        if TESSERACT_AVAILABLE:
            from pdf2image import convert_from_path
            images = convert_from_path(pdf_path)
            for i, image in enumerate(images):
                page_text = pytesseract.image_to_string(image, lang='jpn')
                tesseract_text += page_text or ""
            
            if tesseract_text.strip():
                logger.info(f"pdf2image + pytesseractでテキスト抽出成功: {len(tesseract_text)}文字")
                if not extracted_text.strip():
                    extracted_text = tesseract_text
                all_extracted_texts.append(tesseract_text)
    except Exception as e:
        logger.error(f"pdf2image + pytesseract処理エラー: {str(e)}")
        
    # 方法５: pdfminer.sixを使用（文字化け対策）
    pdfminer_text = ""
    try:
        logger.info("pdfminer.sixでの抽出を試行中...")
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        pdfminer_text = pdfminer_extract_text(pdf_path)
        
        if pdfminer_text.strip():
            logger.info(f"pdfminer.sixでテキスト抽出成功: {len(pdfminer_text)}文字")
            if not extracted_text.strip():
                extracted_text = pdfminer_text
            all_extracted_texts.append(pdfminer_text)
    except Exception as e:
        logger.error(f"pdfminer.six処理エラー: {str(e)}")
    
    # 抽出したテキストから金額と顧客名を抽出
    if extracted_text.strip():
        try:
            from extractors import extract_amount_and_customer, extract_amount_only, ExtractionResult
            import customer_extractor  # 新しい顧客名抽出モジュールをインポート
            
            # 最初に主要なテキストから抽出を試みる
            extraction_result = extract_amount_and_customer(extracted_text)
            customer = extraction_result.customer
            amount = extraction_result.amount
            
            # すべての抽出テキストを試す（金額または顧客名が見つからない場合）
            if amount is None or customer is None:
                logger.info("複数の抽出テキストから金額と顧客名を検索中...")
                for i, text in enumerate(all_extracted_texts):
                    if text != extracted_text:  # 既に処理したテキストはスキップ
                        logger.info(f"抽出テキスト {i+1} を処理中...")
                        if amount is None:
                            amount = extract_amount_only(text)
                            if amount is not None:
                                logger.info(f"追加テキストから金額を抽出: {amount}円")
                        
                        if customer is None:
                            # ファイル名も渡して顧客名を抽出
                            filename = os.path.basename(pdf_path) if pdf_path else None
                            customer = customer_extractor.extract_customer(text, filename)
                            if customer is not None:
                                logger.info(f"追加テキストから顧客名を抽出: {customer}")
                        
                        # 両方見つかったら終了
                        if amount is not None and customer is not None:
                            break
            
            logger.info(f"最終抽出結果: 顧客名={customer}, 金額={amount}")
            return ExtractionResult(customer=customer, amount=amount)
        except Exception as e:
            logger.error(f"金額と顧客名の抽出エラー: {str(e)}")
    
    logger.warning("PDFからテキストを抽出できませんでした")
    return ExtractionResult(customer=None, amount=None)
