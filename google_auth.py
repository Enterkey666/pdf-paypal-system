#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Google OAuth認証モジュール

FlaskアプリケーションにGoogle OAuth認証を追加するためのモジュール
"""

import os
import json
import logging
from flask import Blueprint, redirect, url_for, session, request, flash, current_app
from authlib.integrations.flask_client import OAuth

# データベースモジュールをインポート
import database

# ロガーの設定
logger = logging.getLogger(__name__)

# OAuth設定
oauth = OAuth()

# Blueprintの作成
google_bp = Blueprint('google_auth', __name__)

def setup_google_oauth(app):
    """Google OAuth設定を初期化する関数"""
    
    # クライアントIDとシークレットを環境変数から取得
    google_client_id = os.environ.get('GOOGLE_CLIENT_ID')
    google_client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    
    if not google_client_id or not google_client_secret:
        logger.warning("Google OAuth認証情報が設定されていません。環境変数 GOOGLE_CLIENT_ID と GOOGLE_CLIENT_SECRET を設定してください。")
        return False
    
    # GoogleのOAuth設定
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )
    
    logger.info("Google OAuth設定を初期化しました")
    return True

# Googleログインルート
@google_bp.route('/login/google')
def google_login():
    """Googleログインを開始するエンドポイント"""
    redirect_uri = url_for('google_auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

# Googleコールバックルート
@google_bp.route('/login/google/callback')
def google_callback():
    """Googleログインコールバック処理"""
    try:
        token = oauth.google.authorize_access_token()
        user_info = oauth.google.parse_id_token(token)
        
        # ユーザー情報をログに出力（デバッグ用）
        logger.info(f"Google認証成功: {user_info.get('email')}")
        
        # ユーザー情報をデータベースで確認または作成
        email = user_info.get('email')
        name = user_info.get('name')
        picture = user_info.get('picture')
        
        # メールアドレスからユーザーを取得または作成
        user = database.get_or_create_google_user(email, name, picture)
        
        if not user:
            flash('アカウントの作成に失敗しました', 'danger')
            return redirect(url_for('auth.login'))
        
        # セッション情報を設定
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['email'] = email
        session['is_admin'] = user['is_admin']
        session['picture'] = picture
        
        flash(f'こんにちは、{name}さん！', 'success')
        
        # リダイレクト先の指定があればそこに、なければトップページに
        next_page = session.get('next', None)
        if next_page:
            session.pop('next', None)
            return redirect(next_page)
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Googleコールバック処理エラー: {str(e)}")
        flash('Google認証に失敗しました', 'danger')
        return redirect(url_for('auth.login'))

# セッションクリア（ログアウト）
@google_bp.route('/logout')
def logout():
    """ログアウト処理"""
    # セッションからユーザー情報を削除
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('email', None)
    session.pop('is_admin', None)
    session.pop('picture', None)
    
    flash('ログアウトしました', 'info')
    return redirect(url_for('auth.login'))
