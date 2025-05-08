@echo off
chcp 65001 > nul
REM PDF処理 & PayPal決済リンク発行システム 自動起動ランチャー
title PDF処理 & PayPal決済リンク発行システム - 簡単起動ツール

echo ===================================================
echo  PDF処理 & PayPal決済リンク発行システム ランチャー
echo ===================================================
echo.
echo このツールはZIPファイルから展開後、簡単にアプリを起動するためのものです。
echo.

REM 現在のディレクトリを取得
cd /d "%~dp0"

REM アプリケーションのパスを設定
set APP_PATH=start_app.bat

REM 初回起動かどうかを確認
if not exist ".initialized" (
    echo 初めての起動を検出しました。初期セットアップを行います...
    echo.
    
    REM 管理者権限の確認
    net session >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo 警告: 管理者権限がありません。
        echo 一部の機能が制限される可能性があります。
        echo.
        echo 管理者として実行するには、このファイルを右クリックして
        echo 「管理者として実行」を選択してください。
        echo.
        choice /C YN /M "このまま続行しますか？ (Y/N)"
        if %ERRORLEVEL% equ 2 exit /b 0
        echo.
    )
    
    REM デスクトップにショートカットを作成
    echo デスクトップにショートカットを作成しますか？
    echo これにより、次回からデスクトップから直接アプリを起動できます。
    choice /C YN /M "ショートカットを作成しますか？ (Y/N)"
    if %ERRORLEVEL% equ 1 (
        echo ショートカットを作成しています...
        call "%CURRENT_DIR%\create_shortcut.bat" >nul 2>&1
        if %ERRORLEVEL% equ 0 (
            echo デスクトップにショートカットを作成しました。
        ) else (
            echo ショートカット作成に失敗しました。管理者権限が必要かもしれません。
        )
        echo.
    )
    
    REM 初期化済みフラグを作成
    echo 1 > ".initialized"
)

echo アプリケーションを起動しています...
echo 少々お待ちください...
echo.
echo ※ アプリケーションが起動したら、このウィンドウは閉じても構いません。
echo.

REM アプリケーションを起動
start "" %APP_PATH%

REM 3秒待機してから終了
timeout /t 3 /nobreak >nul
exit /b 0
