#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
テンプレートマッチングモジュール
請求書のテンプレートを登録し、同じフォーマットの請求書から情報を抽出する
"""

import os
import json
import logging
import hashlib
import numpy as np
import cv2
from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import tempfile

# ロギング設定
logger = logging.getLogger(__name__)

class TemplateManager:
    """請求書テンプレート管理クラス"""
    
    def __init__(self, templates_dir):
        """
        初期化
        
        Args:
            templates_dir: テンプレート保存ディレクトリ
        """
        self.templates_dir = templates_dir
        os.makedirs(templates_dir, exist_ok=True)
        self.templates = self._load_templates()
    
    def _load_templates(self):
        """保存されたテンプレートを読み込む"""
        templates = {}
        try:
            index_path = os.path.join(self.templates_dir, "template_index.json")
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    templates = json.load(f)
        except Exception as e:
            logger.error(f"テンプレート読み込みエラー: {str(e)}")
        
        return templates
    
    def _save_templates(self):
        """テンプレートを保存する"""
        try:
            index_path = os.path.join(self.templates_dir, "template_index.json")
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(self.templates, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"テンプレート保存エラー: {str(e)}")
    
    def register_template(self, image_path, name, regions):
        """
        新しいテンプレートを登録する
        
        Args:
            image_path: テンプレート画像のパス
            name: テンプレート名
            regions: 抽出対象領域の辞書 {
                "amount": {"x1": 100, "y1": 200, "x2": 300, "y2": 250},
                "customer": {"x1": 50, "y1": 100, "x2": 400, "y2": 150}
            }
        
        Returns:
            テンプレートID
        """
        try:
            # 画像を読み込む
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"画像を読み込めませんでした: {image_path}")
                return None
            
            # 画像のハッシュを計算
            image_hash = self._compute_image_hash(image)
            
            # テンプレートIDを生成
            template_id = hashlib.md5(f"{name}_{image_hash}".encode()).hexdigest()
            
            # テンプレート画像を保存
            template_image_path = os.path.join(self.templates_dir, f"{template_id}.png")
            cv2.imwrite(template_image_path, image)
            
            # テンプレート情報を登録
            self.templates[template_id] = {
                "name": name,
                "image_path": template_image_path,
                "regions": regions,
                "image_hash": image_hash
            }
            
            # テンプレートを保存
            self._save_templates()
            
            return template_id
        except Exception as e:
            logger.error(f"テンプレート登録エラー: {str(e)}")
            return None
    
    def _compute_image_hash(self, image):
        """
        画像のハッシュを計算する
        
        Args:
            image: OpenCV画像
        
        Returns:
            画像のハッシュ値
        """
        # 画像をグレースケールに変換
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # リサイズして特徴を抽出
        resized = cv2.resize(gray, (32, 32))
        
        # 平均ハッシュを計算
        avg = resized.mean()
        hash_str = ''.join('1' if px > avg else '0' for px in resized.flatten())
        
        return hash_str
    
    def find_matching_template(self, image_path):
        """
        画像に一致するテンプレートを検索する
        
        Args:
            image_path: 検索対象の画像パス
        
        Returns:
            一致したテンプレートID、または None
        """
        try:
            # 画像を読み込む
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"画像を読み込めませんでした: {image_path}")
                return None
            
            # 画像のハッシュを計算
            image_hash = self._compute_image_hash(image)
            
            # 最も類似度の高いテンプレートを検索
            best_match = None
            best_similarity = 0
            
            for template_id, template in self.templates.items():
                # ハッシュの類似度を計算
                template_hash = template["image_hash"]
                similarity = self._calculate_hash_similarity(image_hash, template_hash)
                
                if similarity > best_similarity and similarity > 0.7:  # 70%以上の類似度
                    best_similarity = similarity
                    best_match = template_id
            
            return best_match
        except Exception as e:
            logger.error(f"テンプレートマッチングエラー: {str(e)}")
            return None
    
    def _calculate_hash_similarity(self, hash1, hash2):
        """
        2つのハッシュ値の類似度を計算する
        
        Args:
            hash1: 1つ目のハッシュ値
            hash2: 2つ目のハッシュ値
        
        Returns:
            類似度（0.0〜1.0）
        """
        # ハッシュ値の長さが異なる場合
        if len(hash1) != len(hash2):
            return 0.0
        
        # 一致するビット数を数える
        matching_bits = sum(1 for a, b in zip(hash1, hash2) if a == b)
        
        # 類似度を計算
        return matching_bits / len(hash1)
    
    def extract_from_template(self, image_path, template_id):
        """
        テンプレートを使用して画像から情報を抽出する
        
        Args:
            image_path: 抽出対象の画像パス
            template_id: 使用するテンプレートID
        
        Returns:
            抽出された情報の辞書
        """
        try:
            # テンプレートが存在するか確認
            if template_id not in self.templates:
                logger.error(f"テンプレートが見つかりません: {template_id}")
                return {}
            
            # 画像を読み込む
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"画像を読み込めませんでした: {image_path}")
                return {}
            
            # テンプレート情報を取得
            template = self.templates[template_id]
            regions = template["regions"]
            
            # 各領域からテキストを抽出
            extracted_info = {}
            
            for field_name, region in regions.items():
                # 領域を切り出す
                x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]
                roi = image[y1:y2, x1:x2]
                
                # 一時ファイルに保存
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                    temp_path = temp_file.name
                    cv2.imwrite(temp_path, roi)
                    
                    # OCRでテキスト抽出
                    text = pytesseract.image_to_string(Image.open(temp_path), lang='jpn+eng')
                    extracted_info[field_name] = text.strip()
                    
                    # 一時ファイルを削除
                    os.unlink(temp_path)
            
            return extracted_info
        except Exception as e:
            logger.error(f"テンプレートからの抽出エラー: {str(e)}")
            return {}


def process_pdf_with_template_matching(pdf_path, templates_dir):
    """
    テンプレートマッチングを使用してPDFから情報を抽出する
    
    Args:
        pdf_path: PDFファイルのパス
        templates_dir: テンプレート保存ディレクトリ
    
    Returns:
        抽出された情報の辞書
    """
    try:
        # テンプレートマネージャーを初期化
        template_manager = TemplateManager(templates_dir)
        
        # PDFを画像に変換
        images = convert_from_path(pdf_path, dpi=300)
        
        # 最初のページのみ処理
        if not images:
            logger.error(f"PDFから画像を抽出できませんでした: {pdf_path}")
            return {}
        
        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            temp_path = temp_file.name
            images[0].save(temp_path, "PNG")
            
            # テンプレートを検索
            template_id = template_manager.find_matching_template(temp_path)
            
            if template_id:
                # テンプレートを使用して情報を抽出
                extracted_info = template_manager.extract_from_template(temp_path, template_id)
                
                # 一時ファイルを削除
                os.unlink(temp_path)
                
                return extracted_info
            else:
                logger.info(f"一致するテンプレートが見つかりませんでした: {pdf_path}")
                
                # 一時ファイルを削除
                os.unlink(temp_path)
                
                return {}
    except Exception as e:
        logger.error(f"テンプレートマッチング処理エラー: {str(e)}")
        return {}
