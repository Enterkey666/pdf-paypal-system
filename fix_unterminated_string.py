import re
import sys

def fix_unterminated_string(file_path):
    """
    未終了の三重引用符文字列を修正するスクリプト
    """
    try:
        # ファイルを読み込む
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 開始の三重引用符と終了の三重引用符の数をカウント
        triple_quotes_start = content.count('"""')
        
        # 奇数の場合は未終了の三重引用符が存在する
        if triple_quotes_start % 2 != 0:
            print(f"未終了の三重引用符が見つかりました。")
            
            # 行ごとに処理して問題のある行を特定
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if '"""' in line:
                    print(f"行 {i+1}: {line}")
            
            # バックアップを作成
            backup_path = file_path + '.bak'
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"バックアップを作成しました: {backup_path}")
            
            # 未終了の三重引用符を修正（docstringをコメントに変換）
            modified_content = re.sub(r'"""([^"]*)$', r'# \1', content, flags=re.DOTALL)
            
            # 修正したコンテンツを書き込む
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            print("ファイルを修正しました。")
        else:
            print("未終了の三重引用符は見つかりませんでした。")
    
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python fix_unterminated_string.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    if fix_unterminated_string(file_path):
        print("処理が完了しました。")
    else:
        print("処理に失敗しました。")
        sys.exit(1)
