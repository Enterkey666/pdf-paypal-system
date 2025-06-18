import re
import math
import logging
from typing import List, Dict, Tuple, Optional, Any
from text_normalizer import normalize_text, extract_readable_content

# ロガーの設定
logger = logging.getLogger(__name__)

class AmountExtractor:
    """
    高精度な請求金額抽出のためのクラス
    請求書から金額を抽出するための様々な戦略を実装
    """
    
    def __init__(self):
        # 重要キーワード - 完全一致
        self.target_keywords = [
            "ご請求金額", "請求金額", "合計請求額", "ご請求額", "総請求額",
            "合計金額", "お支払金額", "お支払い金額", "お支払額"
        ]
        
        # 除外キーワード
        self.exclude_keywords = [
            "小計", "消費税", "税額", "明細", "単価", "数量", 
            "振込手数料", "前回繰越", "中間金額", "郵便番号", "受給者番号",
            "〒", "電話番号", "TEL", "FAX", "年月日"
        ]
        
        # 部分一致キーワード
        self.partial_keywords = ["請求", "合計", "支払", "金額", "総額"]
    
    def normalize_text(self, text: str) -> str:
        """テキストの正規化（全角→半角、空白除去など）"""
        # 全角数字・記号を半角に変換
        zen_han_map = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '　': ' ', '，': ',', '．': '.', '￥': '¥', '円': '円'
        }
        for zen, han in zen_han_map.items():
            text = text.replace(zen, han)
            
        return text
    
    def yen_to_int(self, s: str) -> int:
        """金額表記を整数値に変換（例: "123,456" → 123456）"""
        try:
            # カンマ、円記号、スペースを除去
            cleaned = s.replace(",", "").replace("¥", "").replace("￥", "").replace(" ", "").replace("円", "")
            return int(cleaned)
        except ValueError:
            return 0
    
    def collect_candidates(self, text: str, page_idx: int = 0, n_pages: int = 1) -> List[Dict[str, Any]]:
        """金額候補行を収集する"""
        # 郵便番号や受給者番号のパターン
        postal_code_pattern = r'〒\s*[0-9]{3}[-－]?[0-9]{4}'
        recipient_number_pattern = r'[（(][0-9]{7,10}[）)]'
        phone_number_pattern = r'(?:TEL|電話)[：:]?\s*[0-9\-\(\)（）]{10,13}'
        candidates = []
        lines = text.split('\n')
        
        # ページ下部20%の行を特定するため、全体行数の80%以降の行にフラグを設定
        bottom_threshold = int(len(lines) * 0.8)
        
        # 行ごとに処理
        for i, line in enumerate(lines):
            normalized_line = self.normalize_text(line)
            
            # 金額候補を含む行を検出
            amount_matches = re.findall(r"[0-9,]+", normalized_line)
            if not amount_matches:
                continue
                
            # ① キーワード含有チェック
            is_target_line = any(k in normalized_line for k in self.target_keywords)
            has_exclude = any(e in normalized_line for e in self.exclude_keywords)
            
            # 電話番号、郵便番号、受給者番号を除外
            phone_match = re.search(r"電話.*?([0-9０-９\-−－]+)", normalized_line)
            postal_match = re.search(r"〒.*?([0-9０-９\-−－]+)", normalized_line)
            id_match = re.search(r"番号.*?([0-9０-９\-−－]+)", normalized_line)
            
            if has_exclude or phone_match or postal_match or id_match:
                continue
            
            # 有効な金額候補を抽出
            valid_amounts = []
            for amt_str in amount_matches:
                amt = self.yen_to_int(amt_str)
                if amt >= 100 and amt <= 10000000:  # 100円から1000万円までの範囲
                    valid_amounts.append(amt)
            
            if not valid_amounts:
                continue
                
            # 最大の金額を使用
            amount = max(valid_amounts)
            
            # タグ付け
            is_bottom = i >= bottom_threshold
            is_last_page = page_idx == n_pages - 1
            has_yen = '¥' in normalized_line or '￥' in normalized_line or '円' in normalized_line
            
            # 重要なコンテキストに基づいて特徴量を計算
            features = {
                "kw_exact": 1 if is_target_line else 0,
                "kw_loose": 1 if any(k in normalized_line for k in self.partial_keywords) else 0,
                "largest": amount,
                "page_last": 1 if is_last_page else 0,
                "bottom": 1 if is_bottom else 0,
                "has_yen": 1 if has_yen else 0,
                "line": line,
                "amount": amount
            }
            
            candidates.append(features)
        
        # ヒットがなかった場合のフォールバック: ページ最下部の金額を含む行を追加
        if not any(c["kw_exact"] == 1 for c in candidates) and page_idx == n_pages - 1:
            bottom_lines = lines[bottom_threshold:] if bottom_threshold < len(lines) else lines[-5:]
            for line in bottom_lines:
                normalized_line = self.normalize_text(line)
                amount_matches = re.findall(r"[0-9,]+", normalized_line)
                
                for amt_str in amount_matches:
                    amt = self.yen_to_int(amt_str)
                    if amt >= 1000 and amt <= 10000000:  # 1000円から1000万円まで
                        has_yen = '¥' in normalized_line or '￥' in normalized_line or '円' in normalized_line
                        candidates.append({
                            "kw_exact": 0,
                            "kw_loose": 0,
                            "largest": amt,
                            "page_last": 1,
                            "bottom": 1,
                            "has_yen": 1 if has_yen else 0,
                            "line": line,
                            "amount": amt
                        })
        
        return candidates
    
    def filter_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """候補をフィルタリングして優先順位付けする"""
        if not candidates:
            return []
            
        # 郵便番号や受給者番号のパターン
        postal_code_pattern = r'〒\s*[0-9]{3}[-－]?[0-9]{4}'
        recipient_number_pattern = r'[（(][0-9]{7,10}[）)]'
        phone_number_pattern = r'(?:TEL|電話)[：:]?\s*[0-9\-\(\)（）]{10,13}'
        date_pattern = r'[0-9]{4}[年/\-][0-9]{1,2}[月/\-][0-9]{1,2}日?'
        
        filtered_candidates = []
        for candidate in candidates:
            context = candidate.get('context', '')
            amount_str = str(candidate['amount'])
            
            # 郵便番号パターンとマッチするか確認
            if re.search(postal_code_pattern, context):
                postal_match = re.search(r'〒\s*([0-9]{3}[-－]?[0-9]{4})', context)
                if postal_match and postal_match.group(1).replace('-', '').replace('－', '') == amount_str:
                    logger.info(f"郵便番号と一致する金額を除外: {amount_str}")
                    continue
            
            # 受給者番号パターンとマッチするか確認
            if re.search(recipient_number_pattern, context):
                recipient_match = re.search(r'[（(]([0-9]{7,10})[）)]', context)
                if recipient_match and (amount_str in recipient_match.group(1) or recipient_match.group(1) in amount_str):
                    logger.info(f"受給者番号と一致する金額を除外: {amount_str}")
                    continue
            
            # 電話番号パターンとマッチするか確認
            if re.search(phone_number_pattern, context):
                phone_match = re.search(r'(?:TEL|電話)[：:]?\s*([0-9\-]{10,13})', context)
                if phone_match and phone_match.group(1).replace('-', '') == amount_str:
                    logger.info(f"電話番号と一致する金額を除外: {amount_str}")
                    continue
            
            # 日付パターンとマッチするか確認
            if re.search(date_pattern, context):
                date_match = re.search(date_pattern, context)
                if date_match and date_match.group(0).replace('年', '').replace('月', '').replace('日', '').replace('/', '').replace('-', '') == amount_str:
                    logger.info(f"日付と一致する金額を除外: {amount_str}")
                    continue
            
            filtered_candidates.append(candidate)
        
        return filtered_candidates
    
    def score_candidate(self, candidate: Dict[str, Any]) -> float:
        """候補に重み付けスコアを与える"""
        score = 0
        
        # キーワード一致によるスコア
        if candidate["kw_exact"]:
            score += 6
        if candidate["kw_loose"]:
            score += 3
            
        # 位置によるスコア
        if candidate["page_last"]:
            score += 2
        if candidate["bottom"]:
            score += 1
            
        # 金額の特徴によるスコア
        amount = candidate["amount"]
        
        # 円記号があればボーナス
        if candidate["has_yen"]:
            score += 2
            
        # 金額の大きさによるスコアを対数スケールで加算
        if amount > 0:
            score += math.log10(amount)
            
        # 丸い数字（1000や10000の倍数）にはボーナス
        if amount % 1000 == 0:
            score += 0.5
        if amount % 10000 == 0:
            score += 0.5
            
        return score
    
    def pick_invoice_amount(self, text: str, page_idx: int = 0, n_pages: int = 1) -> Optional[int]:
        """請求書金額を抽出する"""
        if not text:
            return None
            
        # 候補収集
        candidates = self.collect_candidates(text, page_idx, n_pages)
        
        if not candidates:
            return None
            
        # フィルタリング
        filtered_candidates = self.filter_candidates(candidates)
        
        if not filtered_candidates:
            return None
            
        # スコアリング
        for i, candidate in enumerate(filtered_candidates):
            filtered_candidates[i]["score"] = self.score_candidate(candidate)
            
        # スコア降順でソート
        filtered_candidates.sort(key=lambda x: x["score"], reverse=True)
        
        # 最高スコアの候補を返す
        if filtered_candidates:
            return filtered_candidates[0]["amount"]
            
        return None
        
    def extract_from_pdf_text(self, text: str, page_count: int = 1) -> Tuple[Optional[int], str]:
        """
        PDFテキストから請求金額を抽出し、金額と元の行を返す
        複数ページの場合は最後のページを優先
        """
        if not text:
            return None, ""
            
        lines = text.split('\n')
        best_amount = None
        best_line = ""
        best_score = -float('inf')
        
        # 各ページとして扱う（単一テキストの場合はページ数=1）
        for page_idx in range(page_count):
            # 単一テキストをページ数で分割する簡易的な方法
            page_start = int(len(lines) * page_idx / page_count)
            page_end = int(len(lines) * (page_idx + 1) / page_count)
            page_text = '\n'.join(lines[page_start:page_end])
            
            # 候補収集とスコアリング
            candidates = self.collect_candidates(page_text, page_idx, page_count)
            
            if not candidates:
                continue
                
            for candidate in candidates:
                score = self.score_candidate(candidate)
                if score > best_score:
                    best_score = score
                    best_amount = candidate["amount"]
                    best_line = candidate["line"]
        
        return best_amount, best_line

# シングルトンインスタンスを作成
extractor = AmountExtractor()

def extract_invoice_amount(text: str, page_count: int = 1) -> Tuple[Optional[int], str]:
    """
    PDFテキストから請求金額を抽出するユーティリティ関数
    戻り値: (金額, 抽出元の行)のタプル、金額が見つからない場合はNone
    """
    return extractor.extract_from_pdf_text(text, page_count)
