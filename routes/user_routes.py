from zoneinfo import ZoneInfo
from flask import Blueprint, flash, jsonify, url_for, redirect, session, request, render_template
from datetime import datetime, timedelta
from extensions.security import get_client_ip, is_safe_url, role_required, get_current_user, login_required, get_cipher
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import and_, func
from pubg_api.models.player import ParsedPlayerStats
from services.verification_service import generate_verification_code, send_email, send_verification_email
from utils.helpers import mask_email
from models import RoleEnum, User, Tournament, Player, PlayerGroup, AdminActionLog, PlayerStats, JoinRequests, RqStatusEnum, IPStatusEnum
from extensions.db_connection import db

# Импорт PUBG API
from pubg_api.client import PUBGApiClient
client = PUBGApiClient()


# Импорт логирования
from services.admin_log_service import log_admin_action as log, log_ip

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

            if (current_password == new_password):
                flash('Пароли не должны совпадать', 'error')
                return redirect(url_for('user.profile'))
            
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

# Авторизация
@user_bp.route('/login', methods=['POST'])
def login():
    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password, password):
            return jsonify({
                'success': False,
                'message': 'Неверные учетные данные'
            }), 401

        # Успешная авторизация
        session['user_logged'] = user.id

        ip_address = get_client_ip()
        log_ip(IPStatusEnum.LOGIN, ip_address)

        # Получаем URL для перенаправления из разных источников
        next_url = (
            request.form.get('next') or 
            request.referrer or  # Страница, с которой пришел пользователь
            url_for('public.home')
        )

        # Проверка безопасного URL для перенаправления
        if next_url and is_safe_url(next_url):
            redirect_url = next_url
        else:
            redirect_url = url_for('public.home')

        return jsonify({
            'success': True,
            'message': f"Добро пожаловать, {user.username} ({user.role})",
            'redirect': redirect_url,  # Возвращаем URL для перенаправления
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role,
                'birthday': user.birthday if (user.birthday) else None
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Произошла ошибка при авторизации. Повторите позже'
        }), 500

# Выход
@user_bp.route('/logout')
@login_required
def logout():
    session.pop('user_logged', None)
    flash("Вы вышли из системы", 'success')
    return redirect(url_for('public.home'))

# Регистрация
@user_bp.route('/register', methods=['POST'])
def register_user():
    cipher = get_cipher()

    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        pubg_nickname = request.form.get('pubg_nickname', '').strip()
        email = request.form.get('email', '').strip().lower()

        # Валидация данных
        if not all([username, password, pubg_nickname, email]):
            return jsonify({
                'success': False, 
                'message': 'Все поля обязательны для заполнения'
            }), 400

        # Проверка уникальности
        if User.query.filter_by(username=username).first():
            return jsonify({
                'success': False,
                'message': 'Это имя пользователя уже занято'
            }), 400

        if User.query.filter_by(email=email).first():
            return jsonify({
                'success': False,
                'message': 'Этот email уже используется'
            }), 400
        
        if User.query.filter_by(pubg_nickname=pubg_nickname).first():
            return jsonify({
                'success': False,
                'message': 'Этот ник PUBG уже зарегистрирован'
            }), 400

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
        
        return jsonify({
            'success': True,
            'message': 'Код подтверждения отправлен на ваш email',
            'redirect': url_for('public.home')  # Перенаправление после подтверждения
        })

    except Exception as e:
        print(e)
        return jsonify({
            'success': False,
            'message': f'Произошла ошибка при регистрации: проверьте указанную почту или свяжитесь с администратором'
        }), 500


# Подтверждение email (AJAX версия)
@user_bp.route('/verify-email', methods=['POST'])
def verify_email_ajax():
    cipher = get_cipher()
    
    if 'temp_user' not in session:
        return jsonify({
            'success': False,
            'message': 'Сессия истекла или не найдена. Пожалуйста, зарегистрируйтесь снова.'
        }), 400

    entered_code = request.form.get('verification_code', '').strip()
    
    try:
        encrypted_code = session.get('encrypted_code')
        expires = datetime.fromisoformat(session.get('code_expires', ''))
        
        if not encrypted_code:
            return jsonify({
                'success': False,
                'message': 'Код подтверждения не найден'
            }), 400
            
        if datetime.now(ZoneInfo("Europe/Moscow")) > expires:
            return jsonify({
                'success': False,
                'message': 'Срок действия кода истек'
            }), 400
            
        decrypted_code = cipher.decrypt(encrypted_code).decode()
        
        if decrypted_code == entered_code:
            temp_user = session['temp_user']
            new_user = User(
                username=temp_user['username'],
                password=temp_user['password'],
                pubg_nickname=temp_user['pubg_nickname'],
                email=temp_user['email'],
                is_verified=True
            )

            # Проверка клана
            try:
                player = client.get_player_by_name(temp_user['pubg_nickname']) or None
                if player:
                    try:
                        if player.clan_id == "clan.ad9293ce262f4c9e847ef73b3f2190b3":
                            new_user.role = RoleEnum.CLAN_MEMBER
                    except Exception as e:
                        print("Ошибка автоматической установки роли пользователя")
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Неверный ник PUBG. Повторите попытку и проверьте правильность ввода.'
                }), 500
           
            
            db.session.add(new_user)
            db.session.commit()
            
            # Очищаем сессию
            session.pop('temp_user', None)
            session.pop('encrypted_code', None)
            session.pop('code_expires', None)
            
            # Авторизуем пользователя сразу после подтверждения
            session['user_logged'] = new_user.id

            ip_address = get_client_ip()
            log_ip(IPStatusEnum.REG, ip_address)
            
            return jsonify({
                'success': True,
                'message': 'Регистрация завершена успешно!',
                'redirect': url_for('public.home')
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Неверный код подтверждения'
            }), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Ошибка при подтверждении email. Попробуйте позже'
        }), 500

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
        return redirect(url_for('user.verify_email_ajax'))
    
    except Exception as e:
        flash('Произошла ошибка при отправке кода', 'error')
        return redirect(url_for('user.register_user'))

# Восстановление пароля - шаг 1 (запрос)
@user_bp.route('/forgot-password', methods=['POST'])
def forgot_password_ajax():
    cipher = get_cipher()
    
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    
    user = User.query.filter_by(username=username, email=email).first()
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'Пользователь с такими данными не найден'
        }), 404
    
    # Генерация и отправка кода
    verification_code = generate_verification_code()
    encrypted_code = cipher.encrypt(verification_code.encode())
    
    session['password_reset'] = {
        'user_id': user.id,
        'encrypted_code': encrypted_code,
        'expires': (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(minutes=30)).isoformat()
    }
    
    send_verification_email(user.email, verification_code)
    
    return jsonify({
        'success': True,
        'message': 'Код подтверждения отправлен на вашу почту'
    })

# Восстановление пароля - шаг 2 (Смена пароля)
@user_bp.route('/reset-password', methods=['POST'])
def reset_password_ajax():
    cipher = get_cipher()
    
    reset_data = session.get('password_reset')
    if not reset_data:
        return jsonify({
            'success': False,
            'message': 'Сессия истекла или не найдена'
        }), 400
    
    entered_code = request.form.get('verification_code', '').strip()
    new_password = request.form.get('new_password', '').strip()
    
    if datetime.now(ZoneInfo("Europe/Moscow")) > datetime.fromisoformat(reset_data['expires']):
        return jsonify({
            'success': False,
            'message': 'Срок действия кода истек'
        }), 400
    
    if len(new_password) < 6 or len(new_password) > 30:
        return jsonify({
            'success': False,
            'message': 'Пароль должен быть от 6 до 30 символов'
        }), 400
    
    try:
        decrypted_code = cipher.decrypt(reset_data['encrypted_code']).decode()
        if decrypted_code == entered_code:
            user = User.query.get(reset_data['user_id'])
            user.password = generate_password_hash(new_password)
            db.session.commit()
            
            session.pop('password_reset', None)
            log(f"Пользователь {user.username} восстановил пароль")
            
            return jsonify({
                'success': True,
                'message': 'Пароль успешно изменён. Теперь вы можете войти.'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Неверный код подтверждения'
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Ошибка при проверке кода'
        }), 500

# Форма регистрации на турнир
@user_bp.route('/form/<tournament_id>', methods=['GET', 'POST'])
@login_required
def player_form(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    user = get_current_user()


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
            if tournament.mode in ['DUO', 'SQUAD']:
                max_players = 4 if tournament.mode == 'SQUAD' else 2
                if group_id == "new_group": # Создание новой группы
                    max_group = db.session.query(func.max(PlayerGroup.group_number)) \
                        .filter_by(tournament_id=tournament_id).scalar() or 0
                    new_group = PlayerGroup(
                        tournament_id=tournament_id,
                        group_number=max_group + 1
                    )
                    db.session.add(new_group)
                    db.session.flush()
                    group_id = new_group.id

                elif group_id == "random_group": # Выбор случайно группы группы
                    random_group = (PlayerGroup.query
                            .join(PlayerGroup.players)
                            .filter(and_(
                                PlayerGroup.tournament_id == tournament_id
                            ))
                            .group_by(PlayerGroup.id)
                            .having(func.count(PlayerGroup.players) < max_players)
                            .order_by(func.random())
                            .first())

                    if random_group:
                        group_id = random_group.id
                    else:
                        group_id = None
                else:
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
                group_id=group_id if tournament.mode in ['DUO', 'SQUAD'] else None,
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

            flash('Вы успешно зарегистрировались на турнир!', 'success')
            return redirect(url_for('public.tournament_details', tournament_id=tournament_id))

        except Exception as e:
            print(e)
            db.session.rollback()
            flash('Произошла ошибка при регистрации. Пожалуйста, попробуйте снова.', 'error')
            return redirect(url_for('user.player_form', tournament_id=tournament_id))

    # Для GET-запроса
    groups = []
    max_players = None
    if tournament.mode in ['DUO', 'SQUAD']:
        groups = PlayerGroup.query \
            .filter_by(tournament_id=tournament_id) \
            .options(db.joinedload(PlayerGroup.players)) \
            .all()
        max_players = 4 if tournament.mode == 'SQUAD' else 2

    now = datetime.now()
    # Определяем статус турнира
    if tournament.reg_start < now and tournament.reg_end > now:
        registration_status = 'open'
    elif tournament.reg_end < now:
        if tournament.tournament_date < now:
            registration_status = "ended"
        else:
            registration_status = 'closed'
    else:
        registration_status = 'soon'

    # Проверка существующей регистрации
    if user:
        existing_player = Player.query.filter_by(
            tournament_id=tournament_id,
            user_id=user.id
        ).first()

    return render_template(
        'public/tournaments/form.html',
        tournament=tournament,
        registration_status=registration_status,
        existing_player=existing_player,
        groups=groups,
        max_players=max_players,
        current_user=user
    )

# Отправка кода подтверждения для удаления регистрации
@user_bp.route('/send-delete-code', methods=['POST'])
@login_required
def send_delete_code():
    cipher = get_cipher()

    try:
        data = request.get_json()
        tournament_id = data.get('tournament_id')
        player_id = data.get('player_id')
        
        user = get_current_user()
        tournament = Tournament.query.get_or_404(tournament_id)
        player = Player.query.filter_by(
            id=player_id,
            tournament_id=tournament_id,
            user_id=user.id
        ).first_or_404()

        # Генерация, шифрование и сохранение кода
        verification_code = generate_verification_code()
        encrypted_code = cipher.encrypt(verification_code.encode())
        
        # Сохраняем данные для удаления в сессии
        session['delete_data'] = {
            'tournament_id': tournament_id,
            'player_id': player_id,
            'user_id': user.id
        }
        session['delete_encrypted_code'] = encrypted_code
        session['delete_code_expires'] = (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(minutes=5)).isoformat()

        # Отправка письма
        send_verification_email(user.email, verification_code)
        
        return jsonify({
            'success': True,
            'message': 'Код подтверждения отправлен на ваш email'
        })
        
    except Exception as e:
        print(f"Send delete code error: {e}")
        return jsonify({
            'success': False,
            'message': 'Произошла ошибка при отправке кода'
        }), 500

# Удаление регистрации с подтверждением
@user_bp.route('/delete-registration', methods=['POST'])
@login_required
def delete_registration():
    cipher = get_cipher()
    
    if 'delete_data' not in session:
        return jsonify({
            'success': False,
            'message': 'Сессия истекла или не найдена. Пожалуйста, запросите код подтверждения снова.'
        }), 400

    entered_code = request.form.get('verification_code', '').strip()
    tournament_id = request.form.get('tournament_id')
    player_id = request.form.get('player_id')
    
    try:
        # Проверяем соответствие данных
        delete_data = session.get('delete_data')
        if (str(delete_data['tournament_id']) != str(tournament_id) or 
            str(delete_data['player_id']) != str(player_id)):
            return jsonify({
                'success': False,
                'message': 'Несоответствие данных. Пожалуйста, запросите новый код.'
            }), 400

        encrypted_code = session.get('delete_encrypted_code')
        expires = datetime.fromisoformat(session.get('delete_code_expires', ''))
        
        if not encrypted_code:
            return jsonify({
                'success': False,
                'message': 'Код подтверждения не найден'
            }), 400
            
        if datetime.now(ZoneInfo("Europe/Moscow")) > expires:
            return jsonify({
                'success': False,
                'message': 'Срок действия кода истек'
            }), 400
            
        decrypted_code = cipher.decrypt(encrypted_code).decode()
        
        if decrypted_code == entered_code:
            # Находим и удаляем запись
            player = Player.query.filter_by(
                id=player_id,
                tournament_id=tournament_id,
                user_id=delete_data['user_id']
            ).first_or_404()

            anotherGroupPlayer = Player.query.filter(
                Player.group_id == player.group_id,
                Player.id != player.id
            ).all()
            group = PlayerGroup.query.get(player.group_id)
            if (not anotherGroupPlayer):
                db.session.delete(group)
            
            tournament = Tournament.query.get_or_404(tournament_id)
            
            # Логируем удаление
            action = f"Игрок {player.name} (ник: {player.nickname}) удалил регистрацию с турнира '{tournament.name}'"
            log = AdminActionLog(
                user_id=delete_data['user_id'],
                action=action
            )
            
            db.session.delete(player)
            db.session.add(log)
            db.session.commit()
            
            # Очищаем сессию
            session.pop('delete_data', None)
            session.pop('delete_encrypted_code', None)
            session.pop('delete_code_expires', None)
            
            return jsonify({
                'success': True,
                'message': 'Ваша регистрация на турнир успешно удалена'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Неверный код подтверждения'
            }), 400
            
    except Exception as e:
        print(f"Delete registration error: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Произошла ошибка при удалении регистрации'
        }), 500

# Повторная отправка кода для удаления
@user_bp.route('/resend-delete-code', methods=['POST'])
@login_required
def resend_delete_code():
    cipher = get_cipher()

    try:
        data = request.get_json()
        tournament_id = data.get('tournament_id')
        player_id = data.get('player_id')
        
        user = get_current_user()
        
        # Проверяем существование записи
        player = Player.query.filter_by(
            id=player_id,
            tournament_id=tournament_id,
            user_id=user.id
        ).first_or_404()

        # Генерация нового кода
        new_code = generate_verification_code()
        encrypted_code = cipher.encrypt(new_code.encode())
        
        # Обновление данных в сессии
        session['delete_data'] = {
            'tournament_id': tournament_id,
            'player_id': player_id,
            'user_id': user.id
        }
        session['delete_encrypted_code'] = encrypted_code
        session['delete_code_expires'] = (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(minutes=5)).isoformat()

        # Отправка письма
        send_verification_email(user.email, new_code)
        
        return jsonify({
            'success': True,
            'message': 'Новый код подтверждения отправлен на ваш email'
        })
    
    except Exception as e:
        print(f"Resend delete code error: {e}")
        return jsonify({
            'success': False,
            'message': 'Произошла ошибка при отправке кода'
        }), 500

# Подача заявки в клан
@user_bp.route('/join-clan-request', methods=['POST'])
@login_required
def join_clan_request():
    try:
        # Проверяем, что пользователь авторизован (декоратор уже проверил)
        user = get_current_user()
        if not user:
            return jsonify({
                'success': False,
                'message': 'Пользователь не найден'
            }), 401

        name = request.form.get('name', '').strip()
        birthday = request.form.get('birthday', '').strip()
        info = request.form.get('info', '').strip()
        know_from = request.form.get('know_from_optional', '').strip()
        agree_rules = request.form.get('agree_rules') == 'on'

        # Проверка обязательных полей
        if not all([name, birthday, info]) or not agree_rules:
            return jsonify({
                'success': False,
                'message': 'Все поля обязательны для заполнения'
            }), 400

        # Формирование содержимого письма
        email_body = f"""
        Новая заявка на вступление в клан:
        
        Пользователь: {user.username} (ID: {user.id})
        Имя: {name}
        Дата рождения: {birthday}
        Информация о себе: {info}
        Узнал о клане из/от: {know_from}
        Согласие с правилами: {'Да' if agree_rules else 'Нет'}
        
        Дата подачи заявки: {datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M')}
        """

        # Отправка письма
        send_email(
            to="goldenbulls.requests@mail.ru",
            subject=f"Новая заявка в клан от {user.username}",
            body=email_body
        )

        try:
            birthday_date = datetime.strptime(birthday, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Неверный формат даты рождения. Используйте формат ГГГГ-ММ-ДД'
            }), 400

        new_join_rq = JoinRequests(
                        user_id = user.id,
                        user_info = info,
                        know_from = know_from,
                        desired_role = 1,
                        status = RqStatusEnum.REVIEW
                    )
        
        if not user.name: 
            user.name = name
        if not user.birthday:
            user.birthday = birthday_date

        db.session.add(new_join_rq)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Ваша заявка успешно отправлена! Мы свяжемся с вами в ближайшее время.'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Произошла ошибка при отправке заявки, сообщите администратору об ошибке'
        }), 500