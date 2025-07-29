#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
認証初期化モジュール
Flask-Loginの初期化と設定を行う
"""

import os
import logging
from flask import Flask, session
from flask_login import LoginManager, current_user

# データベースモジュールをインポート
import database

# ロガーの設定
logger = logging.getLogger(__name__)

def init_login_manager(app):
    """
    Flask-Loginの初期化と設定
    
    Args:
        app: Flaskアプリケーションインスタンス
    """
    try:
        # LoginManagerの初期化
        login_manager = LoginManager(app)
        login_manager.login_view = 'auth.login'
        login_manager.login_message = 'この機能を使用するにはログインが必要です'
        login_manager.login_message_category = 'info'
        
        # ユーザーローダー関数の設定
        @login_manager.user_loader
        def load_user(user_id):
            """
            ユーザーIDからユーザーオブジェクトを取得する
            
            Args:
                user_id (str): ユーザーID
                
            Returns:
                User: ユーザーオブジェクト、存在しない場合はNone
            """
            try:
                user = database.get_user_by_id(int(user_id))
                if user:
                    # セッション変数とFlask-Loginの状態を同期
                    if 'user_id' in session and int(session['user_id']) == user.id:
                        # セッション変数を更新
                        session['is_admin'] = user.is_admin
                        session['admin_logged_in'] = user.is_admin
                        session['is_paid_member'] = user.is_paid_member
                    return user
                return None
            except Exception as e:
                logger.error(f"ユーザーロード中にエラーが発生: {str(e)}")
                return None
        
        logger.info("Flask-Loginの初期化が完了しました")
        return login_manager
    
    except Exception as e:
        logger.error(f"Flask-Loginの初期化中にエラーが発生: {str(e)}")
        return None

def sync_session_with_user():
    """
    現在のユーザー状態とセッション変数を同期する
    ログイン後やページ遷移時に呼び出す
    """
    try:
        if current_user.is_authenticated:
            # Flask-Loginのユーザー情報をセッションに反映
            session['user_id'] = current_user.id
            session['username'] = current_user.username
            session['is_admin'] = current_user.is_admin
            session['admin_logged_in'] = current_user.is_admin
            session['is_paid_member'] = current_user.is_paid_member
            logger.debug(f"ユーザー状態をセッションに同期: {current_user.username}, admin={current_user.is_admin}")
        else:
            # 認証されていない場合はセッション変数をクリア
            if 'user_id' in session:
                session.pop('user_id', None)
            if 'username' in session:
                session.pop('username', None)
            if 'is_admin' in session:
                session.pop('is_admin', None)
            if 'admin_logged_in' in session:
                session.pop('admin_logged_in', None)
            if 'is_paid_member' in session:
                session.pop('is_paid_member', None)
            logger.debug("未認証ユーザー: セッション認証変数をクリア")
    except Exception as e:
        logger.error(f"セッション同期中にエラーが発生: {str(e)}")
