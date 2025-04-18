import re
from typing import Tuple, Optional

def extract_amount_only(text: str) -> Optional[int]:
    """
    PDFテキストから金額のみを抽出する関数
    """
    # 金額抽出のパターン
    amount_patterns = [
        # 表の「合計」行にある金額パターン
        r'\b合\s*計\b[^\n]*?([0-9,.]+)(?:\s*円|\s*$)',
        
        # 金額欄のパターン
        r'金額[^\n]*?\s*[¥\u00a5]\s*([0-9,.]+)\s*[-\u2010-\u2015]',
        
        # サンプル請求書形式の金額パターン
        r'[¥\u00a5]\s*([0-9,.]+)\s*[-\u2010-\u2015]',
        
        # 単純な金額パターン
        r'([0-9,.]+)\s*円'
    ]
    
    # 配列にパターンマッチ結果を保存
    found_amounts = []
    
    # テキスト全体を探索
    for pattern in amount_patterns:
        matches = re.finditer(pattern, text, re.MULTILINE)
        for match in matches:
            try:
                # カンマや空白を除去して整数変換
                amount_str = match.group(1).replace(',', '').replace(' ', '')
                amt = int(amount_str)
                if 100 <= amt < 1000000:  # 妥当な金額範囲のみ取得
                    context = text[max(0, match.start() - 20):min(len(text), match.end() + 20)]
                    found_amounts.append((amt, context))
            except ValueError:
                continue
    
    if found_amounts:
        print(f"抽出された全金額: {[amt for amt, _ in found_amounts]}")
        # 最も可能性の高い金額を選択
        # 複数候補がある場合は最大の金額を選択
        return max([amt for amt, _ in found_amounts])
    return None

def extract_amount_and_customer(text: str) -> Tuple[Optional[int], Optional[str]]:
    """
    PDFテキストから金額（例: 1000, 1,000, 1000円）と顧客名（例: 名前: 佐藤太郎, 佐藤太郎様）を抽出
    請求書のレイアウトを考慮し、左上の宣先（顧客名）と右側の請求者を区別する
    """
    # デバッグ出力
    print(f"抽出対象テキスト（一部）: {text[:200]}...")
    print(f"テキスト全体の長さ: {len(text)}文字")
    
    # テキストを行ごとに分割して請求書の構造を分析
    lines = text.split('\n')
    
    # 1. デバッグ全行表示
    for i, line in enumerate(lines[:30]):
        if line.strip():  # 空行でない場合のみ
            print(f"行{i+1}: {line}")
    
    # 2. 先にサンプル請求書の名前パターン（山口 大輝（山口 大輝）様）を直接探す
    print("\n*** 顧客名パターンマッチング開始 ***")
    
    # 最初に純テキストで山口 大輝のような名前を探す
    raw_name_pattern = r'(\w{1,2}\s*\w{1,3})'
    raw_matches = re.finditer(raw_name_pattern, text[:500], re.MULTILINE)
    for match in raw_matches:
        name = match.group(1).strip()
        if re.match(r'[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+\s+[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+', name):
            print(f"\u2605 生の全角文字名前パターン検出: '{name}'")
            # これが実際に名前かどうか確認するロジックを追加
            context = text[max(0, match.start() - 30):min(len(text), match.end() + 30)]
            print(f"  コンテキスト: '{context}'")
            
            # 前後のコンテキストから顧客名である可能性を確認
            if "様" in context or "宣" in context[:20] or "宣先" in context[:20]:
                print(f"  → 顧客名である可能性が高いです")
                amount = extract_amount_only(text)
                return amount, f"{name}様"
    
    # サンプル請求書の形式に隣接するパターンを直接チェック
    sample_patterns = [
        # 山口 大輝（山口 大輝）様 的なパターン
        r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{1,2}\s*[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{1,3})\s*(?:\([^)]+\))?\s*様',
        
        # 姓名の間が空白もしくはなしのパターン
        r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{1,2}[ \t]*[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{1,3})\s*様',
        
        # より柔軟なパターン（姓名の間の空白が必要ない）
        r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{1,2}[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{1,3})\s*様',
        
        # 漢字とカタカナの組み合わせにも対応
        r'([\u4e00-\u9fa5\u3040-\u309f]+[ \t]*[\u30a0-\u30ff]+|[\u30a0-\u30ff]+[ \t]*[\u4e00-\u9fa5\u3040-\u309f]+)\s*様'
    ]
    
    # 全テキストに対してサンプルパターンを適用
    for pattern in sample_patterns:
        matches = re.finditer(pattern, text, re.MULTILINE)
        for match in matches:
            customer_name = match.group(1).strip()
            print(f"パターンマッチ: '{pattern}' → '{customer_name}様'")
            # 見つかった場合は即座にリターン
            amount = extract_amount_only(text)
            return amount, f"{customer_name}様"
    
    # 行ごとに左右のテキストを分割して分析
    left_side_text = []
    
    # 手動で左側の行を抜き出す
    for i, line in enumerate(lines[:20]):
        if i < 10:  # 最初の10行は特に重要
            left_side_text.append(line.strip())
        elif len(line.strip()) > 0 and len(line.strip()) < 30:  # 長すぎない行のみ抽出
            # 請求書の左側にある可能性が高いテキストを優先的に取得
            if not line.strip().startswith("↓"):  # 矢印など特殊文字で始まらない
                left_side_text.append(line.strip())
    
    # 左側テキストを結合
    left_text = '\n'.join(left_side_text)
    print(f"\n--- 左側テキスト(顧客対象) ---\n{left_text}")
    
    # 最初に[IMPORTANT]タグがついた重要行を優先的にチェック
    important_sections = re.findall(r'(.*\[IMPORTANT\].*)', text)
    print(f"発見された重要セクション: {len(important_sections)}個")
    for section in important_sections:
        print(f"\u91cd要セクション: {section}")
    
    # 金額抽出の正規表現パターンをさらに強化
    amount_patterns = [
        # 請求書でよく使われるキーワードの直後に金額があるパターン
        r'(?:請求金額|合計金額|御請求額|お支払い金額|合計|金額|総額|氏名)\s*[:：]?\s*(?:¥|￥)?\s*([0-9,.]+)(?:\s*円|\s*$)',
        
        # 表の「合計」行にある金額のパターン
        r'\b合\s*計\b[^\n]*?([0-9,.]+)(?:\s*円|\s*$)',
        
        # 金額表記の単純パターン
        r'(?:¥|￥)\s*([0-9,.]+)(?:\s*円|\s*$)',
        r'([0-9,.]+)\s*円',
        
        # 特殊な表記に対応（円表記がない場合など）
        r'(?:[金支請])(?:[\s:：]*)(\d[0-9,.\s]+)(?:\s*$|\s+[^0-9])',
        
        # 金額のみの行（レイアウトで金額が単独行にある場合）
        r'^\s*([0-9,.]+)\s*円\s*$'
    ]
    
    # 重要セクションから優先的に抽出を試みる
    amount = None
    
    # 重要セクションから先に抽出を試みる
    for section in important_sections:
        for pattern in amount_patterns:
            amount_match = re.search(pattern, section, re.IGNORECASE | re.MULTILINE)
            if amount_match:
                try:
                    # 数字以外の文字を削除して整数に変換
                    amount_str = amount_match.group(1).replace(',', '').replace('.', '').replace(' ', '').strip()
                    amount = int(amount_str)
                    print(f"重要セクションからの金額抽出成功 - パターン: {pattern}")
                    print(f"抽出された金額: {amount}円")
                    return amount, extract_customer(text)  # 重要セクションから抽出できた場合は信頼性が高いのですぐに返す
                except ValueError:
                    continue
    
    # テキスト全体から金額を抽出
    found_amounts = []
    
    for pattern in amount_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            try:
                amount_str = match.group(1).replace(',', '').replace('.', '').replace(' ', '').strip()
                amt = int(amount_str)
                # 合理的な金額のみを考慮 (100円以上100万円未満を想定)
                if 100 <= amt < 1000000:
                    context = text[max(0, match.start() - 30):min(len(text), match.end() + 30)]
                    weight = 1
                    
                    # 優先度を計算 (「合計」や「請求金額」などの重要キーワードが含まれているか)
                    for keyword in ["請求金額", "合計金額", "御請求額", "お支払い金額", "合計", "総額"]:
                        if keyword in context:
                            weight += 2
                    
                    found_amounts.append((amt, weight, context))
            except ValueError:
                continue
    
    # 重要度（重み）に基づいて金額をソート
    found_amounts.sort(key=lambda x: (-x[1], -x[0]))  # 重要度が高く、かつ金額が大きい順
    
    if found_amounts:
        amount = found_amounts[0][0]  # 最も可能性の高い金額を選択
        print(f"最終的な金額抽出結果: {amount}円 (重要度: {found_amounts[0][1]})")
        print(f"金額のコンテキスト: {found_amounts[0][2]}")
        
        # 候補金額を表示
        if len(found_amounts) > 1:
            print("他の候補金額:")
            for i, (amt, weight, context) in enumerate(found_amounts[1:5]):
                print(f"  {i+1}. {amt}円 (重要度: {weight})")
    
    # 顧客名は別関数で抽出
    customer = extract_customer(text)
    
    return amount, customer

def extract_customer(text: str) -> Optional[str]:
    """
    PDFテキストから顧客名（宛先）を抽出する特化関数
    左上に書かれているフルネームを優先的に抽出し、「様」を付ける
    請求書の左側にある情報から宛先を抽出し、右側の請求者情報と区別する
    """
    # テキストを行ごとに分割して左右の情報を区別
    lines = text.split('\n')
    left_side_text = []
    
    # 請求書の左側部分のみを抽出（顧客情報を含む）
    for line in lines[:20]:  # 最初の20行に限定
        line = line.strip()
        if not line:  # 空行はスキップ
            continue
            
        # 簡易的な判定: 行の前半分を左側として抽出
        mid_point = len(line) // 2
        if len(line) > 10:  # 十分な長さがある行のみ対象
            left_side_text.append(line[:mid_point].strip())
        else:
            # 短い行は全体を左側に含める
            left_side_text.append(line)
    
    # 左側テキストを結合
    left_text = '\n'.join(left_side_text)
    print(f"PDF左上部分（顧客名抽出用）: {left_text[:200]}...")
    
    # 重要セクションから顧客名を優先的に抽出
    important_sections = re.findall(r'(.*\[IMPORTANT\].*)', text)
    
    # 顧客名抽出のより詳細なパターン
    # サンプル請求書の形式に合わせてパターン追加
    name_patterns = [
        # 「姓名 (姓名) 様」形式 - サンプル請求書で確認された形式
        r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+\s*[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+)\s*(?:\(\s*[^\)]+\))?\s*様',
        
        # 左上にある可能性が高いフルネームのパターン
        r'^\s*([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{1,10}\s*[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{1,10})\s*(?:様)?\s*$',  # フルネーム(姓名)
        
        # 行の先頭にある名前パターン
        r'^\s*([^・･“”メ■→\d\(\)\[\]\{\}]{2,20})\s*(?:様)?\s*$',
        
        # 「様」が付くパターン
        r'([^\s]{2,20})\s*様',
        
        # 住所の直前にある可能性が高い名前
        r'([^・･“”メ■→\d\n\(\)\[\]\{\}\s]{2,15})(?:様)?(?:\s+御中|御中|\s*、\s*ご住所|ご住所)',
        
        # 請求先や顧客名を示すフィールドの後に客名が来るパターン
        r'(?:請求先|客様名|顧客名|氏名|名称|宛名|\b宛\b)[^\n:]*[:|：|\s]\s*([^\n\d]{2,30}?)(?:\s|$|様)'
    ]
    
    # 左上部分の各行を調査
    for i, line in enumerate(left_side_text):
        # サンプル請求書形式に合わせて優先的にチェックするパターン
        # 「姓名 (姓名) 様」形式を優先
        sample_pattern = r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+\s*[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+)\s*(?:\(\s*[^\)]+\))?\s*様'
        name_match = re.search(sample_pattern, line, re.IGNORECASE)
        if name_match:
            customer = name_match.group(1).strip()
            print(f"対象請求書形式から顧客名抽出成功({i+1}行目): {customer}様")
            return f"{customer}様"
        
        # その他のパターンもチェック
        for j, pattern in enumerate(name_patterns):
            name_match = re.search(pattern, line, re.IGNORECASE)
            if name_match:
                customer = name_match.group(1).strip()
                # 文字列整形
                customer = customer.replace('\n', '').replace('\r', '')
                
                # 無効な文字を除去、最低長もチェック
                if len(customer) > 2 and any(c.isalpha() for c in customer):
                    print(f"左上部分({i+1}行目)から顧客名抽出: {customer} (パターン{j+1})")
                    
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
                
                # 無効な文字を除去
                if len(customer) > 0 and any(c.isalpha() for c in customer):
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
