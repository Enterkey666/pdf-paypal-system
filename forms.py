from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Length, Email, Optional

class LoginForm(FlaskForm):
    """ログインフォーム"""
    username = StringField('ユーザー名', validators=[DataRequired(), Length(min=1, max=80)])
    password = PasswordField('パスワード', validators=[DataRequired()])
    remember = BooleanField('ログイン状態を保持する')
    submit = SubmitField('ログイン')

class UserRegistrationForm(FlaskForm):
    """ユーザー登録フォーム"""
    username = StringField('ユーザー名', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('メールアドレス', validators=[DataRequired(), Email()])
    password = PasswordField('パスワード', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('登録')

class PayPalSettingsForm(FlaskForm):
    """PayPal設定フォーム"""
    client_id = StringField('Client ID', validators=[Optional()])
    client_secret = StringField('Client Secret', validators=[Optional()])
    paypal_mode = SelectField('PayPalモード', 
                             choices=[('sandbox', 'Sandbox'), ('live', 'Live')],
                             default='sandbox')
    submit = SubmitField('保存')

class UserProfileForm(FlaskForm):
    """ユーザープロフィールフォーム"""
    email = StringField('メールアドレス', validators=[DataRequired(), Email()])
    submit = SubmitField('更新')

class PasswordChangeForm(FlaskForm):
    """パスワード変更フォーム"""
    current_password = PasswordField('現在のパスワード', validators=[DataRequired()])
    new_password = PasswordField('新しいパスワード', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('新しいパスワード（確認）', validators=[DataRequired()])
    submit = SubmitField('変更')
