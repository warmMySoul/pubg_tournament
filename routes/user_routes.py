from flask import Blueprint, flash, url_for, redirect, session, request, render_template
from datetime import datetime
from extensions.security import role_required
from werkzeug.security import generate_password_hash, check_password_hash
from models import RoleEnum, User
from db_connection import db

# Импорт логирования
from services.admin_log_service import log_admin_action as log

user_bp = Blueprint('user', __name__, url_prefix='/user')


@user_bp.route('/profile', methods=['GET', 'POST'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR, RoleEnum.CLAN_MEMBER, RoleEnum.GUEST])
def profile():
    user = User.query.get_or_404(session['user_logged'])

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')

        user.name = request.form.get('name')
        user.pubg_nickname = request.form.get('pubg_nickname')
        birthday_str = request.form.get('birthday')

        if birthday_str:
            try:
                user.birthday = datetime.strptime(birthday_str, '%Y-%m-%d')
            except ValueError:
                flash('Неверный формат даты', 'error')
                return redirect(url_for('user.profile'))

        if current_password and new_password:
            if not check_password_hash(user.password, current_password):
                flash('Текущий пароль неверен', 'error')
                return redirect(url_for('user.profile'))
            elif len(new_password) < 6 or len(new_password) > 30:
                flash('Новый пароль должен быть от 6 до 30 символов', 'error')
                return redirect(url_for('user.profile'))
            else:
                user.password = generate_password_hash(new_password)
                log(f"Пользователь {user.username} сменил пароль")

        db.session.commit()
        flash('Профиль успешно обновлён', 'success')
        log(f"Обновил свой профиль")
        return redirect(url_for('user.profile'))

    return render_template('profile.html', user=user)