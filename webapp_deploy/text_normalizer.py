import re
import unicodedata
from typing import Dict, Any, Optional

class TextNormalizer:
    """
    日本語PDFテキストの正規化を行うクラス
    文字化け対策、エンコーディング問題の解決を担当
    """
    
    def __init__(self):
        # 全角→半角変換マッピング
        self.zen_han_map = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '　': ' ', '，': ',', '．': '.', '￥': '¥', '：': ':',
            'ー': '-', '－': '-', '−': '-', '／': '/', '％': '%'
        }
        
        # 一般的な文字化けパターン（PDFで発生する一般的なケース）
        self.mojibake_patterns = {
            '�': '',  # 認識不能文字を削除
            '��': '',  # 連続した認識不能文字
            r'\u3000': ' ',  # 全角スペース
            r'\ufffd': '',  # Unicode REPLACEMENT CHARACTER
        }
    
    def normalize_spaces(self, text: str) -> str:
        """空白の正規化（連続スペースの単一化など）"""
        if not text:
            return ""
        
        # 連続する空白を1つに
        text = re.sub(r'\s+', ' ', text)
        # 行頭と行末の空白を削除
        text = re.sub(r'^\s+|\s+$', '', text, flags=re.MULTILINE)
        return text
    
    def normalize_zenkaku(self, text: str) -> str:
        """全角文字を半角に変換"""
        if not text:
            return ""
            
        for zen, han in self.zen_han_map.items():
            text = text.replace(zen, han)
        return text
    
    def remove_mojibake(self, text: str) -> str:
        """文字化け文字の除去と置換"""
        if not text:
            return ""
            
        # 一般的な文字化けパターンを置換
        for pattern, replacement in self.mojibake_patterns.items():
            text = text.replace(pattern, replacement)
        
        # 認識不能文字（�）を含む行の修復を試みる
        lines = text.split('\n')
        fixed_lines = []
        
        for line in lines:
            # 認識不能文字を含む行
            if '�' in line:
                # 数字のみの部分を抽出保存
                numbers = re.findall(r'[0-9,]+', line)
                # 認識可能な日本語文字を保持
                readable_chars = ''.join([c for c in line if c != '�' and (not unicodedata.category(c).startswith('C'))])
                
                if numbers or readable_chars:
                    # 認識可能な部分を組み合わせて復元
                    fixed_line = readable_chars
                    for num in numbers:
                        if num not in fixed_line:
                            fixed_line += f" {num}"
                    fixed_lines.append(fixed_line)
                else:
                    # 復元不可能な場合は行を除外
                    continue
            else:
                fixed_lines.append(line)
                
        return '\n'.join(fixed_lines)
    
    def normalize(self, text: str) -> str:
        """テキストの総合的な正規化処理"""
        if not text:
            return ""
            
        # 1. 文字化け対応
        text = self.remove_mojibake(text)
        
        # 2. 全角→半角変換
        text = self.normalize_zenkaku(text)
        
        # 3. 空白の正規化
        text = self.normalize_spaces(text)
        
        return text
    
    def extract_readable_text(self, text: str) -> Dict[str, Any]:
        """
        文字化けしたテキストから読める部分を抽出し、
        構造化情報として返す
        """
        if not text:
            return {"text": "", "lines": [], "numbers": [], "readable_ratio": 0}
            
        lines = text.split('\n')
        readable_lines = []
        all_numbers = []
        
        for line in lines:
            # 行の半分以上が読める文字であれば追加
            readable_chars = sum(1 for c in line if c != '�' and (not unicodedata.category(c).startswith('C')))
            if readable_chars > len(line) / 2:
                readable_lines.append(line)
                
            # 数値を抽出（金額として使える可能性あり）
            numbers = re.findall(r'[0-9,]+', line)
            if numbers:
                all_numbers.extend(numbers)
                
        # 読める文字の割合を計算
        total_chars = len(text) if text else 1
        readable_chars = sum(1 for c in text if c != '�' and (not unicodedata.category(c).startswith('C')))
        readable_ratio = readable_chars / total_chars
        
        return {
            "text": '\n'.join(readable_lines),
            "lines": readable_lines,
            "numbers": all_numbers,
            "readable_ratio": readable_ratio
        }

# シングルトンインスタンス
normalizer = TextNormalizer()

def normalize_text(text: str) -> str:
    """テキスト正規化のためのユーティリティ関数"""
    return normalizer.normalize(text)

def extract_readable_content(text: str) -> Dict[str, Any]:
    """文字化けテキストから読める部分を抽出するユーティリティ関数"""
    return normalizer.extract_readable_text(text)
