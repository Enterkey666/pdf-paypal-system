import re
import os
import json
import logging
import hashlib
import datetime
from typing import Optional, List, Tuple, Dict
from text_normalizer import normalize_text, extract_readable_content

# ロガーの設定
logger = logging.getLogger(__name__)

# キャッシュ用の辞書（キー：ファイル名またはテキストハッシュ、値：{name: 顧客名, timestamp: タイムスタンプ}）
_customer_cache = {}

def clear_cache():
    """
    キャッシュをクリアする
    """
    global _customer_cache
    _customer_cache = {}
    logger.info("顧客名キャッシュをクリアしました")
    

def get_alternatives(key: str) -> List[Dict]:
    """
    指定されたキーに対する代替候補を取得する
    
    Args:
        key: キャッシュキー（ファイル名またはテキストハッシュ）
        
    Returns:
        代替候補のリスト、キーが存在しない場合は空リスト
    """
    if key in _customer_cache:
        cache_entry = _customer_cache[key]
        if isinstance(cache_entry, dict) and 'alternatives' in cache_entry:
            return cache_entry['alternatives']
    return []

def sanitize_for_log(text: str) -> str:
    """
    ログ出力用に文字列をサニタイズする
    
    Args:
        text: サニタイズするテキスト
        
    Returns:
        サニタイズされたテキスト
    """
    if not text:
        return ""
    try:
        # 問題のある文字を安全な文字に置換
        return text.encode('cp932', errors='replace').decode('cp932')
    except:
        # エンコードに失敗した場合はASCII文字のみ残す
        return ''.join(c if ord(c) < 128 else '?' for c in text)

def mask_personal_info(name: str) -> str:
    """
    個人情報を保護するためのマスキング処理
    
    Args:
        name: マスキングする顧客名
        
    Returns:
        マスキングされた顧客名
    """
    # 企業名（株式会社など）を含む場合はマスキングしない
    if any(term in name for term in ['株式会社', '有限会社', '合同会社', '社団法人', '財団法人', '協会', '組合', 'Co.', 'Ltd.', 'Inc.', 'Corp.']):
        return name
    
    # 「様」が含まれる場合は特別処理
    if '様' in name:
        # 「様」の前の部分を取得
        name_part = name.split('様')[0].strip()
        # 姓名の区切りを検出
        parts = name_part.split()
        if len(parts) > 1:
            # 姓だけ残して名をマスキング
            return parts[0] + ' ' + '*' * len(''.join(parts[1:])) + ' 様'
        return name_part + ' 様'
        
    # 個人名と思われる場合は姓だけ残してマスキング
    parts = name.split()
    if len(parts) > 1:
        # 姓だけ残して名をマスキング
        return parts[0] + ' ' + '*' * len(''.join(parts[1:]))
    
    return name

def is_valid_customer_name(name: str, invalid_terms: List[str], allow_alphanumeric: bool = False) -> bool:
    """
    顧客名が有効かどうかを判定する
    
    Args:
        name: 判定する顧客名
        invalid_terms: 無効な用語のリスト
        allow_alphanumeric: 英数字のみの名前を許可するかどうか
        
    Returns:
        有効な場合はTrue、無効な場合はFalse
    """
    # 空文字列や1文字の名前は無効
    if not name or len(name) < 2:
        logger.debug(f"名前が短すぎます: '{name}'")
        return False
        
    # 数字のみの名前は無効
    if name.isdigit():
        logger.debug(f"数字のみの名前は無効です: '{name}'")
        return False
        
    # 無効な用語を含む名前は無効
    for term in invalid_terms:
        if term in name:
            logger.debug(f"無効な用語 '{term}' を含む名前です: '{name}'")
            return False
    
    # ファイル名として使われる可能性が高い英数字のみの名前は、
    # allow_alphanumericがFalseの場合のみ無効とする
    if not allow_alphanumeric and re.match(r'^[A-Za-z0-9_]+$', name):
        logger.debug(f"ファイル名の可能性が高い名前ですが、許可されません: '{name}'")
        return False
            
    return True

def extract_customer(text: str, filename: str = None, force_refresh: bool = False) -> Optional[str]:
    """
    PDFテキストから顧客名（宛先）を抽出する特化関数
    左上に書かれているフルネームを優先的に抽出する
    ファイル名からも顧客名候補を抽出する
    「〜様」パターンを優先的に抽出する
    
    Args:
        text: 抽出元のテキスト
        filename: PDFファイル名（オプション）
        force_refresh: キャッシュを無視して強制的に再抽出する
        
    Returns:
        抽出された顧客名、見つからない場合はNone
    """
    # テキストが空の場合は None を返す
    if not text:
        return None
    
    # キャッシュチェック（ファイル名をキーとして使用）
    cache_key = filename if filename else hashlib.md5(text[:1000].encode()).hexdigest()
    if not force_refresh and cache_key in _customer_cache:
        cache_entry = _customer_cache[cache_key]
        # キャッシュエントリが辞書形式かどうかを確認
        if isinstance(cache_entry, dict) and 'name' in cache_entry:
            logger.info(f"キャッシュから顧客名を取得: {cache_entry['name']} (キャッシュ時間: {cache_entry['timestamp']})")
            return cache_entry['name']
        else:
            # 古い形式のキャッシュエントリの場合は、そのまま返す
            logger.info(f"キャッシュから顧客名を取得（旧形式）: {cache_entry}")
            return cache_entry
    
    # デバッグ情報
    logger.info(f"顧客名抽出処理開始 (テキスト長: {len(text)} 文字)")
        
    # 文字化けしているテキストから読みやすい部分を抽出
    readable_data = extract_readable_content(text)
    if readable_data["readable_ratio"] < 0.5:  # 読める文字が50%未満の場合
        # 読み取り可能な部分だけを使用
        text = readable_data["text"]
        logger.info(f"読み取り可能な部分のみ使用: {len(text)} 文字")
    else:
        # 読み取り可能な割合が高い場合は正規化だけ行う
        text = normalize_text(text)
        logger.info(f"正規化したテキスト: {len(text)} 文字")
    
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
        # YORUTOKOを除外リストから削除
    ]
    
    # 「合計」を含む行を除外するための前処理
    filtered_text = "\n".join([line for line in text.split('\n') if not any(term in line for term in ['合計', '小計', '総額', '金額'])])
    logger.info(f"「合計」などを含む行を除外したテキスト: {len(filtered_text)} 文字")
    
    # フィルタリング後のテキストが空または極端に短い場合は、元のテキストを使用
    if len(filtered_text) < 50:
        logger.warning(f"フィルタリング後のテキストが短すぎるため、元のテキストを使用します: {len(filtered_text)} 文字")
        filtered_text = text
    
    # 顧客名を抽出するための候補リスト
    candidates = []
    
    # 「客様」「顧客」「宛名」などのキーワードの後に続く名前を抽出
    customer_field_patterns = [
        r'(?:お客様|顧客|お名前|氏名|宛名)[\s:：]*([^\n\d]{2,30})(?:\s*様)?',
        r'(?:宛先|請求先)[\s:：]*([^\n\d]{2,30})(?:\s*様)?',
        r'(?:御中|様)[：:]\s*([^\n\d]{2,30})',
        r'〒[0-9\-]+[\s\r\n]+([^\n\d]{2,30})(?:\s*[（）\(\)\s].*)?(?:\s*様)',  # 郵便番号の後の名前
    ]
    
    for pattern in customer_field_patterns:
        matches = re.finditer(pattern, filtered_text)
        for match in matches:
            name = match.group(1).strip()
            if is_valid_customer_name(name, invalid_customer_terms):
                context = filtered_text[max(0, match.start() - 20):min(len(filtered_text), match.end() + 20)]
                logger.info(f"顧客フィールドから抽出: '{sanitize_for_log(name)}' (コンテキスト: '{sanitize_for_log(context)}')")
                candidates.append({'name': name, 'score': 5, 'source': 'テキスト'})  # 優先度5（最高）
    
    # 「様」が付く名前を抽出
    sama_pattern = r'([^\d]{2,30})\s*様'
    for match in re.finditer(sama_pattern, filtered_text):
        name = match.group(1).strip()
        # 括弧を含む名前の処理
        if '(' in name or '（' in name:
            # 括弧の前の部分を使用
            name = re.sub(r'[\(\uff08].*', '', name).strip()
        if is_valid_customer_name(name, invalid_customer_terms):
            context = filtered_text[max(0, match.start() - 20):min(len(filtered_text), match.end() + 20)]
            logger.info(f"「様」付きから抽出: '{sanitize_for_log(name)}' (コンテキスト: '{sanitize_for_log(context)}')")
            candidates.append({'name': name, 'score': 4, 'source': 'テキスト'})  # 優先度4（高）
    
    # 「御中」が付く名前を抽出
    onchu_pattern = r'([^\s\d]{2,15})御中'
    for match in re.finditer(onchu_pattern, filtered_text):
        name = match.group(1).strip()
        if is_valid_customer_name(name, invalid_customer_terms):
            context = filtered_text[max(0, match.start() - 20):min(len(filtered_text), match.end() + 20)]
            logger.info(f"「御中」付きから抽出: '{sanitize_for_log(name)}' (コンテキスト: '{sanitize_for_log(context)}')")
            candidates.append({'name': name, 'score': 3, 'source': 'テキスト'})  # 優先度3（中高）
    
    # 「〜様」パターンを抽出（最優先）
    # より柔軟な正規表現パターンを使用して、括弧や余分な空白を含む名前も抽出
    # 複数のパターンを試す
    sama_patterns = [
        # 標準的な「名前+様」パターン
        r'([^\d]{2,50})[\u3000\s]*様',
        # 改行を含む可能性があるパターン
        r'([^\d]{2,50})[\u3000\s\n]*様',
        # 括弧を含む可能性があるパターン
        r'([^\d]{2,30})[\s]*\([^)]*\)[\s]*様',
        # 特殊なケースのパターン
        r'([^\d]{1,20})[\s]+([^\d]{1,20})[\s]*\([^)]*\)[\s]*様'
    ]
    
    logger.info(f"「様」パターンの検索開始 - テキストの一部: {filtered_text[:100]}...")
    
    # すべてのパターンで検索
    sama_matches = []
    for i, pattern in enumerate(sama_patterns):
        matches = list(re.finditer(pattern, filtered_text))
        logger.info(f"パターン{i+1}の一致数: {len(matches)}")
        sama_matches.extend(matches)
    
    logger.info(f"「様」パターンの合計一致数: {len(sama_matches)}")
    
    for match in sama_matches:
        raw_name = match.group(1).strip()
        logger.info(f"「様」パターン生の抽出結果: '{sanitize_for_log(raw_name)}'")
        
        # 括弧を除去する処理
        name = re.sub(r'\s*\([^)]*\)\s*', ' ', raw_name).strip()
        # 日本語の括弧も除去
        name = re.sub(r'\s*（[^）]*）\s*', ' ', name).strip()
        # 連続する空白を1つにまとめる
        name = re.sub(r'[\u3000\s]+', ' ', name).strip()
        
        logger.info(f"「様」パターン前処理後: '{sanitize_for_log(name)}'")
        
        if is_valid_customer_name(name, invalid_customer_terms):
            context = filtered_text[max(0, match.start() - 20):min(len(filtered_text), match.end() + 20)]
            logger.info(f"「様」付きから抽出: '{sanitize_for_log(name)}' (コンテキスト: '{sanitize_for_log(context)}')")
            candidates.append({'name': name, 'score': 20, 'source': 'テキスト'})  # 優先度20（最高）
    
    # 文書の最初の20行から日本語名を抽出
    lines = filtered_text.split('\n')[:20]  # 最初の20行のみ
    for i, line in enumerate(lines):
        # 行の内容をデバッグ表示
        logger.debug(f"行{i+1}: {line}")
        
        # 金額関連の用語を含む行はスキップ
        if any(term in line for term in invalid_customer_terms):
            logger.debug(f"金額関連の用語を含む行なのでスキップ: {line}")
            continue
        
        # 日本語名のパターン（漢字・ひらがな・カタカナの連続）
        japanese_name_pattern = r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{2,15})'
        for match in re.finditer(japanese_name_pattern, line):
            name = match.group(1).strip()
            if is_valid_customer_name(name, invalid_customer_terms):
                logger.info(f"日本語名から抽出: '{name}' (行{i+1})")
                candidates.append({'name': name, 'score': 2, 'source': 'テキスト'})  # 優先度2（中）
                
    # 「〜様」パターンを検出（優先度を高く設定）
    sama_pattern = re.compile(r'([\w\s]{2,30})\s*様')
    sama_matches = list(sama_pattern.finditer(text[:2000]))  # 最初の2000文字を検索範囲に拡大
    
    logger.info(f"「様」パターンの合計一致数: {len(sama_matches)}")
    
    # 「〜様」パターンが見つかった場合
    if sama_matches:
        for match in sama_matches:
            raw_name = match.group(1).strip()
            logger.info(f"「様」パターン生の抽出結果: '{sanitize_for_log(raw_name)}'")
            
            # 括弧を除去する処理
            name = re.sub(r'\s*\([^)]*\)\s*', ' ', raw_name).strip()
            # 日本語の括弧も除去
            name = re.sub(r'\s*（[^）]*）\s*', ' ', name).strip()
            # 連続する空白を1つにまとめる
            name = re.sub(r'\s+', ' ', name).strip()
            
            if is_valid_customer_name(name, invalid_customer_terms):
                logger.info(f"「〜様」パターンから顧客名を抽出: {name}様")
                # 「様」パターンの優先度をさらに高く設定
                candidates.append({'name': f"{name}様", 'score': 15, 'source': 'sama_pattern'})  # 優先度15（最高）
                
    # 「御中」パターンも検出
    onchu_pattern = re.compile(r'([\w\s]{2,30}(?:株式会社|有限会社|合同会社|社団法人|財団法人))\s*御中')
    onchu_matches = list(onchu_pattern.finditer(text[:2000]))
    
    logger.info(f"「御中」パターンの合計一致数: {len(onchu_matches)}")
    
    # 「御中」パターンが見つかった場合
    if onchu_matches:
        for match in onchu_matches:
            raw_name = match.group(1).strip()
            logger.info(f"「御中」パターン生の抽出結果: '{sanitize_for_log(raw_name)}'")
            
            # 括弧を除去する処理
            name = re.sub(r'\s*\([^)]*\)\s*', ' ', raw_name).strip()
            # 日本語の括弧も除去
            name = re.sub(r'\s*（[^）]*）\s*', ' ', name).strip()
            # 連続する空白を1つにまとめる
            name = re.sub(r'\s+', ' ', name).strip()
            
            if is_valid_customer_name(name, invalid_customer_terms):
                logger.info(f"「御中」パターンから顧客名を抽出: {name}御中")
                candidates.append({'name': f"{name}御中", 'score': 14, 'source': 'onchu_pattern'})  # 優先度14（高）
    
    # テキストから有効な顧客名が抽出されたか確認
    valid_customer_from_text = None
    if candidates:
        # スコアでソートして最も高いスコアの候補を選択
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # デバッグ: すべての候補を表示
        logger.info(f"顧客名候補一覧 (合計: {len(candidates)}件):")
        for i, candidate in enumerate(candidates[:5]):  # 上位5件のみ表示
            logger.info(f"  候補{i+1}: '{candidate['name']}' (スコア: {candidate['score']}, 出典: {candidate['source']})")
        
        selected_candidate = candidates[0]
        customer_name = selected_candidate['name']
        
        # 個人情報保護のため、顧客名の一部のみをログに出力
        if customer_name and len(customer_name) > 2:
            masked_name = customer_name[0] + '*' * (len(customer_name) - 2) + customer_name[-1]
            logger.info(f"最終選択された顧客名: {masked_name} (スコア: {selected_candidate['score']}, 出典: {selected_candidate['source']})")
        else:
            logger.info(f"最終選択された顧客名: {customer_name} (スコア: {selected_candidate['score']}, 出典: {selected_candidate['source']})")
        
        return customer_name
    
    # 候補がない場合はファイル名から抽出を試みる
    if filename:
        logger.info(f"テキストから顧客名が見つからなかったため、ファイル名から抽出を試みます: {filename}")
        
        # ファイル名から顧客名を抽出するロジック
        # 特定のキーワードを含むファイル名の場合は設定から顧客名を取得
        if 'YORUTOKO' in filename or re.search(r'YORUTOKO_page\d*', filename) or any(keyword in filename for keyword in ['特別', 'special']):
            # 設定から顧客名を取得するか、デフォルト値を使用
            try:
                # まず暗号化された設定ファイルを探す
                from utils.crypto_util import CryptoUtil
                
                encrypted_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'customer_mapping.enc')
                config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'customer_mapping.json')
                
                customer_mapping = {}
                
                # 暗号化ファイルが存在する場合は復号化して使用
                if os.path.exists(encrypted_config_path):
                    try:
                        with open(encrypted_config_path, 'rb') as f:
                            encrypted_data = f.read()
                        customer_mapping = CryptoUtil.decrypt_data(encrypted_data)
                        logger.info("暗号化された顧客マッピング設定を使用します")
                    except Exception as decrypt_err:
                        logger.error(f"暗号化された顧客マッピング設定の復号化エラー: {decrypt_err}")
                        customer_mapping = {}
                # 通常の設定ファイルがある場合はそこから読み込む
                elif os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        customer_mapping = json.load(f)
                    logger.info("通常の顧客マッピング設定を使用します")
                
                # 顧客名を設定
                # ファイル名からの抽出は低い優先度で追加するのみ
                if 'YORUTOKO' in filename:
                    special_name = 'YORUTOKO'
                    logger.info(f"YORUTOKOキーワードから顧客名候補を追加: {special_name}")
                    # 優先度0（最低）で追加することで、PDFテキストからの抽出を確実に優先
                    candidates.append({'name': special_name, 'score': 0, 'source': 'filename'})
                else:
                    file_key = next((key for key in customer_mapping.keys() if key in filename), None)
                    if file_key:
                        special_name = customer_mapping.get(file_key)
                        logger.info(f"ファイル名キーワードから顧客名候補を追加")
                        candidates.append({'name': special_name, 'score': 1, 'source': 'filename'})  # 優先度1（低）
                    else:
                        special_name = customer_mapping.get('default', '夕床商事')
                        logger.info(f"デフォルトの顧客名候補を追加")
                        candidates.append({'name': special_name, 'score': 1, 'source': 'filename'})  # 優先度1（低）
            except Exception as e:
                logger.error(f"顧客名マッピング設定の読み込みエラー: {e}")
                special_name = '夕床商事'
                logger.info(f"エラー発生時のデフォルト顧客名候補を追加")
                candidates.append({'name': special_name, 'score': 1, 'source': 'filename'})  # 優先度1（低）
        else:
            # 通常のファイル名処理：アンダースコアやハイフンで区切られた部分を使用
            # 拡張子を除去
            base_filename = os.path.splitext(filename)[0]
            
            # アンダースコアやハイフンの前に「invoice」「receipt」などがある場合は、その前までを顧客名として使用
            invoice_pattern = r'(.+?)(?:_|-)(?:invoice|receipt|bill|payment|order)'
            invoice_match = re.search(invoice_pattern, base_filename, re.IGNORECASE)
            
            if invoice_match:
                potential_name = invoice_match.group(1).strip()
                logger.info(f"ファイル名から顧客名を抽出（パターンマッチ）: {potential_name}")
            else:
                # パターンに一致しない場合は、最初のアンダースコアまたはハイフンまでを顧客名として使用
                name_parts = re.split(r'[_\-]', base_filename, 1)
                potential_name = name_parts[0].strip()
                
                # 最初の部分が短すぎる場合は、アンダースコアで区切られた最初の2つの部分を使用
                if len(potential_name) < 3 and len(name_parts) > 1:
                    name_parts = re.split(r'_', base_filename, 2)
                    if len(name_parts) >= 2:
                        potential_name = f"{name_parts[0]}_{name_parts[1]}".strip()
                
                logger.info(f"ファイル名から顧客名を抽出: {potential_name}")
            
            # ファイル名が長すぎる場合は適切な長さに切り詰める
            if len(potential_name) > 20:
                potential_name = potential_name[:20]
            
            # ファイル名から抽出した名前は英数字のみでも許可する
            if potential_name and len(potential_name) >= 2 and is_valid_customer_name(potential_name, invalid_customer_terms, allow_alphanumeric=True):
                candidates.append({'name': potential_name, 'score': 1, 'source': 'filename'})  # 優先度1（低）に設定
    
    # 候補がない場合はデフォルト値を返す
    if not candidates:
        logger.warning("顧客名候補が見つかりませんでした")
        return None
    
    # スコアでソートして最高スコアの候補を選択
    candidates.sort(key=lambda x: x['score'], reverse=True)
    best_candidate = candidates[0]['name']
    logger.info(f"最適な顧客名候補: {best_candidate} (スコア: {candidates[0]['score']}, ソース: {candidates[0]['source']})")
    
    # 個人情報保護のためのマスキング処理
    masked_name = mask_personal_info(best_candidate)
    if masked_name != best_candidate:
        logger.info(f"個人情報保護のためマスキング処理を適用: {masked_name}")
        # マスキング処理後の名前を使用するかどうかの設定（現在はオリジナルを使用）
        # best_candidate = masked_name
    
    # 代替候補を保存（上位3つまで）
    alternatives = []
    for i in range(1, min(4, len(candidates))):
        alt_name = candidates[i]['name']
        alt_masked = mask_personal_info(alt_name)
        alternatives.append({
            'name': alt_name,
            'masked': alt_masked,
            'score': candidates[i]['score'],
            'source': candidates[i]['source']
        })
    
    # キャッシュに保存（新しい形式：辞書形式で保存）
    _customer_cache[cache_key] = {
        'name': best_candidate,
        'masked': masked_name,
        'alternatives': alternatives,
        'timestamp': datetime.datetime.now().isoformat()
    }
    logger.info(f"顧客名をキャッシュに保存しました: {best_candidate}")
    
    return best_candidate
