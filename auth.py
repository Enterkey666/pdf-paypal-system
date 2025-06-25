#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
認証モジュール
メールアドレスとパスワードによる認証機能を提供
"""

import os
import logging
from flask import Blueprint, redirect, url_for, session, request, flash, render_template, current_app
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

# データベースモジュールをインポート
import database

# ロガーの設定
logger = logging.getLogger(__name__)

# Blueprintの作成
auth_bp = Blueprint('auth', __name__)

# LoginManagerの作成
login_manager = LoginManager()

# データベースモジュールのUserクラスを使用するのでここでの定義は不要

# ユーザーローダー関数
@login_manager.user_loader
def load_user(user_id):
    # データベースモジュールのget_user_by_id関数はすでにUserオブジェクトを返す
    return database.get_user_by_id(int(user_id))

# LoginManagerの設定
def setup_login_manager(app):
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'この機能を利用するにはログインが必要です'
    login_manager.login_message_category = 'info'
    logger.info("LoginManagerを初期化しました")

# 管理者権限チェック用デコレータ
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('この機能を利用するには管理者権限が必要です', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# ログインルート
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """ログイン処理"""
    # ユーザーが既にログインしている場合はトップページにリダイレクト
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form

        # 入力検証
        if not username or not password:
            flash('ユーザー名とパスワードを入力してください', 'danger')
            return render_template('login.html')

        # ユーザー認証
        user = database.get_user_by_username(username)
        if user and user.check_password(password):
            login_user(user, remember=remember)
            
            # ログイン成功ログ
            logger.info(f"ユーザー {username} がログインしました")
            
            # ログイン日時を更新
            database.update_last_login(user.id)
            
            # リダイレクト先の指定があればそこに、なければトップページに
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('ユーザー名またはパスワードが正しくありません', 'danger')
            logger.warning(f"ログイン失敗: {username}")

    return render_template('login.html')

# 新規登録ルート
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """ユーザー登録処理"""
    # ユーザーが既にログインしている場合はトップページにリダイレクト
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        # 入力検証
        if not username or not email or not password:
            flash('すべての項目を入力してください', 'danger')
            return render_template('register.html')

        if password != password_confirm:
            flash('パスワードが一致しません', 'danger')
            return render_template('register.html')

        # 最初のユーザーの場合は管理者権限を付与
        user_count = database.get_user_count()
        is_admin = (user_count == 0) or (username.lower() == 'admin')
        
        # ユーザー作成
        success, message = database.create_user(username, password, email=email, is_admin=is_admin)
        if success:
            # 作成したユーザーを取得してログイン
            user = database.get_user_by_username(username)
            if user:
                login_user(user)
                if is_admin:
                    flash('管理者アカウントが作成され、ログインしました', 'success')
                    logger.info(f"新規管理者登録とログイン: {email}")
                else:
                    flash('アカウントが作成され、ログインしました', 'success')
                    logger.info(f"新規ユーザー登録とログイン: {email}")
                return redirect(url_for('index'))
            else:
                flash('アカウントは作成されましたが、ログインに失敗しました', 'warning')
                return redirect(url_for('auth.login'))
        else:
            flash(message, 'danger')
            logger.warning(f"ユーザー登録失敗: {message}")

    return render_template('register.html')

# ログアウトルート
@auth_bp.route('/logout')
@login_required
def logout():
    """ログアウト処理"""
    logger.info(f"ユーザー {current_user.email} がログアウトしました")
    logout_user()
    flash('ログアウトしました', 'info')
    return redirect(url_for('auth.login'))
