from flask import Blueprint, request, session, redirect, url_for, flash, render_template
from werkzeug.security import check_password_hash, generate_password_hash
from models import User, RoleEnum
from db_connection import db

# Импорт логирования
from services.admin_log_service import log_admin_action as log

auth_bp = Blueprint('auth', __name__)

# Авторизация
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_logged'] = user.id
            flash(f"Добро пожаловать, {user.username} ({user.role})", 'success')
            if user.role == RoleEnum.ADMIN:
                return redirect(url_for('admin.admin'))
            return redirect(url_for('home'))
        else:
            flash('Неверные учетные данные', 'error')

    return render_template('login.html')

# Выход
@auth_bp.route('/logout')
def logout():
    session.pop('user_logged', None)
    flash("Вы вышли из системы", 'success')
    return redirect(url_for('auth.login'))

# Регистрация
@auth_bp.route('/register', methods=['GET', 'POST'])
def register_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        pubg_nickname = request.form['pubg_nickname']

        if User.query.filter_by(username=username).first():
            flash('Это имя пользователя уже занято', 'error')
        else:
            new_user = User(
                username=username,
                pubg_nickname=pubg_nickname,
                password=generate_password_hash(password),
                role=RoleEnum.GUEST  # стартовая роль — гость
            )
            db.session.add(new_user)
            db.session.commit()
            flash('Вы успешно зарегистрировались', 'success')
            log(f"Зарегистрирован новый пользователь (гость) '{username}'")
            return redirect(url_for('auth.login'))
    return render_template('register_user.html')