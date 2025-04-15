from functools import wraps
from flask import session, redirect, url_for, flash
from models import User

# Получение данных авторизованного пользователя
def get_current_user():
    user_id = session.get('user_logged')
    return User.query.get(user_id) if user_id else None

# Проверка роли текущего пользователя
def role_required(required_roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user or user.role not in required_roles:
                flash('Недостаточно прав доступа', 'error')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator
