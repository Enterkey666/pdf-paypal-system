#!/bin/bash

# PDF処理 & PayPal決済リンク発行システム 自動起動スクリプト（macOS用）
echo "==================================================="
echo " PDF処理 & PayPal決済リンク発行システム セットアップ"
echo "==================================================="
echo ""

# 現在のディレクトリを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 初回起動かどうかを確認
if [ ! -f ".initialized_mac" ]; then
    echo "初めての起動を検出しました。初期セットアップを行います..."
    echo ""
    
    # Pythonが存在するか確認
    if ! command -v python3 &> /dev/null; then
        echo "エラー: Python3が見つかりません。"
        echo ""
        echo "Pythonをインストールする必要があります。"
        echo "Homebrew経由でインストールするには以下のコマンドを実行してください："
        echo "brew install python3"
        echo ""
        echo "または公式サイトからダウンロード："
        echo "https://www.python.org/downloads/"
        echo ""
        echo "Pythonをインストールした後、このスクリプトを再度実行してください。"
        read -p "続行するには何かキーを押してください..."
        exit 1
    fi
    
    # 必要なライブラリをインストール
    echo "必要なライブラリを確認しています..."
    if ! python3 -c "import flask" &> /dev/null; then
        echo "必要なライブラリをインストールしています..."
        echo "これには数分かかる場合があります。しばらくお待ちください..."
        echo ""
        pip3 install -r requirements.txt
        if [ $? -ne 0 ]; then
            echo "エラー: ライブラリのインストールに失敗しました。"
            echo "インターネット接続を確認し、再度試してください。"
            read -p "続行するには何かキーを押してください..."
            exit 1
        fi
        echo ""
        echo "ライブラリのインストールが完了しました！"
    fi
    
    # アプリケーションショートカットを作成
    echo "アプリケーションフォルダにショートカットを作成しますか？ (y/n)"
    read -p "> " create_shortcut
    if [[ $create_shortcut == "y" || $create_shortcut == "Y" ]]; then
        echo "ショートカットを作成しています..."
        
        # AppleScriptでアプリケーションを作成
        osascript > /dev/null 2>&1 <<EOF
        tell application "Finder"
            set desktopPath to path to desktop folder as string
            set appPath to desktopPath & "PDF処理システム.app"
            
            try
                do shell script "mkdir -p \"" & appPath & "/Contents/MacOS\""
                do shell script "echo '#!/bin/bash
cd \"$SCRIPT_DIR\"
python3 app.py' > \"" & appPath & "/Contents/MacOS/run_app\""
                do shell script "chmod +x \"" & appPath & "/Contents/MacOS/run_app\""
                
                do shell script "mkdir -p \"" & appPath & "/Contents/Resources\""
                do shell script "echo '<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
    <key>CFBundleExecutable</key>
    <string>run_app</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.pdf-paypal-system</string>
    <key>CFBundleName</key>
    <string>PDF処理システム</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
</dict>
</plist>' > \"" & appPath & "/Contents/Info.plist\""
                
                display dialog "デスクトップにショートカットを作成しました。" buttons {"OK"} default button "OK"
            on error errMsg
                display dialog "ショートカット作成に失敗しました: " & errMsg buttons {"OK"} default button "OK"
            end try
        end tell
EOF
        
        if [ $? -eq 0 ]; then
            echo "デスクトップにショートカットを作成しました。"
        else
            echo "ショートカット作成に失敗しました。"
        fi
        echo ""
    fi
    
    # 初期化済みフラグを作成
    echo "1" > ".initialized_mac"
fi

# アプリケーションを起動
echo "アプリケーションを起動しています..."
echo "ブラウザが自動的に開きます。"
echo ""
echo "※ アプリケーションを終了するには、このターミナルウィンドウを閉じるか、Ctrl+Cを押してください。"
echo ""

# ブラウザを開く
open "http://localhost:8080" &

# アプリケーションを起動
python3 app.py
