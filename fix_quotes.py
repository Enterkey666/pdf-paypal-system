"""
app.pyファイルの未終了の三重引用符を修正するスクリプト
"""

def fix_unterminated_quotes():
    input_file = 'app.py'
    output_file = 'app.py.fixed'
    backup_file = 'app.py.backup'
    
    # バックアップを作成
    try:
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as src, open(backup_file, 'w', encoding='utf-8') as dst:
            content = src.read()
            dst.write(content)
        print(f"バックアップを作成しました: {backup_file}")
    except Exception as e:
        print(f"バックアップ作成エラー: {str(e)}")
        return False
    
    # 行ごとに読み込み、未終了の三重引用符を修正
    try:
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as src:
            lines = src.readlines()
        
        # 三重引用符の状態を追跡
        in_triple_quotes = False
        fixed_lines = []
        
        for i, line in enumerate(lines):
            # 行内の三重引用符の数をカウント
            triple_quotes_count = line.count('"""')
            
            # 行内で三重引用符の開始と終了が両方ある場合
            if triple_quotes_count == 2:
                fixed_lines.append(line)
                continue
            
            # 三重引用符の開始
            if triple_quotes_count == 1 and not in_triple_quotes:
                in_triple_quotes = True
                # 三重引用符をコメントに変換
                fixed_line = line.replace('"""', '# ')
                fixed_lines.append(fixed_line)
            
            # 三重引用符の終了
            elif triple_quotes_count == 1 and in_triple_quotes:
                in_triple_quotes = False
                # 三重引用符を削除
                fixed_line = line.replace('"""', '')
                fixed_lines.append(fixed_line)
            
            # 三重引用符の中
            elif in_triple_quotes:
                # 各行をコメントに変換
                fixed_line = '# ' + line
                fixed_lines.append(fixed_line)
            
            # 通常の行
            else:
                fixed_lines.append(line)
        
        # 最後まで三重引用符が閉じられていない場合
        if in_triple_quotes:
            print("警告: ファイルの最後まで三重引用符が閉じられていません。すべてコメントに変換しました。")
        
        # 修正した内容を書き込む
        with open(output_file, 'w', encoding='utf-8') as dst:
            dst.writelines(fixed_lines)
        
        print(f"修正したファイルを作成しました: {output_file}")
        return True
    
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")
        return False

if __name__ == "__main__":
    if fix_unterminated_quotes():
        print("処理が完了しました。")
    else:
        print("処理に失敗しました。")
