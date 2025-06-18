#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
インタラクティブな修正機能モジュール
OCRで抽出した結果をユーザーが確認・修正できるインターフェースを提供する
"""

import os
import json
import logging
import datetime
from flask import render_template, request, jsonify

# ロギング設定
logger = logging.getLogger(__name__)

class CorrectionHistory:
    """修正履歴管理クラス"""
    
    def __init__(self, history_dir):
        """
        初期化
        
        Args:
            history_dir: 履歴保存ディレクトリ
        """
        self.history_dir = history_dir
        os.makedirs(history_dir, exist_ok=True)
        self.history_file = os.path.join(history_dir, "correction_history.json")
        self.history = self._load_history()
    
    def _load_history(self):
        """保存された履歴を読み込む"""
        history = []
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
        except Exception as e:
            logger.error(f"履歴読み込みエラー: {str(e)}")
        
        return history
    
    def _save_history(self):
        """履歴を保存する"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"履歴保存エラー: {str(e)}")
    
    def add_correction(self, original_data, corrected_data, filename):
        """
        修正履歴を追加する
        
        Args:
            original_data: 元のデータ
            corrected_data: 修正後のデータ
            filename: 対象ファイル名
        """
        try:
            timestamp = datetime.datetime.now().isoformat()
            
            correction = {
                "timestamp": timestamp,
                "filename": filename,
                "original": original_data,
                "corrected": corrected_data
            }
            
            self.history.append(correction)
            
            # 履歴が長すぎる場合は古いものを削除
            if len(self.history) > 1000:
                self.history = self.history[-1000:]
            
            self._save_history()
        except Exception as e:
            logger.error(f"修正履歴追加エラー: {str(e)}")
    
    def get_history(self, limit=100):
        """
        修正履歴を取得する
        
        Args:
            limit: 取得する履歴の最大数
        
        Returns:
            修正履歴のリスト
        """
        return self.history[-limit:]


class LearningData:
    """学習データ管理クラス"""
    
    def __init__(self, data_dir):
        """
        初期化
        
        Args:
            data_dir: データ保存ディレクトリ
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.data_file = os.path.join(data_dir, "learning_data.json")
        self.data = self._load_data()
    
    def _load_data(self):
        """保存されたデータを読み込む"""
        data = {
            "amount_patterns": [],
            "customer_patterns": [],
            "corrections": {}
        }
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
        except Exception as e:
            logger.error(f"学習データ読み込みエラー: {str(e)}")
        
        return data
    
    def _save_data(self):
        """データを保存する"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"学習データ保存エラー: {str(e)}")
    
    def add_correction(self, field, original, corrected):
        """
        修正データを追加する
        
        Args:
            field: フィールド名（"amount"または"customer"）
            original: 元の値
            corrected: 修正後の値
        """
        try:
            key = f"{field}:{original}"
            self.data["corrections"][key] = corrected
            
            # パターンを学習
            if field == "amount":
                self._learn_amount_pattern(original, corrected)
            elif field == "customer":
                self._learn_customer_pattern(original, corrected)
            
            self._save_data()
        except Exception as e:
            logger.error(f"修正データ追加エラー: {str(e)}")
    
    def _learn_amount_pattern(self, original, corrected):
        """
        金額パターンを学習する
        
        Args:
            original: 元の金額
            corrected: 修正後の金額
        """
        # 既存のパターンと類似していないか確認
        for pattern in self.data["amount_patterns"]:
            if self._is_similar_pattern(original, pattern["pattern"]):
                # 類似パターンが見つかった場合は出現回数を増やす
                pattern["count"] += 1
                return
        
        # 新しいパターンを追加
        self.data["amount_patterns"].append({
            "pattern": original,
            "correction": corrected,
            "count": 1
        })
    
    def _learn_customer_pattern(self, original, corrected):
        """
        顧客名パターンを学習する
        
        Args:
            original: 元の顧客名
            corrected: 修正後の顧客名
        """
        # 既存のパターンと類似していないか確認
        for pattern in self.data["customer_patterns"]:
            if self._is_similar_text(original, pattern["pattern"]):
                # 類似パターンが見つかった場合は出現回数を増やす
                pattern["count"] += 1
                return
        
        # 新しいパターンを追加
        self.data["customer_patterns"].append({
            "pattern": original,
            "correction": corrected,
            "count": 1
        })
    
    def _is_similar_pattern(self, text1, text2):
        """
        2つのパターンが類似しているか判定する
        
        Args:
            text1: 1つ目のテキスト
            text2: 2つ目のテキスト
        
        Returns:
            類似している場合はTrue
        """
        # 簡易的な類似度計算
        # 実際のアプリケーションではより高度なアルゴリズムを使用する
        return text1 == text2
    
    def _is_similar_text(self, text1, text2):
        """
        2つのテキストが類似しているか判定する
        
        Args:
            text1: 1つ目のテキスト
            text2: 2つ目のテキスト
        
        Returns:
            類似している場合はTrue
        """
        # 簡易的な類似度計算
        # 実際のアプリケーションではより高度なアルゴリズムを使用する
        return text1.lower() == text2.lower()
    
    def get_correction_suggestion(self, field, value):
        """
        修正候補を取得する
        
        Args:
            field: フィールド名（"amount"または"customer"）
            value: 元の値
        
        Returns:
            修正候補
        """
        # 直接一致する修正がある場合
        key = f"{field}:{value}"
        if key in self.data["corrections"]:
            return self.data["corrections"][key]
        
        # パターンマッチングで類似する修正を探す
        patterns = self.data["amount_patterns"] if field == "amount" else self.data["customer_patterns"]
        
        for pattern in patterns:
            if self._is_similar_pattern(value, pattern["pattern"]):
                return pattern["correction"]
        
        return None
        
    def get_correction_suggestions(self, field, value):
        """
        修正候補を複数取得する（互換性のため、単数形の関数のエイリアス）
        
        Args:
            field: フィールド名（"amount"または"customer"）
            value: 元の値
        
        Returns:
            修正候補のリスト
        """
        suggestion = self.get_correction_suggestion(field, value)
        if suggestion:
            return [suggestion]
        return []


# Flaskルート関数
def setup_interactive_correction_routes(app, history_dir, data_dir):
    """
    インタラクティブな修正機能のルートを設定する
    
    Args:
        app: Flaskアプリケーション
        history_dir: 履歴保存ディレクトリ
        data_dir: データ保存ディレクトリ
    """
    correction_history = CorrectionHistory(history_dir)
    learning_data = LearningData(data_dir)
    
    @app.route('/correction', methods=['GET'])
    def correction_page():
        """修正ページを表示する"""
        return render_template('correction.html')
    
    @app.route('/api/correction/history', methods=['GET'])
    def get_correction_history():
        """修正履歴を取得する"""
        limit = request.args.get('limit', 100, type=int)
        history = correction_history.get_history(limit)
        return jsonify({"history": history})
    
    @app.route('/api/correction/save', methods=['POST'])
    def save_correction():
        """修正を保存する"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "データがありません"}), 400
            
            original_data = data.get('original', {})
            corrected_data = data.get('corrected', {})
            filename = data.get('filename', '')
            
            # 修正履歴を追加
            correction_history.add_correction(original_data, corrected_data, filename)
            
            # 学習データに追加
            for field in ['amount', 'customer']:
                if field in original_data and field in corrected_data:
                    if original_data[field] != corrected_data[field]:
                        learning_data.add_correction(field, original_data[field], corrected_data[field])
            
            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"修正保存エラー: {str(e)}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/correction/suggest', methods=['POST'])
    def get_correction_suggestion():
        """修正候補を取得する"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "データがありません"}), 400
            
            field = data.get('field', '')
            value = data.get('value', '')
            
            if not field or not value:
                return jsonify({"error": "フィールドまたは値が指定されていません"}), 400
            
            suggestion = learning_data.get_correction_suggestion(field, value)
            
            return jsonify({
                "success": True,
                "suggestion": suggestion
            })
        except Exception as e:
            logger.error(f"修正候補取得エラー: {str(e)}")
            return jsonify({"error": str(e)}), 500
