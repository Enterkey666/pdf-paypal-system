import re
import logging

logger = logging.getLogger(__name__)

def extract_customer_and_amount(text):
    """
    PDFテキストから顧客名と金額を抽出する
    
    Args:
        text (str): PDFから抽出されたテキスト
        
    Returns:
        dict: 抽出された顧客名と金額の辞書
    """
    result = {
        'customer': '',
        'amount': '',
        'formatted_customer': '',
        'formatted_amount': ''
    }
    
    try:
        # 顧客名の抽出パターン
        customer_patterns = [
            r'(?:お客様|顧客|氏名|名前)[:：\s]*([^\n\r]+)',
            r'(?:様|さん)\s*([^\n\r]+)',
            r'(?:宛先|送付先)[:：\s]*([^\n\r]+)',
            r'([^\n\r]*様)',
            r'([^\n\r]*さん)',
        ]
        
        # 金額の抽出パターン
        amount_patterns = [
            r'(?:金額|料金|代金|請求額|合計)[:：\s]*([0-9,]+)(?:円|¥)?',
            r'¥\s*([0-9,]+)',
            r'([0-9,]+)\s*円',
            r'(?:税込|税抜)[:：\s]*([0-9,]+)(?:円|¥)?',
        ]
        
        # 顧客名を抽出
        for pattern in customer_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                customer = match.group(1).strip()
                if customer and len(customer) > 1:
                    result['customer'] = customer
                    result['formatted_customer'] = customer
                    break
        
        # 金額を抽出
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = match.group(1).strip()
                if amount:
                    # カンマを除去して数値として処理
                    amount_num = amount.replace(',', '')
                    if amount_num.isdigit():
                        result['amount'] = amount_num
                        result['formatted_amount'] = f"¥{amount}"
                        break
        
        logger.info(f"抽出結果: 顧客={result['customer']}, 金額={result['amount']}")
        
    except Exception as e:
        logger.error(f"顧客名・金額抽出エラー: {str(e)}")
    
    return result

def validate_extraction(customer, amount):
    """
    抽出された顧客名と金額を検証する
    
    Args:
        customer (str): 顧客名
        amount (str): 金額
        
    Returns:
        dict: 検証結果
    """
    result = {
        'valid': True,
        'errors': []
    }
    
    if not customer or len(customer.strip()) < 2:
        result['valid'] = False
        result['errors'].append('顧客名が正しく抽出されていません')
    
    if not amount or not amount.replace(',', '').isdigit():
        result['valid'] = False
        result['errors'].append('金額が正しく抽出されていません')
    
    return result
