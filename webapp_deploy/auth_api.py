import functools
from flask import jsonify, current_app
from flask_login import current_user

def api_admin_required(f):
    """
    API用の管理者権限チェックデコレータ
    未認証の場合はJSONエラーレスポンスを返す（リダイレクトしない）
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({
                'success': False,
                'message': '管理者権限が必要です。ログインしてください。',
                'auth_required': True
            }), 401
        return f(*args, **kwargs)
    return decorated_function
