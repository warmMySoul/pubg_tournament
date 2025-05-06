from zoneinfo import ZoneInfo
from flask import Blueprint, flash, url_for, redirect, session, request, render_template
from datetime import datetime, timedelta
from extensions.security import is_safe_url, role_required, get_current_user, login_required, get_cipher
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from pubg_api.models.player import ParsedPlayerStats
from services.verification_service import generate_verification_code, send_verification_email
from utils.helpers import mask_email, registration_open as tournament_reg_is_open
from models import RoleEnum, User, Tournament, Player, PlayerGroup, AdminActionLog, PlayerStats
from extensions.db_connection import db

# Импорт PUBG API
from pubg_api.client import PUBGApiClient
client = PUBGApiClient()


# Импорт логирования
from services.admin_log_service import log_admin_action as log

user_bp = Blueprint('user', __name__, url_prefix='/user')

# Профиль пользователя
@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():

    # Инициализация шифровальщика
    cipher = get_cipher()

    user = User.query.get_or_404(session['user_logged'])
    player_stats = None
    updated_at = None

    if user.username != "admin":
        cached_stats = PlayerStats.query.filter_by(user_id=user.id).first()
        
        if cached_stats:
            try:
                player_stats = ParsedPlayerStats.from_json(cached_stats.stats_json)
                updated_at = cached_stats.updated_at            
            except Exception as e:
                flash(f"Возникли ошибки при загрузке статистики. Попробуйте позже.", 'warning')
        else:
            try:
                player = client.get_player_by_name(user.pubg_nickname)
                if player:
                    try:
                        player_stats = client.get_player_lifetime_stats_by_id(player.id)
                        cached_stats = PlayerStats(
                            user_id=user.id,
                            pubg_id=player.id,
                            stats_json=player_stats.to_dict(),
                            match_ids=player.match_ids
                        )
                        db.session.add(cached_stats)
                        db.session.commit()
                        updated_at = cached_stats.updated_at
                    except Exception as e:
                        db.session.rollback()
                        flash(f"Статистика временно недоступна.", 'error')
            except Exception as e:
                flash(f"Игрока с таким ником не найдено. Проверьте ник. Для изменения обратитесь к администратору", 'error')

    # Обработка POST-запроса (изменение профиля)
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            # Обновление обычных данных профиля
            user.name = request.form.get('name')
            birthday_str = request.form.get('birthday')

            if birthday_str:
                try:
                    user.birthday = datetime.strptime(birthday_str, '%Y-%m-%d')
                except ValueError:
                    flash('Неверный формат даты', 'error')
                    return redirect(url_for('user.profile'))

            try:
                db.session.commit()
                flash('Профиль успешно обновлён', 'success')
                log(f"Обновил свой профиль")
            except Exception as e:
                db.session.rollback()
                flash(f'Ошибка при обновлении профиля. Проверьте данные.', 'error')

            return redirect(url_for('user.profile'))
            
        elif action == 'request_password_change':
            # Запрос на смену пароля
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            
            if not check_password_hash(user.password, current_password):
                flash('Текущий пароль неверен', 'error')
                return redirect(url_for('user.profile'))
                
            if len(new_password) < 6 or len(new_password) > 30:
                flash('Новый пароль должен быть от 6 до 30 символов', 'error')
                return redirect(url_for('user.profile'))
                
            # Генерация и отправка кода подтверждения
            verification_code = generate_verification_code()
            encrypted_code = cipher.encrypt(verification_code.encode())
            
            session['password_change_data'] = {
                'user_id': user.id,
                'new_password_hash': generate_password_hash(new_password),
                'encrypted_code': encrypted_code,
                'expires': (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(minutes=30)).isoformat()
            }
            
            send_verification_email(user.email, verification_code)
            flash('Код подтверждения отправлен на вашу почту', 'success')
            return redirect(url_for('user.profile'))
            
        elif action == 'confirm_password_change':
            # Подтверждение смены пароля
            entered_code = request.form.get('verification_code')
            change_data = session.get('password_change_data')
            
            if not change_data or change_data['user_id'] != user.id:
                flash('Сессия истекла. Начните процесс смены пароля заново.', 'error')
                return redirect(url_for('user.profile'))
                
            if datetime.now(ZoneInfo("Europe/Moscow")) > datetime.fromisoformat(change_data['expires']):
                flash('Срок действия кода истек', 'error')
                return redirect(url_for('user.profile'))
                
            try:
                decrypted_code = cipher.decrypt(change_data['encrypted_code']).decode()
                if decrypted_code == entered_code:
                    user.password = change_data['new_password_hash']
                    db.session.commit()
                    session.pop('password_change_data', None)
                    flash('Пароль успешно изменён', 'success')
                    log(f"Пользователь {user.username} сменил пароль")
                else:
                    flash('Неверный код подтверждения', 'error')
            except Exception as e:
                flash('Ошибка при проверке кода', 'error')
            
            return redirect(url_for('user.profile'))

    # Маскировка email для отображения
    masked_email = mask_email(user.email) if user.email else None
    
    return render_template('user/profile.html', 
                         user=user, 
                         stats=player_stats, 
                         updated_at=updated_at,
                         masked_email=masked_email,
                         password_change_requested='password_change_data' in session)

@user_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_logged'] = user.id
            flash(f"Добро пожаловать, {user.username} ({user.role})", 'success')
            
            # Перенаправляем на next или на главную
            next_url = request.form['next']
            if next_url and is_safe_url(next_url):
                return redirect(next_url)
            return redirect(url_for('public.home'))
        else:
            flash('Неверные учетные данные', 'error')

    return render_template('user/login.html')

# Выход
@user_bp.route('/logout')
@login_required
def logout():
    session.pop('user_logged', None)
    flash("Вы вышли из системы", 'success')
    return redirect(url_for('public.home'))

# Регистрация
@user_bp.route('/register', methods=['GET', 'POST'])
def register_user():
    # Инициализация шифровальщика
    cipher = get_cipher()

    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            pubg_nickname = request.form.get('pubg_nickname', '').strip()
            email = request.form.get('email', '').strip().lower()  # Нормализуем email

            # Валидация данных
            if not all([username, password, pubg_nickname, email]):
                flash('Все поля обязательны для заполнения', 'error')
                return render_template('user/register_user.html')

            # Проверка уникальности
            if User.query.filter_by(username=username).first():
                flash('Это имя пользователя уже занято', 'error')
            elif User.query.filter_by(email=email).first():
                flash('Этот email уже используется', 'error')
            else:
                # Сохраняем данные в сессию до подтверждения email
                session['temp_user'] = {
                    'username': username,
                    'password': generate_password_hash(password),
                    'pubg_nickname': pubg_nickname,
                    'email': email
                }

                # Генерация, шифрование и сохранение кода
                verification_code = generate_verification_code()
                encrypted_code = cipher.encrypt(verification_code.encode())
                session['encrypted_code'] = encrypted_code
                session['code_expires'] = (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(minutes=5)).isoformat()

                # Отправка письма
                send_verification_email(email, verification_code)
                flash('Код подтверждения отправлен на ваш email', 'success')
                return redirect(url_for('user.verify_email'))

        except Exception as e:
            flash('Произошла ошибка при регистрации', 'error')

    return render_template('user/register_user.html')

# Подтверждение почты
@user_bp.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    # Инициализация шифровальщика
    cipher = get_cipher()

    # Проверяем, есть ли временные данные пользователя
    if 'temp_user' not in session:
        flash('Сессия истекла или не найдена. Пожалуйста, зарегистрируйтесь снова.', 'error')
        return redirect(url_for('user.register_user'))

    if request.method == 'POST':
        entered_code = request.form.get('verification_code', '').strip()
        
        # Проверяем наличие и срок действия кода
        try:
            encrypted_code = session.get('encrypted_code')
            expires = datetime.fromisoformat(session.get('code_expires', ''))
            
            if not encrypted_code:
                flash('Код подтверждения не найден', 'error')
                return redirect(url_for('user.register_user'))
                
            if datetime.now(ZoneInfo("Europe/Moscow")) > expires:
                flash('Срок действия кода истек', 'error')
                return redirect(url_for('user.register_user'))
                
            # Расшифровываем и сравниваем код
            decrypted_code = cipher.decrypt(encrypted_code).decode()
            
            if decrypted_code == entered_code:
                # Создаем пользователя
                temp_user = session['temp_user']
                new_user = User(
                    username=temp_user['username'],
                    password=temp_user['password'],
                    pubg_nickname=temp_user['pubg_nickname'],
                    email=temp_user['email'],
                    is_verified=True
                )
                
                try:
                    db.session.add(new_user)
                    db.session.commit()
                    
                    # Очищаем сессию
                    session.pop('temp_user', None)
                    session.pop('encrypted_code', None)
                    session.pop('code_expires', None)
                    
                    flash('Email подтвержден! Вы успешно зарегистрированы.', 'success')
                    log(f'Зарегистрирован новый пользователь - {new_user.username} ({new_user.pubg_nickname})')
                    return redirect(url_for('user.login'))
                    
                except Exception as db_error:
                    db.session.rollback()
                    flash('Ошибка при создании пользователя', 'error')
                    
            else:
                flash('Неверный код подтверждения', 'error')
                
        except Exception as e:
            flash('Ошибка при проверке кода', 'error')

    return render_template('user/verify_email.html')

# Переотправка кода на почту
@user_bp.route('/resend-code', methods=['GET'])
def resend_code():
    # Инициализация шифровальщика
    cipher = get_cipher()

    try:
        temp_user = session.get('temp_user')
        if not temp_user:
            flash('Сессия истекла. Зарегистрируйтесь снова.', 'error')
            return redirect(url_for('user.register_user'))

        # Генерация нового кода
        new_code = generate_verification_code()
        encrypted_code = cipher.encrypt(new_code.encode())
        
        # Обновление данных в сессии
        session['encrypted_code'] = encrypted_code
        session['code_expires'] = (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(minutes=5)).isoformat()

        # Отправка письма
        send_verification_email(temp_user['email'], new_code)
        flash('Новый код отправлен! Проверьте почту.', 'success')
        return redirect(url_for('user.verify_email'))
    
    except Exception as e:
        flash('Произошла ошибка при отправке кода', 'error')
        return redirect(url_for('user.register_user'))

# Восстановление пароля - шаг 1 (запрос)
@user_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():

    # Инициализация шифровальщика
    cipher = get_cipher()

    if request.method == 'POST':
        username = request.form.get('username').strip()
        email = request.form.get('email').strip().lower()
        
        user = User.query.filter_by(username=username, email=email).first()
        
        if user:
            # Генерация и отправка кода
            verification_code = generate_verification_code()
            encrypted_code = cipher.encrypt(verification_code.encode())
            
            session['password_reset'] = {
                'user_id': user.id,
                'encrypted_code': encrypted_code,
                'expires': (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(minutes=30)).isoformat()
            }
            
            send_verification_email(user.email, verification_code)
            flash('Код подтверждения отправлен на вашу почту', 'success')
            return redirect(url_for('user.reset_password'))
        else:
            flash('Пользователь с такими данными не найден', 'error')
    
    return render_template('user/forgot_password.html')

# Восстановление пароля - шаг 2 (ввод кода и нового пароля)
@user_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():

    # Инициализация шифровальщика
    cipher = get_cipher()

    reset_data = session.get('password_reset')
    if not reset_data:
        flash('Сессия истекла или не найдена', 'error')
        return redirect(url_for('user.forgot_password'))
    
    if request.method == 'POST':
        entered_code = request.form.get('verification_code')
        new_password = request.form.get('new_password')
        
        if datetime.now(ZoneInfo("Europe/Moscow")) > datetime.fromisoformat(reset_data['expires']):
            flash('Срок действия кода истек', 'error')
            return redirect(url_for('user.forgot_password'))
        
        try:
            decrypted_code = cipher.decrypt(reset_data['encrypted_code']).decode()
            if decrypted_code == entered_code:
                if len(new_password) < 6 or len(new_password) > 30:
                    flash('Пароль должен быть от 6 до 30 символов', 'error')
                    return redirect(url_for('user.reset_password'))
                
                user = User.query.get(reset_data['user_id'])
                user.password = generate_password_hash(new_password)
                db.session.commit()
                
                session.pop('password_reset', None)
                flash('Пароль успешно изменён. Теперь вы можете войти.', 'success')
                log(f"Пользователь {user.username} восстановил пароль")
                return redirect(url_for('user.login'))
            else:
                flash('Неверный код подтверждения', 'error')
        except Exception as e:
            flash('Ошибка при проверке кода', 'error')
    
    return render_template('user/reset_password.html')

@user_bp.route('/form/<tournament_id>', methods=['GET', 'POST'])
@login_required
def player_form(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    user = get_current_user()

    # Проверка существующей регистрации
    if user:
        existing_player = Player.query.filter_by(
            tournament_id=tournament_id,
            user_id=user.id  # Теперь проверяем по user_id
        ).first()
        
        if existing_player:
            return render_template('public/tournaments/tournament_register_already.html', 
                                tournament=tournament, 
                                player=existing_player)

    if not tournament_reg_is_open(tournament):
        return render_template('public/tournaments/registration_closed.html', 
                            tournament=tournament)

    if request.method == 'POST':
        try:
            group_id = request.form.get('group_id')
            
            # Определяем имя и никнейм
            name = request.form.get('name', '').strip()
            nickname = user.pubg_nickname if user else request.form.get('nickname', '').strip()
            
            # Проверка обязательных полей
            if not name:
                flash('Имя обязательно для заполнения', 'error')
                return redirect(url_for('user.player_form', tournament_id=tournament_id))
            
            if not nickname:
                flash('Никнейм обязателен для заполнения', 'error')
                return redirect(url_for('user.player_form', tournament_id=tournament_id))

            # Проверка на дубликат ника
            existing_nickname = Player.query.filter_by(
                tournament_id=tournament_id,
                nickname=nickname
            ).first()

            if existing_nickname:
                flash('Игрок с таким ником уже зарегистрирован на этот турнир.', 'error')
                return redirect(url_for('user.player_form', tournament_id=tournament_id))

            # Для групповых режимов
            if tournament.mode in ['Дуо', 'Сквад']:
                max_players = 4 if tournament.mode == 'Сквад' else 2
                
                # Создание новой группы, если не выбрана
                if not group_id:
                    max_group = db.session.query(func.max(PlayerGroup.group_number)) \
                        .filter_by(tournament_id=tournament_id).scalar() or 0
                    new_group = PlayerGroup(
                        tournament_id=tournament_id,
                        group_number=max_group + 1
                    )
                    db.session.add(new_group)
                    db.session.flush()
                    group_id = new_group.id
                
                # Проверка заполненности группы
                group = PlayerGroup.query.get(group_id)
                if group and len(group.players) >= max_players:
                    flash('Выбранная группа уже заполнена', 'error')
                    return redirect(url_for('user.player_form', tournament_id=tournament_id))

            # Обновляем имя пользователя, если оно было изменено
            if user and user.name != name:
                user.name = name
                db.session.commit()

            # Создаём игрока с привязкой к пользователю
            new_player = Player(
                tournament_id=tournament_id,
                user_id=user.id if user else None,
                group_id=group_id if tournament.mode in ['Дуо', 'Сквад'] else None,
                name=name,
                nickname=nickname
            )

            # Логируем регистрацию
            action = f"Игрок {name} (ник: {nickname}) зарегистрировался на турнир '{tournament.name}'"
            log = AdminActionLog(
                user_id=user.id if user else None,
                action=action
            )

            db.session.add(new_player)
            db.session.add(log)
            db.session.commit()

            session['last_registered_tournament'] = tournament_id
            flash('Вы успешно зарегистрировались на турнир!', 'success')
            return redirect(url_for('public.view_players_public', tournament_id=tournament_id))

        except Exception as e:
            db.session.rollback()
            flash('Произошла ошибка при регистрации. Пожалуйста, попробуйте снова.', 'error')
            return redirect(url_for('user.player_form', tournament_id=tournament_id))

    # Для GET-запроса
    groups = []
    max_players = None
    if tournament.mode in ['Дуо', 'Сквад']:
        groups = PlayerGroup.query \
            .filter_by(tournament_id=tournament_id) \
            .options(db.joinedload(PlayerGroup.players)) \
            .all()
        max_players = 4 if tournament.mode == 'Сквад' else 2

    return render_template(
        'public/tournaments/form.html',
        tournament=tournament,
        groups=groups,
        max_players=max_players,
        current_user=user
    )

    # Для GET-запроса
    groups = []
    max_players = None
    if tournament.mode in ['Дуо', 'Сквад']:
        groups = PlayerGroup.query \
            .filter_by(tournament_id=tournament_id) \
            .options(db.joinedload(PlayerGroup.players)) \
            .all()
        max_players = 4 if tournament.mode == 'Сквад' else 2

    return render_template(
        'public/tournaments/form.html',
        tournament=tournament,
        groups=groups,
        max_players=max_players,
        current_user=user  # Передаем пользователя в шаблон
    )