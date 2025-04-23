from functools import wraps
from flask import session, redirect, url_for, flash, request
from cryptography.fernet import Fernet
from flask import current_app
from models import User

# Получение данных авторизованного пользователя
def get_current_user():
    user_id = session.get('user_logged')
    return User.query.get(user_id) if user_id else None

# Проверка авторизации пользователя
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not get_current_user():
            flash('Для доступа к данной странице необходимо авторизоваться', 'error')
            return redirect(request.referrer or url_for('public.home'))
        return f(*args, **kwargs)
    return decorated_function

# Проверка роли текущего пользователя (теперь включает проверку авторизации)
def role_required(required_roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                flash('Для доступа к данной странице необходимо авторизоваться', 'warning')
                return redirect(request.referrer or url_for('public.home'))
            if user.role not in required_roles:
                flash('Недостаточно прав доступа', 'error')
                return redirect(request.referrer or url_for('public.home'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

def get_cipher():
    """Инициализирует шифровальщик в контексте приложения"""
    return Fernet(current_app.config['FERNET_KEY'].encode())