import re
import logging
from typing import Tuple, Optional, List, Dict, Any, NamedTuple

# 新しいモジュールをインポート
from text_normalizer import normalize_text, extract_readable_content


def is_valid_customer_name(customer: str, invalid_terms: list) -> bool:
    """
    顧客名が有効かどうかをチェックする
    
    Args:
        customer: チェックする顧客名
        invalid_terms: 無効な用語のリスト
        
    Returns:
        bool: 有効な顧客名であればTrue、そうでなければFalse
    """
    # 空文字列や None の場合は無効
    if not customer:
        print(f"空の顧客名を除外")
        return False
        
    # 数字のみの顧客名は無効
    if customer.isdigit():
        print(f"数字のみの顧客名を除外: {customer}")
        return False
    
    # 顧客名が短すぎる場合も除外
    if len(customer) < 2:
        print(f"短すぎる顧客名を除外: {customer}")
        return False
        
    # 顧客名に文字が含まれているか確認
    if not any(c.isalpha() for c in customer):
        print(f"文字が含まれていない顧客名を除外: {customer}")
        return False
    
    # 顧客名が金額関連の用語でないかチェック
    for invalid_term in invalid_terms:
        if invalid_term in customer or customer in invalid_term:
            print(f"金額関連の用語を顧客名から除外: {customer} (含まれる無効な用語: {invalid_term})")
            return False
            
    # すべてのチェックをパスした場合は有効
    return True
from amount_extractor import extract_invoice_amount

# ロガーの設定
logger = logging.getLogger(__name__)

# 抽出結果を表す名前付きタプル
class ExtractionResult(NamedTuple):
    customer: Optional[str]
    amount: Optional[str]
    context: Optional[Dict[str, Any]] = None  # 追加情報（元の行、スコアなど）

def extract_amount_only(text: str) -> Optional[int]:
    """
    テキストから金額のみを抽出する
    複数の正規表現パターンを使用して金額を抽出し、最も適切なものを返す
    
    Args:
        text: 抽出元のテキスト
        
    Returns:
        抽出された金額（整数）、見つからない場合はNone
    """
    if not text:
        return None
    
    # デバッグ情報
    logger.info(f"金額抽出処理開始 (テキスト長: {len(text)} 文字)")
        
    # テキストの正規化（全角→半角、空白除去など）
    normalized_text = normalize_text(text)
    
    # 文字化けしているテキストから読みやすい部分を抽出
    readable_data = extract_readable_content(text)
    if readable_data["readable_ratio"] < 0.5:  # 読める文字が50%未満の場合
        # 読み取り可能な部分だけを使用
        text = readable_data["text"]
        normalized_text = normalize_text(text)
        logger.info(f"読み取り可能な部分のみ使用: {len(text)} 文字")
    
    # コンテキスト情報を取得（「万」などの単位を検出するため）
    context = texts = {
        '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
        '六': '6', '七': '7', '八': '8', '九': '9', '零': '0',
        '拾': '10', '百': '00', '千': '000', '万': '0000'
    }
    
    # 金額を抽出するための正規表現パターン（優先度順）
    amount_patterns = [
        # 請求書や領収書でよく使われるパターン（最優先）
        r'(?:ご請求金額|請求金額|請求額|合計金額|合計額|総額|お支払金額|お支払い金額)[\s:：]*[¥￥]?\s*([0-9,.]+)',
        r'(?:合計|総計|総合計|総請求額)[\s:：]*[¥￥]?\s*([0-9,.]+)',
        
        # 金額の前後に「円」がつくパターン
        r'([0-9,.]+)\s*円',
        r'金額[\s:：]*([0-9,.]+)\s*円',
        
        # 通貨記号付きの金額
        r'[¥￥]\s*([0-9,.￥¥]+)',
        
        # 3桁以上の数字（少額請求）
        r'\b([1-9][0-9]{2,5})\b',  # 100〜99999の3-6桁の数字
        
        # 金額のみのパターン（最後の手段）
        r'\b([0-9]{3,6})\b'  # 単語境界を追加して、IDの一部を拾わないようにする
    ]
    
    # 配列にパターンマッチ結果を保存（優先度、金額、コンテキスト）
    found_amounts = []
    
    # 両方のテキストで探索（元のテキストと正規化したテキスト）
    for search_text in [text, normalized_text]:
        for priority, pattern in enumerate(amount_patterns):
            matches = re.finditer(pattern, search_text, re.MULTILINE)
            for match in matches:
                try:
                    # 数値文字列を正規化（カンマ・スペース・通貨記号を除去）
                    amount_str = (match.group(1)
                                   .replace(',', '')
                                   .replace(' ', '')
                                   .replace('\u3000', '')   # 全角スペース
                                   .replace('¥', '')
                                   .replace('￥', '')
                                   .replace('\u00a5', ''))  # FULLWIDTH YEN SIGN
                    
                    # 「?」や「�」が含まれる場合の特殊処理
                    if '?' in amount_str or '�' in amount_str or '\ufffd' in amount_str:
                        # 認識できない文字が連続している場合、その数を桁数として扱う
                        unknown_chars = re.search(r'([\?�\ufffd]+)', amount_str)
                        if unknown_chars:
                            # 認識できない文字の数を数えて、その桁数の平均的な金額を推定
                            num_digits = len(unknown_chars.group(1))
                            if num_digits >= 1 and num_digits <= 7:
                                # コンテキストから推定する
                                if '万' in context:
                                    # 万単位の場合
                                    base = 10000
                                else:
                                    # 通常の場合
                                    base = 10 ** (num_digits - 1)
                                
                                # 推定金額を計算
                                amt = base
                                print(f"認識できない文字を含む金額を推定: {amount_str} → {amt}円 ({num_digits}桁)")
                                # 推定値なので優先度を下げる
                                weight = 1
                                found_amounts.append((weight, amt, context))
                                continue
                    
                    amt = int(amount_str)
                    
                    # 妥当な金額範囲のみ取得
                    if 100 <= amt < 10000000:  # 100円から1000万円まで
                        context = search_text[max(0, match.start() - 40):min(len(search_text), match.end() + 40)]
                        
                        # 郵便番号や受給者番号などを除外するフィルタリング
                        # 郵便番号パターン（例: 〒7000804）
                        if re.search(r'〒\s*[0-9]{3,7}', context):
                            postal_match = re.search(r'〒\s*([0-9]{3}[-－]?[0-9]{4})', context)
                            if postal_match and postal_match.group(1).replace('-', '').replace('－', '') == str(amt):
                                logger.info(f"郵便番号と一致する金額を除外: {amt}")
                                continue
                                
                        # 受給者番号パターン（例: （3000068924））
                        if re.search(r'[（(][0-9]{7,10}[）)]', context):
                            recipient_match = re.search(r'[（(]([0-9]{7,10})[）)]', context)
                            if recipient_match:
                                recipient_num = recipient_match.group(1)
                                # 受給者番号の一部が金額と一致する場合も除外
                                if str(amt) in recipient_num or recipient_num in str(amt):
                                    logger.info(f"受給者番号と一致する金額を除外: {amt}, 受給者番号: {recipient_num}")
                                    continue
                        
                        # 受給者番号が前後の文脈に含まれる場合も除外
                        if '受給者' in context and re.search(r'[0-9]{7,10}', context):
                            for num_match in re.finditer(r'[0-9]{7,10}', context):
                                if str(amt) in num_match.group(0) or num_match.group(0) in str(amt):
                                    logger.info(f"受給者関連の番号と一致する金額を除外: {amt}")
                                    continue
                                    
                        # 電話番号パターンと一致する場合も除外
                        phone_pattern = r'(?:TEL|電話|FAX|ファックス)[：:]?\s*[0-9\-]{10,13}'
                        if re.search(phone_pattern, context):
                            phone_match = re.search(r'(?:TEL|電話|FAX|ファックス)[：:]?\s*([0-9\-]{10,13})', context)
                            if phone_match and phone_match.group(1).replace('-', '') == str(amt):
                                logger.info(f"電話番号と一致する金額を除外: {amt}")
                                continue
                                
                        # 日付パターンと一致する場合も除外
                        date_pattern = r'[0-9]{4}[年/\-][0-9]{1,2}[月/\-][0-9]{1,2}日?'
                        if re.search(date_pattern, context):
                            date_match = re.search(date_pattern, context)
                            if date_match and date_match.group(0).replace('年', '').replace('月', '').replace('日', '').replace('/', '').replace('-', '') == str(amt):
                                logger.info(f"日付と一致する金額を除外: {amt}")
                                continue
                        
                        # 優先度を計算（パターンの順序が重要）
                        weight = len(amount_patterns) - priority
                        
                        # 重要なキーワードに基づく優先度調整
                        if 'ご請求額' in context:
                            weight += 15
                        elif '請求額' in context:
                            weight += 12
                        elif '合計' in context and '合計' in context[max(0, match.start() - 20):match.end() + 20]:
                            weight += 10  # 合計の優先度を大幅に上げる（ただし近い位置に「合計」がある場合のみ）
                        elif '総額' in context:
                            weight += 8
                        elif '金額' in context and '金額' in context[max(0, match.start() - 20):match.end() + 20]:
                            weight += 7  # 「金額」キーワードが近くにある場合
                        elif 'お支払' in context:
                            weight += 6  # 「お支払」キーワードが含まれる場合
                            
                        # 通貨記号が含まれる場合は優先度を上げる
                        if '¥' in context[max(0, match.start() - 5):match.end() + 5] or '￥' in context[max(0, match.start() - 5):match.end() + 5]:
                            weight += 5  # 通貨記号が近くにある場合
                        
                        # 項目名が含まれる場合は優先度を下げる（おやつ、教材費など）
                        item_keywords = ['おやつ', '教材費', '活動費', '利用者負担額', '交通費']
                        for keyword in item_keywords:
                            if keyword in context and '合計' not in context:
                                weight -= 5  # 項目別金額の優先度を大幅に下げる
                                
                        # 郵便番号や受給者番号などの特定パターンを検出して優先度を大幅に下げる
                        exclude_patterns = [
                            r'〒\s*[0-9]{3}[-－]?[0-9]{4}',  # 郵便番号
                            r'[（(][0-9]{7,10}[）)]',        # 受給者番号
                            r'受給者番号[：:]?\s*[0-9]+',     # 受給者番号（別形式）
                            r'[0-9]{4}年[0-9]{1,2}月',       # 年月表記
                            r'[0-9]{1,2}月[0-9]{1,2}日'      # 月日表記
                        ]
                        
                        for pattern in exclude_patterns:
                            if re.search(pattern, context):
                                weight -= 8  # 郵便番号などのパターンがある場合は優先度を大幅に下げる
                        
                        # 金額の大きさも考慮（小さすぎる金額や端数のない綺麗すぎる金額は優先度調整）
                        if amt < 1000:
                            weight -= 2
                        
                        # 請求書の金額は通常端数がある（1000円ぴったりよりも1,080円のような金額が多い）
                        # 1000円単位の端数がない金額は、郵便番号などの可能性が高いので優先度を下げる
                        if amt >= 1000 and amt % 1000 == 0 and '合計' not in context[max(0, match.start() - 20):match.end() + 20]:
                            weight -= 1
                        
                        # 「円」が含まれる場合は優先度を上げる
                        if '円' in context[match.end():match.end()+5]:
                            weight += 1
                        
                        # 結果を追加
                        found_amounts.append((weight, amt, context))
                        print(f"金額候補: {amt}円 (優先度: {weight}, パターン: {priority+1})")
                        print(f"  コンテキスト: '{context}'")
                except ValueError:
                    continue
    
    if found_amounts:
        # 優先度でソート（降順）
        found_amounts.sort(key=lambda x: (-x[0], -x[1]))  # 優先度が同じなら金額の大きい方
        
        logger.info(f"抽出された全金額: {[(amt, weight) for weight, amt, _ in found_amounts[:5]]}")
        logger.info(f"最適な金額: {found_amounts[0][1]}円 (優先度: {found_amounts[0][0]})")
        
        # 代替候補も記録（デバッグ用）
        if len(found_amounts) > 1:
            logger.info(f"代替金額候補: {[(amt, weight) for weight, amt, _ in found_amounts[1:3]]}")
        
        # 最も優先度の高い金額を返す
        return found_amounts[0][1]
    
    logger.warning("有効な金額が見つかりませんでした")
    return None

def extract_amount_and_customer(text: str, ocr_data=None) -> ExtractionResult:
    """
    PDFから抽出したテキストから金額と顧客名を抽出する
    複数の抽出戦略を使用して最適な結果を得る
    """
    # 空文字列やNoneの場合は早期リターン
    if not text:
        return ExtractionResult(None, None)
        
    # テキストを正規化して読み取り可能な部分を抽出
    readable_content = extract_readable_content(text)
    normalized_text = readable_content["text"]
    
    # 正規化されたテキストがない場合は元のテキストを使用
    if not normalized_text:
        normalized_text = text
        
    # テキストの正規化（文字化け対策）
    normalized_text = normalize_text(normalized_text)
    
    # 正規化後もテキストが空の場合
    if not normalized_text or normalized_text.strip() == '':
        # 文字化けテキストから読める部分を抽出
        readable_content = extract_readable_content(text)
        if readable_content["readable_ratio"] < 0.3:  # 30%未満しか読めない場合
            logger.warning(f"テキストの可読率が低すぎます: {readable_content['readable_ratio']:.2f}")
            return ExtractionResult(customer=None, amount=None)
        normalized_text = readable_content["text"]

    # 金額の抽出（extract_invoice_amountを使用）
    amount_result, _ = extract_invoice_amount(normalized_text)
    amount = amount_result
    
    # 金額が見つからない場合は従来の方法を試す
    if amount is None:
        amount = extract_amount_only(normalized_text)
    
    # 顧客名の抽出
    customer = extract_customer(normalized_text)
    
    # 追加情報を含む結果を返す
    context = {
        "normalized": True,
        "original_line": "",
        "amount_extraction_method": "improved_algorithm" if amount_result else "legacy"
    }
    
    return ExtractionResult(customer=customer, amount=amount, context=context) if amount is not None else None

def extract_customer(text: str) -> Optional[str]:
    """
    PDFテキストから顧客名（宛先）を抽出する特化関数
    左上に書かれているフルネームを優先的に抽出し、「様」を付ける
    """
    # テキストが空の場合は None を返す
    if not text:
        return None
    
    # デバッグ情報を追加
    print(f"\n===== 顧客名抽出処理開始 =====\n")
    print(f"元のテキスト長: {len(text)} 文字")
        
    # 文字化けしているテキストから読みやすい部分を抽出
    readable_data = extract_readable_content(text)
    if readable_data["readable_ratio"] < 0.5:  # 読める文字が50%未満の場合
        # 読み取り可能な部分だけを使用
        text = readable_data["text"]
        print(f"読み取り可能な部分のみ使用: {len(text)} 文字")
    else:
        # 読み取り可能な割合が高い場合は正規化だけ行う
        text = normalize_text(text)
        print(f"正規化したテキスト: {len(text)} 文字")
    
    # 金額関連の用語リスト - 顧客名として無効な用語
    invalid_customer_terms = [
        '合計', '小計', '総額', '総額計', '金額', '請求額', 
        '請求金額', '請求合計', '小計額', '税込', '税込み',
        '税抜', '税抜き', '消費税', '消費税等', '合計額',
        '合計金額', '小計金額', '税込合計', '税抜合計',
        '合計欄', '小計欄', '金額欄', '請求欄', '合計額欄',
        '小計額欄', '総額欄', '総額額', '合計額金額',
        '合計金', '小計金', '総額金', '請求金', '請求書',
        '領収書', '領収書合計', '領収書金額', '領収書額',
        '請求書合計', '請求書金額', '請求書額', '小計欄金額',
        '御請求額', '御請求金額', '御合計', '御合計額'
    ]
    
    # 「合計」を含む行を完全に除外するための前処理
    filtered_text = "\n".join([line for line in text.split('\n') if '合計' not in line])
    print(f"「合計」を含む行を除外したテキスト: {len(filtered_text)} 文字")
    
    # 顧客名を抽出するための候補リスト
    customer_candidates = []
    
    # 「客様」「顧客」「宛名」などのキーワードの後に続く名前を抽出
    customer_field_patterns = [
        r'(?:お客様|顧客|お名前|氏名|宛名)[\s:：]*([^\n\d\s]{2,15})(?:様)?',
        r'(?:宛先|請求先)[\s:：]*([^\n\d\s]{2,15})(?:様)?',
    ]
    
    for pattern in customer_field_patterns:
        matches = re.finditer(pattern, filtered_text)
        for match in matches:
            name = match.group(1).strip()
            if is_valid_customer_name(name, invalid_customer_terms):
                context = filtered_text[max(0, match.start() - 20):min(len(filtered_text), match.end() + 20)]
                print(f"顧客フィールドから抽出: '{name}' (コンテキスト: '{context}')")
                customer_candidates.append((3, name))  # 優先度3（高）
    
    # 「様」が付く名前を抽出
    sama_pattern = r'([^\s\d]{2,15})様'
    for match in re.finditer(sama_pattern, filtered_text):
        name = match.group(1).strip()
        if is_valid_customer_name(name, invalid_customer_terms):
            context = filtered_text[max(0, match.start() - 20):min(len(filtered_text), match.end() + 20)]
            print(f"「様」付きから抽出: '{name}' (コンテキスト: '{context}')")
            customer_candidates.append((2, name))  # 優先度2（中）
    
    # 文書の最初の20行から日本語名を抽出
    lines = filtered_text.split('\n')[:20]  # 最初の20行のみ
    for i, line in enumerate(lines):
        # 行の内容をデバッグ表示
        print(f"行{i+1}: {line}")
        
        # 金額関連の用語を含む行はスキップ
        if any(term in line for term in invalid_customer_terms):
            print(f"  → 金額関連の用語を含む行なのでスキップ: {line}")
            continue
        
        # 日本語名のパターン（漢字・ひらがな・カタカナの連続）
        japanese_name_pattern = r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{2,15})'
        for match in re.finditer(japanese_name_pattern, line):
            name = match.group(1).strip()
            if is_valid_customer_name(name, invalid_customer_terms):
                print(f"日本語名から抽出: '{name}' (行{i+1})")
                customer_candidates.append((1, name))  # 優先度1（低）
    
    # 候補がない場合はNoneを返す
    if not customer_candidates:
        print("有効な顧客名が見つかりませんでした")
        return None
    
    # 優先度順にソート
    customer_candidates.sort(reverse=True)
    best_candidate = customer_candidates[0][1]
    
    # 「様」が含まれていない場合は追加
    if "様" not in best_candidate:
        best_candidate += "様"
    
    print(f"\n最終的な顧客名: {best_candidate}\n")
    return best_candidate

    # 左上から顧客名を抽出
    for i, line in enumerate(lines[:20]):
        # 行の内容をデバッグ表示
        print(f"\u884c{i+1}: {line}")

        # まず、この行が金額関連の用語を含むかチェック
        contains_invalid_term = False
        for term in invalid_customer_terms:
            if term in line:
                print(f"  → 金額関連の用語 '{term}' を含む行なのでスキップ")
                contains_invalid_term = True
                break

        if contains_invalid_term:
            continue

        # サンプル請求書形式のパターンをチェック
        sample_pattern = r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+\s*[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+)\s*(?:\(\s*[^\)]+\))?\s*様'
        name_match = re.search(sample_pattern, line, re.IGNORECASE)
        if name_match:
            customer = name_match.group(1).strip()

            # 顧客名の有効性チェック
            if is_valid_customer_name(customer, invalid_customer_terms):
                print(f"\u2705 対象請求書形式から顧客名抽出成功({i+1}行目): {customer}様")
                return f"{customer}様"
            else:
                print(f"\u274c 無効な顧客名をスキップ: {customer}")
                continue

        # その他のパターンもチェック
        for j, pattern in enumerate(name_patterns):
            name_match = re.search(pattern, line, re.IGNORECASE)
            if name_match:
                customer = name_match.group(1).strip()
                # 文字列整形
                customer = customer.replace('\n', '').replace('\r', '')

                # 「請求」という文字を除去
                customer = customer.replace('請求', '')

                # 顧客名の有効性チェック
                if is_valid_customer_name(customer, invalid_customer_terms):
                    print(f"\u2705 左上部分({i+1}行目)から顧客名抽出: {customer} (パターン{j+1})")

                    # 「様」が含まれていない場合は追加
                    if "様" not in customer:
                        customer += "様"

                    return customer
    
    # 左上から抽出できなかった場合は、重要セクションをチェック
    for section in important_sections:
        for pattern in name_patterns:
            name_match = re.search(pattern, section, re.IGNORECASE | re.MULTILINE)
            if name_match:
                customer = name_match.group(1).strip()
                # 文字列整形
                customer = customer.replace('\n', '').replace('\r', '')
                
                # 「請求」という文字を除去
                customer = customer.replace('請求', '')
                
                # 顧客名の有効性チェック
                if is_valid_customer_name(customer, invalid_customer_terms):
                    print(f"重要セクションから顧客名抽出: {customer}")
                    
                    # 「様」が含まれていない場合は追加
                    if "様" not in customer:
                        customer += "様"
                    
                    return customer
    
    # 通常のテキストから抽出
    found_names = []
    
    for pattern in name_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            try:
                # 文字列整形
                name = match.group(1).strip().replace('\n', '').replace('\r', '')
                
                # 無効な文字を除去、最低長もチェック
                if len(name) > 1 and any(c.isalpha() for c in name):
                    context = text[max(0, match.start() - 30):min(len(text), match.end() + 30)]
                    weight = 1
                    
                    # 重要度の計算
                    for keyword in ["請求先", "客様名", "顧客名", "氏名"]:
                        if keyword in context:
                            weight += 2
                            
                    # 「様」が含まれている場合は重要度を上げる
                    if "様" in name or match.group(0).endswith("様"):
                        weight += 3
                    
                    found_names.append((name, weight, context))
            except IndexError:
                continue
    
    # 重要度に基づいて顧客名をソート
    found_names.sort(key=lambda x: -x[1])
    
    if found_names:
        customer = found_names[0][0]
        print(f"最終的な顧客名抽出結果: {customer} (重要度: {found_names[0][1]})")
        
        # 「様」が含まれていない場合は追加
        if "様" not in customer:
            customer += "様"
        
        # 候補名前を表示
        if len(found_names) > 1:
            print("他の候補名前:")
            for i, (name, weight, _) in enumerate(found_names[1:3]):
                print(f"  {i+1}. {name} (重要度: {weight})")
                
        return customer
    
    return None
