#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
拡張OCRモジュール
複数のOCR手法を組み合わせて高精度なテキスト抽出を行う
"""

import os
import io
import cv2
import logging
import tempfile
import numpy as np
from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import traceback

# ロギング設定
logger = logging.getLogger(__name__)

# Tesseractコマンドパスの設定（必要に応じて変更）
# pytesseract.pytesseract.tesseract_cmd = r'/usr/local/bin/tesseract'

# Google Cloud Vision APIのインポート（使用する場合）
try:
    from google.cloud import vision
    GOOGLE_VISION_AVAILABLE = True
except ImportError:
    GOOGLE_VISION_AVAILABLE = False
    logger.warning("Google Cloud Vision APIが利用できません。必要に応じてインストールしてください。")

# Azure Computer Visionのインポート（使用する場合）
try:
    from azure.cognitiveservices.vision.computervision import ComputerVisionClient
    from msrest.authentication import CognitiveServicesCredentials
    AZURE_VISION_AVAILABLE = True
except ImportError:
    AZURE_VISION_AVAILABLE = False
    logger.warning("Azure Computer Visionが利用できません。必要に応じてインストールしてください。")

# Amazon Textractのインポート（使用する場合）
try:
    import boto3
    AWS_TEXTRACT_AVAILABLE = True
except ImportError:
    AWS_TEXTRACT_AVAILABLE = False
    logger.warning("AWS Textractが利用できません。必要に応じてインストールしてください。")


def check_tesseract_available():
    """Tesseract OCRが利用可能かチェックする"""
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text_with_tesseract(image_path, lang='jpn+eng'):
    """
    Tesseract OCRを使用して画像からテキストを抽出する
    
    Args:
        image_path: 画像ファイルのパス
        lang: 言語設定（デフォルトは日本語と英語）
    
    Returns:
        抽出されたテキスト
    """
    try:
        return pytesseract.image_to_string(Image.open(image_path), lang=lang)
    except Exception as e:
        logger.error(f"Tesseract OCRエラー: {str(e)}")
        return ""


def extract_text_with_layout_analysis(image_path, lang='jpn+eng'):
    """
    レイアウト分析を行い、テキストを抽出する
    
    Args:
        image_path: 画像ファイルのパス
        lang: 言語設定
    
    Returns:
        抽出されたテキスト（全体と領域ごと）
    """
    try:
        # 画像を読み込む
        image = cv2.imread(image_path)
        if image is None:
            logger.error(f"画像を読み込めませんでした: {image_path}")
            return {"full_text": "", "regions": {}}
        
        # グレースケールに変換
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 画像サイズを取得
        height, width = gray.shape
        
        # 領域を定義（上部、中央、下部、左側、右側）
        regions = {
            "top": gray[0:int(height*0.3), 0:width],
            "middle": gray[int(height*0.3):int(height*0.7), 0:width],
            "bottom": gray[int(height*0.7):height, 0:width],
            "left": gray[0:height, 0:int(width*0.5)],
            "right": gray[0:height, int(width*0.5):width],
            "center": gray[int(height*0.3):int(height*0.7), int(width*0.3):int(width*0.7)]
        }
        
        # 各領域からテキストを抽出
        region_texts = {}
        for region_name, region_img in regions.items():
            # 一時ファイルに保存
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name
                cv2.imwrite(temp_path, region_img)
                
                # OCRでテキスト抽出
                region_text = pytesseract.image_to_string(Image.open(temp_path), lang=lang)
                region_texts[region_name] = region_text
                
                # 一時ファイルを削除
                os.unlink(temp_path)
        
        # 全体のテキストも抽出
        full_text = pytesseract.image_to_string(Image.open(image_path), lang=lang)
        
        return {
            "full_text": full_text,
            "regions": region_texts
        }
    except Exception as e:
        logger.error(f"レイアウト分析エラー: {str(e)}")
        traceback.print_exc()
        return {"full_text": "", "regions": {}}


def extract_with_google_vision(image_path):
    """
    Google Cloud Vision APIを使用して画像からテキストを抽出する
    
    Args:
        image_path: 画像ファイルのパス
    
    Returns:
        抽出されたテキスト
    """
    if not GOOGLE_VISION_AVAILABLE:
        logger.warning("Google Cloud Vision APIが利用できません")
        return ""
    
    try:
        # クライアントを初期化
        client = vision.ImageAnnotatorClient()
        
        # 画像を読み込む
        with open(image_path, "rb") as image_file:
            content = image_file.read()
        
        image = vision.Image(content=content)
        
        # テキスト検出を実行
        response = client.text_detection(image=image)
        texts = response.text_annotations
        
        if texts:
            return texts[0].description
        return ""
    except Exception as e:
        logger.error(f"Google Cloud Vision APIエラー: {str(e)}")
        return ""


def extract_with_azure_vision(image_path, subscription_key, endpoint):
    """
    Azure Computer Visionを使用して画像からテキストを抽出する
    
    Args:
        image_path: 画像ファイルのパス
        subscription_key: Azure Computer VisionのAPIキー
        endpoint: Azure Computer VisionのエンドポイントURL
    
    Returns:
        抽出されたテキスト
    """
    if not AZURE_VISION_AVAILABLE:
        logger.warning("Azure Computer Visionが利用できません")
        return ""
    
    try:
        # クライアントを初期化
        client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(subscription_key))
        
        # 画像を読み込む
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
        
        # テキスト検出を実行
        results = client.recognize_printed_text_in_stream(image_data)
        
        text = ""
        for region in results.regions:
            for line in region.lines:
                for word in line.words:
                    text += word.text + " "
                text += "\n"
        
        return text
    except Exception as e:
        logger.error(f"Azure Computer Visionエラー: {str(e)}")
        return ""


def extract_with_aws_textract(image_path):
    """
    AWS Textractを使用して画像からテキストを抽出する
    
    Args:
        image_path: 画像ファイルのパス
    
    Returns:
        抽出されたテキスト
    """
    if not AWS_TEXTRACT_AVAILABLE:
        logger.warning("AWS Textractが利用できません")
        return ""
    
    try:
        # クライアントを初期化
        client = boto3.client('textract')
        
        # 画像を読み込む
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
        
        # テキスト検出を実行
        response = client.detect_document_text(Document={'Bytes': image_bytes})
        
        text = ""
        for item in response["Blocks"]:
            if item["BlockType"] == "LINE":
                text += item["Text"] + "\n"
        
        return text
    except Exception as e:
        logger.error(f"AWS Textractエラー: {str(e)}")
        return ""


def pdf_to_images(pdf_path, dpi=300):
    """
    PDFを画像に変換する
    
    Args:
        pdf_path: PDFファイルのパス
        dpi: 解像度（デフォルトは300）
    
    Returns:
        画像のパスのリスト
    """
    try:
        # PDFを画像に変換
        images = convert_from_path(pdf_path, dpi=dpi)
        image_paths = []
        
        # 一時ディレクトリを作成
        temp_dir = tempfile.mkdtemp()
        
        # 各ページを画像として保存
        for i, image in enumerate(images):
            image_path = os.path.join(temp_dir, f"page_{i+1}.png")
            image.save(image_path, "PNG")
            image_paths.append(image_path)
        
        return image_paths, temp_dir
    except Exception as e:
        logger.error(f"PDF画像変換エラー: {str(e)}")
        return [], None


def preprocess_image(image_path):
    """
    OCRの精度向上のために画像を前処理する
    
    Args:
        image_path: 画像ファイルのパス
    
    Returns:
        前処理された画像のパス
    """
    try:
        # 画像を読み込む
        image = cv2.imread(image_path)
        
        # グレースケールに変換
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # ノイズ除去
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # 適応的二値化
        binary = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            temp_path = temp_file.name
            cv2.imwrite(temp_path, binary)
        
        return temp_path
    except Exception as e:
        logger.error(f"画像前処理エラー: {str(e)}")
        return image_path


def extract_text_hybrid(file_path, config=None):
    """
    複数の抽出方法を試し、最も信頼性の高い結果を返す
    
    Args:
        file_path: ファイルのパス（PDFまたは画像）
        config: 設定情報
    
    Returns:
        抽出結果の辞書
    """
    if config is None:
        config = {}
    
    results = {}
    file_ext = os.path.splitext(file_path)[1].lower()
    
    # PDFの場合は画像に変換
    if file_ext == '.pdf':
        image_paths, temp_dir = pdf_to_images(file_path)
    else:
        # 画像ファイルの場合はそのまま使用
        image_paths = [file_path]
        temp_dir = None
    
    all_texts = []
    all_region_texts = {}
    
    try:
        for image_path in image_paths:
            # 画像の前処理
            processed_image = preprocess_image(image_path)
            
            # 方法1: 通常のTesseract OCR
            if check_tesseract_available():
                text = extract_text_with_tesseract(processed_image)
                all_texts.append(("tesseract", text))
            
            # 方法2: レイアウト分析
            layout_results = extract_text_with_layout_analysis(processed_image)
            all_texts.append(("layout_full", layout_results["full_text"]))
            
            # 領域ごとのテキストを保存
            for region, text in layout_results["regions"].items():
                if region not in all_region_texts:
                    all_region_texts[region] = []
                all_region_texts[region].append(text)
            
            # 方法3: Google Cloud Vision API（設定されている場合）
            if GOOGLE_VISION_AVAILABLE and config.get('use_google_vision', False):
                text = extract_with_google_vision(processed_image)
                all_texts.append(("google_vision", text))
            
            # 方法4: Azure Computer Vision（設定されている場合）
            if AZURE_VISION_AVAILABLE and config.get('use_azure_vision', False):
                subscription_key = config.get('azure_subscription_key', '')
                endpoint = config.get('azure_endpoint', '')
                if subscription_key and endpoint:
                    text = extract_with_azure_vision(processed_image, subscription_key, endpoint)
                    all_texts.append(("azure_vision", text))
            
            # 方法5: AWS Textract（設定されている場合）
            if AWS_TEXTRACT_AVAILABLE and config.get('use_aws_textract', False):
                text = extract_with_aws_textract(processed_image)
                all_texts.append(("aws_textract", text))
            
            # 一時ファイルを削除
            if processed_image != image_path:
                os.unlink(processed_image)
    
    finally:
        # 一時ファイルとディレクトリを削除
        if temp_dir:
            for image_path in image_paths:
                if os.path.exists(image_path):
                    os.unlink(image_path)
            os.rmdir(temp_dir)
    
    # 結果を返す
    results["all_texts"] = all_texts
    results["region_texts"] = all_region_texts
    
    return results


def select_best_text(texts):
    """
    複数のテキスト抽出結果から最適なものを選択する
    
    Args:
        texts: (method, text)のタプルのリスト
    
    Returns:
        最適なテキスト
    """
    if not texts:
        return ""
    
    # テキストの長さでスコアリング
    scored_texts = []
    for method, text in texts:
        # 空のテキストはスキップ
        if not text or text.isspace():
            continue
        
        # スコアを計算
        score = len(text)
        
        # 特定のメソッドにボーナスを与える
        if method == "google_vision":
            score *= 1.2
        elif method == "azure_vision":
            score *= 1.1
        elif method == "layout_full":
            score *= 1.05
        
        scored_texts.append((score, method, text))
    
    # スコアの高い順にソート
    scored_texts.sort(reverse=True)
    
    # 最高スコアのテキストを返す
    if scored_texts:
        return scored_texts[0][2]
    
    return ""


def get_combined_text(extraction_results):
    """
    抽出結果から最適なテキストを組み合わせる
    
    Args:
        extraction_results: extract_text_hybrid関数の結果
    
    Returns:
        組み合わせたテキスト
    """
    all_texts = extraction_results.get("all_texts", [])
    region_texts = extraction_results.get("region_texts", {})
    
    # 全体のテキストから最適なものを選択
    full_text = select_best_text(all_texts)
    
    # 中央部分のテキストを特に重視
    center_texts = region_texts.get("center", [])
    if center_texts:
        center_text = "\n".join(center_texts)
    else:
        center_text = ""
    
    # 結果を組み合わせる
    combined_text = full_text
    
    # 中央テキストが全体テキストに含まれていない場合は追加
    if center_text and center_text not in full_text:
        combined_text += "\n\n--- 中央部分 ---\n" + center_text
    
    return combined_text
