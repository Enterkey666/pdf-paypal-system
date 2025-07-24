import re
import logging
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)

class ExtractionResult(NamedTuple):
    """PDF抽出結果を格納するクラス"""
    customer: Optional[str]
    amount: Optional[int]
    raw_text: str = ""
    confidence: float = 0.0

def extract_amount_and_customer(text: str) -> ExtractionResult:
    """
    PDFテキストから顧客名と金額を抽出
    
    Args:
        text: PDFから抽出されたテキスト
        
    Returns:
        ExtractionResult: 抽出結果
    """
    
    # テキストを正規化
    normalized_text = text.replace('\n', ' ').replace('\r', ' ')
    normalized_text = re.sub(r'\s+', ' ', normalized_text).strip()
    
    # 金額抽出
    amount = extract_amount(normalized_text)
    
    # 顧客名抽出
    customer = extract_customer_name(normalized_text)
    
    # 信頼度計算
    confidence = calculate_confidence(customer, amount, normalized_text)
    
    logger.info(f"抽出結果 - 顧客: {customer}, 金額: {amount}, 信頼度: {confidence:.2f}")
    
    return ExtractionResult(
        customer=customer,
        amount=amount,
        raw_text=text,
        confidence=confidence
    )

def extract_amount(text: str) -> Optional[int]:
    """テキストから金額を抽出"""
    
    # 日本円のパターン
    yen_patterns = [
        r'(\d{1,3}(?:,\d{3})*)\s*円',  # 1,000円
        r'￥\s*(\d{1,3}(?:,\d{3})*)',  # ￥1,000
        r'金額[:\s]*(\d{1,3}(?:,\d{3})*)',  # 金額: 1,000
        r'合計[:\s]*(\d{1,3}(?:,\d{3})*)',  # 合計: 1,000
        r'請求額[:\s]*(\d{1,3}(?:,\d{3})*)',  # 請求額: 1,000
        r'総額[:\s]*(\d{1,3}(?:,\d{3})*)',  # 総額: 1,000
    ]
    
    for pattern in yen_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # 最初の有効な金額を返す
            for match in matches:
                try:
                    amount = int(match.replace(',', ''))
                    if 100 <= amount <= 10000000:  # 100円〜1000万円の範囲
                        return amount
                except ValueError:
                    continue
    
    # ドル・その他通貨のパターン
    dollar_patterns = [
        r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # $1,000.00
        r'USD\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # USD 1,000.00
    ]
    
    for pattern in dollar_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            for match in matches:
                try:
                    amount = float(match.replace(',', ''))
                    # ドルを円に概算変換（150円/ドル）
                    yen_amount = int(amount * 150)
                    if 100 <= yen_amount <= 10000000:
                        return yen_amount
                except ValueError:
                    continue
    
    # 単純な数字パターン（最後の手段）
    simple_patterns = [
        r'(\d{4,7})',  # 4-7桁の数字
    ]
    
    for pattern in simple_patterns:
        matches = re.findall(pattern, text)
        if matches:
            for match in matches:
                try:
                    amount = int(match)
                    if 1000 <= amount <= 1000000:  # 1,000円〜100万円の範囲
                        return amount
                except ValueError:
                    continue
    
    return None

def extract_customer_name(text: str) -> Optional[str]:
    """テキストから顧客名を抽出"""
    
    # 一般的な顧客名パターン
    customer_patterns = [
        r'お客様[:\s]*([^\s\n]{2,20})',  # お客様: 田中太郎
        r'顧客名[:\s]*([^\s\n]{2,20})',  # 顧客名: 田中太郎
        r'宛先[:\s]*([^\s\n]{2,20})',    # 宛先: 田中太郎
        r'請求先[:\s]*([^\s\n]{2,20})',  # 請求先: 田中太郎
        r'お名前[:\s]*([^\s\n]{2,20})',  # お名前: 田中太郎
        r'氏名[:\s]*([^\s\n]{2,20})',    # 氏名: 田中太郎
        r'様[:\s]*([^\s\n]{2,20})',      # 田中太郎様
        r'([^\s\n]{2,10})\s*様',         # 田中太郎 様
    ]
    
    # 無効な用語（会社名や一般的な用語を除外）
    invalid_terms = [
        '株式会社', '有限会社', '合同会社', '請求書', '領収書', '見積書',
        '担当者', '責任者', '代表者', '管理者', '事務所', '会社',
        '部署', '課', '係', '班', 'チーム', 'グループ',
        'お客様', '顧客', '利用者', 'ユーザー', '会員',
        '営業', '販売', '経理', '総務', '人事', '開発',
        '2023', '2024', '2025', '令和', '平成',
        'PDF', 'html', 'www', 'http', 'https', '.com', '.co.jp'
    ]
    
    for pattern in customer_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            for match in matches:
                # 空白を削除
                customer = match.strip()
                
                # 長さチェック
                if len(customer) < 2 or len(customer) > 20:
                    continue
                
                # 無効な用語チェック
                if any(term in customer for term in invalid_terms):
                    continue
                
                # 数字だけの場合は除外
                if customer.isdigit():
                    continue
                
                # 記号だけの場合は除外
                if re.match(r'^[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]+$', customer):
                    continue
                
                return customer
    
    # 日本語の名前パターン（ひらがな・カタカナ・漢字）
    japanese_name_pattern = r'([あ-ん]{2,5}[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{1,10}|[ア-ン]{2,5}[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{1,10}|[\u4E00-\u9FAF]{2,4})'
    
    matches = re.findall(japanese_name_pattern, text)
    if matches:
        for match in matches:
            customer = match.strip()
            if len(customer) >= 2 and not any(term in customer for term in invalid_terms):
                return customer
    
    return None

def calculate_confidence(customer: Optional[str], amount: Optional[int], text: str) -> float:
    """抽出結果の信頼度を計算"""
    
    confidence = 0.0
    
    # 顧客名の信頼度
    if customer:
        confidence += 0.4
        # 日本語の名前らしさ
        if re.match(r'^[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\s]+$', customer):
            confidence += 0.1
        # 適切な長さ
        if 2 <= len(customer) <= 10:
            confidence += 0.1
    
    # 金額の信頼度
    if amount:
        confidence += 0.3
        # 現実的な金額範囲
        if 500 <= amount <= 100000:
            confidence += 0.1
    
    # テキスト品質の信頼度
    if text:
        # 日本語テキストの割合
        japanese_chars = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text))
        if japanese_chars > len(text) * 0.3:
            confidence += 0.1
        
        # 請求書・領収書キーワードの存在
        keywords = ['請求', '領収', '金額', '合計', '支払', '料金']
        if any(keyword in text for keyword in keywords):
            confidence += 0.1
    
    return min(confidence, 1.0)