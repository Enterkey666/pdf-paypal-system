#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""認証関連のルート

ログイン、ログアウト、ユーザー管理などの認証関連の機能を提供するルート
"""

import os
import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

# データベースモジュールをインポート
import database

# ロガーの設定
logger = logging.getLogger(__name__)

# Blueprintの作成
auth_bp = Blueprint('auth', __name__)

# ログインフォーム
class LoginForm(FlaskForm):
    username = StringField('ユーザー名', validators=[DataRequired()])
    password = PasswordField('パスワード', validators=[DataRequired()])
    remember = BooleanField('ログイン状態を保持')
    submit = SubmitField('ログイン')

# ユーザー登録フォーム
class RegisterForm(FlaskForm):
    username = StringField('ユーザー名', validators=[DataRequired(), Length(min=3, max=50)])
    password = PasswordField('パスワード', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('パスワード（確認）', 
                                    validators=[DataRequired(), EqualTo('password')])
    is_admin = BooleanField('管理者権限')
    submit = SubmitField('登録')
    
    def validate_username(self, username):
        user = database.get_user_by_username(username.data)
        if user:
            raise ValidationError('このユーザー名は既に使用されています。別のユーザー名を選択してください。')

# PayPal設定フォーム
class PayPalSettingsForm(FlaskForm):
    client_id = StringField('PayPal Client ID', validators=[DataRequired()])
    client_secret = StringField('PayPal Client Secret', validators=[DataRequired()])
    mode = SelectField('モード', choices=[('sandbox', 'Sandbox (テスト)'), ('live', 'Live (本番)')], validators=[DataRequired()])
    currency = StringField('通貨コード', validators=[DataRequired()], default='JPY')
    submit = SubmitField('保存')

# ログインルート
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # 既にログイン済みの場合はトップページにリダイレクト
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        user = database.get_user_by_username(username)
        
        if user and check_password_hash(user['password_hash'], password):
            # セッションにユーザー情報を保存
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            # admin_logged_inも設定して一貫性を確保
            session['admin_logged_in'] = user['is_admin']
            
            # ログイン状態を保持する場合
            if form.remember.data:
                session.permanent = True
            
            logger.info(f"ユーザー '{username}' がログインしました")
            flash(f'ようこそ、{username}さん！', 'success')
            
            # リダイレクト先の指定があればそこに、なければトップページに
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            logger.warning(f"ユーザー '{username}' のログイン試行が失敗しました")
            flash('ユーザー名またはパスワードが正しくありません', 'danger')
    
    return render_template('login.html', form=form)

# ログアウトルート
@auth_bp.route('/logout')
def logout():
    username = session.get('username', '不明')
    
    # セッションからユーザー情報を削除
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', None)
    session.pop('admin_logged_in', None)
    
    logger.info(f"ユーザー '{username}' がログアウトしました")
    flash('ログアウトしました', 'info')
    return redirect(url_for('auth.login'))

# ユーザー登録ルート（管理者のみアクセス可能）
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # 管理者でなければアクセス拒否
    if not session.get('is_admin', False):
        flash('このページにアクセスする権限がありません', 'danger')
        return redirect(url_for('auth.login'))
    
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        is_admin = form.is_admin.data
        
        # パスワードをハッシュ化
        password_hash = generate_password_hash(password)
        
        # ユーザーをデータベースに登録
        try:
            user_id = database.create_user(username, password_hash, is_admin)
            logger.info(f"新しいユーザー '{username}' が登録されました（管理者: {is_admin}）")
            flash(f'ユーザー "{username}" を登録しました', 'success')
            return redirect(url_for('auth.user_list'))
        except Exception as e:
            logger.error(f"ユーザー登録エラー: {str(e)}")
            flash(f'ユーザー登録中にエラーが発生しました: {str(e)}', 'danger')
    
    return render_template('register.html', form=form)

# ユーザー一覧ルート（管理者のみアクセス可能）
@auth_bp.route('/users')
def user_list():
    # 管理者でなければアクセス拒否
    if not session.get('is_admin', False):
        flash('このページにアクセスする権限がありません', 'danger')
        return redirect(url_for('auth.login'))
    
    try:
        users = database.get_all_users()
        return render_template('user_list.html', users=users)
    except Exception as e:
        logger.error(f"ユーザー一覧取得エラー: {str(e)}")
        flash(f'ユーザー一覧の取得中にエラーが発生しました: {str(e)}', 'danger')
        return redirect(url_for('index'))

# ユーザー削除ルート（管理者のみアクセス可能）
@auth_bp.route('/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    # 管理者でなければアクセス拒否
    if not session.get('is_admin', False):
        flash('このページにアクセスする権限がありません', 'danger')
        return redirect(url_for('auth.login'))
    
    # 自分自身は削除できない
    if user_id == session.get('user_id'):
        flash('自分自身を削除することはできません', 'danger')
        return redirect(url_for('auth.user_list'))
    
    try:
        user = database.get_user_by_id(user_id)
        if user:
            database.delete_user(user_id)
            logger.info(f"ユーザー '{user['username']}' が削除されました")
            flash(f'ユーザー "{user["username"]}" を削除しました', 'success')
        else:
            flash('指定されたユーザーが見つかりません', 'danger')
    except Exception as e:
        logger.error(f"ユーザー削除エラー: {str(e)}")
        flash(f'ユーザー削除中にエラーが発生しました: {str(e)}', 'danger')
    
    return redirect(url_for('auth.user_list'))

# PayPal設定ルート
@auth_bp.route('/paypal_settings', methods=['GET', 'POST'])
def paypal_settings():
    # ログインしていなければログインページにリダイレクト
    if 'user_id' not in session:
        return redirect(url_for('auth.login', next=request.url))
    
    user_id = session['user_id']
    form = PayPalSettingsForm()
    
    # フォーム送信時の処理
    if form.validate_on_submit():
        try:
            # PayPal設定を保存
            settings = {
                'client_id': form.client_id.data,
                'client_secret': form.client_secret.data,
                'mode': form.mode.data,
                'currency': form.currency.data
            }
            
            database.save_paypal_settings(user_id, settings)
            logger.info(f"ユーザーID {user_id} のPayPal設定が更新されました")
            flash('PayPal設定を保存しました', 'success')
            return redirect(url_for('auth.paypal_settings'))
        
        except Exception as e:
            logger.error(f"PayPal設定保存エラー: {str(e)}")
            flash(f'設定の保存中にエラーが発生しました: {str(e)}', 'danger')
    
    # GETリクエスト時は現在の設定を取得して表示
    elif request.method == 'GET':
        try:
            settings = database.get_paypal_settings(user_id)
            if settings:
                form.client_id.data = settings['client_id']
                form.client_secret.data = settings['client_secret']
                form.mode.data = settings['mode']
                form.currency.data = settings['currency']
        except Exception as e:
            logger.error(f"PayPal設定取得エラー: {str(e)}")
            flash(f'設定の取得中にエラーが発生しました: {str(e)}', 'danger')
    
    return render_template('paypal_settings.html', form=form)

# ユーザープロファイルルート
@auth_bp.route('/profile')
def profile():
    # ログインしていなければログインページにリダイレクト
    if 'user_id' not in session:
        return redirect(url_for('auth.login', next=request.url))
    
    user_id = session['user_id']
    
    try:
        # ユーザー情報を取得
        user = database.get_user_by_id(user_id)
        
        # PayPal設定情報を取得
        paypal_settings = database.get_paypal_settings(user_id)
        
        # 処理履歴を取得
        history = database.get_user_processing_history(user_id, limit=10)
        
        return render_template('profile.html', user=user, paypal_settings=paypal_settings, history=history)
    
    except Exception as e:
        logger.error(f"プロファイル情報取得エラー: {str(e)}")
        flash(f'プロファイル情報の取得中にエラーが発生しました: {str(e)}', 'danger')
        return redirect(url_for('index'))

# パスワード変更ルート
@auth_bp.route('/change_password', methods=['GET', 'POST'])
def change_password():
    # ログインしていなければログインページにリダイレクト
    if 'user_id' not in session:
        return redirect(url_for('auth.login', next=request.url))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 入力チェック
        if not current_password or not new_password or not confirm_password:
            flash('すべての項目を入力してください', 'danger')
            return redirect(url_for('auth.change_password'))
        
        if new_password != confirm_password:
            flash('新しいパスワードと確認用パスワードが一致しません', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # 現在のパスワードを確認
        user_id = session['user_id']
        user = database.get_user_by_id(user_id)
        
        if not user or not check_password_hash(user['password_hash'], current_password):
            flash('現在のパスワードが正しくありません', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # パスワードを更新
        try:
            new_password_hash = generate_password_hash(new_password)
            database.update_user_password(user_id, new_password_hash)
            logger.info(f"ユーザーID {user_id} のパスワードが変更されました")
            flash('パスワードを変更しました', 'success')
            return redirect(url_for('auth.profile'))
        
        except Exception as e:
            logger.error(f"パスワード変更エラー: {str(e)}")
            flash(f'パスワード変更中にエラーが発生しました: {str(e)}', 'danger')
    
    return render_template('change_password.html')

# 初期管理者ユーザー作成関数
def create_initial_admin():
    try:
        # 管理者ユーザーが存在するか確認
        admin_exists = database.admin_user_exists()
        
        if not admin_exists:
            # 環境変数から管理者パスワードを取得、なければランダム生成
            admin_password = os.environ.get('ADMIN_PASSWORD')
            if not admin_password:
                import secrets
                import string
                # 16文字のランダムパスワードを生成
                chars = string.ascii_letters + string.digits
                admin_password = ''.join(secrets.choice(chars) for _ in range(16))
                logger.info(f"管理者パスワードが環境変数に設定されていないため、ランダムパスワードを生成しました: {admin_password}")
                print(f"初期管理者パスワード: {admin_password}")
            
            # パスワードをハッシュ化
            password_hash = generate_password_hash(admin_password)
            
            # 管理者ユーザーを作成
            admin_id = database.create_user('admin', password_hash, True)
            logger.info(f"初期管理者ユーザー 'admin' を作成しました (ID: {admin_id})")
            
            # 初期PayPal設定を作成（環境変数から取得）
            paypal_settings = {
                'client_id': os.environ.get('PAYPAL_CLIENT_ID', ''),
                'client_secret': os.environ.get('PAYPAL_CLIENT_SECRET', ''),
                'mode': os.environ.get('PAYPAL_MODE', 'sandbox'),
                'currency': os.environ.get('PAYPAL_CURRENCY', 'JPY')
            }
            
            # 設定が空でなければ保存
            if paypal_settings['client_id'] and paypal_settings['client_secret']:
                database.save_paypal_settings(admin_id, paypal_settings)
                logger.info(f"初期管理者ユーザーのPayPal設定を環境変数から作成しました")
    
    except Exception as e:
        logger.error(f"初期管理者ユーザー作成エラー: {str(e)}")
