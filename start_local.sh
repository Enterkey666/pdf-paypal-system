#!/bin/bash

# PDF PayPal System - ローカル起動スクリプト

echo "🚀 PDF PayPal System ローカル開発環境を起動します"
echo "=================================================="

# 現在のディレクトリを確認
echo "📂 作業ディレクトリ: $(pwd)"

# Python仮想環境の確認・作成
if [ ! -d "venv" ]; then
    echo "🐍 Python仮想環境を作成中..."
    python3 -m venv venv
fi

# 仮想環境をアクティベート
echo "📦 仮想環境をアクティベート中..."
source venv/bin/activate

# 依存関係のインストール
echo "📚 依存関係をインストール中..."
pip install -r requirements.txt

# 設定ファイルの確認
if [ ! -f "config.json" ]; then
    echo "⚠️  config.json が見つかりません"
    echo "config.example.json をコピーして設定してください:"
    echo "cp config.example.json config.json"
    
    if [ -f "config.example.json" ]; then
        cp config.example.json config.json
        echo "✅ config.json を作成しました（config.example.jsonからコピー）"
    fi
fi

# ログディレクトリ作成
mkdir -p logs

# オプション選択
echo ""
echo "起動オプションを選択してください:"
echo "1) 従来版アプリ (app.py)"
echo "2) ローカル開発版 (local_app.py) - 推奨"
echo "3) Firebase Emulator"
echo ""
read -p "選択 [1-3]: " choice

case $choice in
    1)
        echo "🌐 従来版アプリを起動中..."
        echo "URL: http://localhost:5000"
        python app.py
        ;;
    2)
        echo "🛠️  ローカル開発版を起動中..."
        echo "URL: http://localhost:5000"
        echo "設定確認: http://localhost:5000/config"
        echo "ヘルスチェック: http://localhost:5000/health"
        python local_app.py
        ;;
    3)
        echo "🔥 Firebase Emulatorを起動中..."
        
        # Firebase CLIの確認
        if ! command -v firebase &> /dev/null; then
            echo "❌ Firebase CLI がインストールされていません"
            echo "インストール方法:"
            echo "npm install -g firebase-tools"
            exit 1
        fi
        
        echo "Firebase Emulator UI: http://localhost:4000"
        echo "Functions: http://localhost:5001"
        echo "Firestore: http://localhost:8080"
        echo "Storage: http://localhost:9199"
        echo "Hosting: http://localhost:5000"
        
        firebase emulators:start
        ;;
    *)
        echo "❌ 無効な選択です"
        exit 1
        ;;
esac