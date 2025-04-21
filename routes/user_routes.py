from flask import Blueprint, flash, url_for, redirect, session, request, render_template
from datetime import datetime
from extensions.security import role_required, get_current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from pubg_api.models.player import ParsedPlayerStats
from utils.helpers import registration_open as tournament_reg_is_open
from models import RoleEnum, User, Tournament, Player, PlayerGroup, AdminActionLog, PlayerStats
from db_connection import db

# Импорт PUBG API
from pubg_api.client import PUBGApiClient

client = PUBGApiClient()


# Импорт логирования
from services.admin_log_service import log_admin_action as log

user_bp = Blueprint('user', __name__, url_prefix='/user')


@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get_or_404(session['user_logged'])
    player_stats = None
    updated_at = None

    if(user.username != "admin"):

        # Проверяем, есть ли сохраненные данные в PlayerStats
        cached_stats = PlayerStats.query.filter_by(user_id=user.id).first()
        
        if cached_stats:
            # Если есть кешированная статистика, берем pubg_id из таблицы
            try:
                player_stats = ParsedPlayerStats.from_json(cached_stats.stats_json)
                updated_at = cached_stats.updated_at            
            except Exception as e:
                flash(f"Возникли ошибки при загрузке статистики. Попробуйте позже.", 'warning')
        else:
            # Если нет кешированных данных, получаем через API
            try:
                player = client.get_player_by_name(user.pubg_nickname)
                if player:
                    try:
                        player_stats = client.get_player_lifetime_stats_by_id(player.id)
                        
                        # Сохраняем данные в PlayerStats
                        cached_stats = PlayerStats(
                            user_id=user.id,
                            pubg_id=player.id,
                            stats_json=player_stats.to_dict()
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
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')

        user.name = request.form.get('name')
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

        try:
            db.session.commit()
            flash('Профиль успешно обновлён', 'success')
            log(f"Обновил свой профиль")
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении профиля. Проверьте данные.', 'error')

        return redirect(url_for('user.profile'))

    return render_template('user/profile.html', 
                         user=user, 
                         stats=player_stats, 
                         updated_at=updated_at)

# Авторизация
@user_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_logged'] = user.id
            flash(f"Добро пожаловать, {user.username} ({user.role})", 'success')
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
            return redirect(url_for('user.login'))
    return render_template('user/register_user.html')

@user_bp.route('/form/<tournament_id>', methods=['GET', 'POST'])
@login_required
def player_form(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    user = get_current_user()

    # Проверка, если пользователь уже зарегистрирован на турнир
    if user:
        existing_player = Player.query.filter_by(
            tournament_id=tournament_id,
            nickname=user.pubg_nickname  # Мы предполагаем, что у игрока есть связь с пользователем через user_id
        ).first()
        
        if existing_player:
            # Если игрок уже зарегистрирован, выводим информацию
            return render_template('public/tournaments/tournament_register_already.html', tournament=tournament, player=existing_player)

    if not tournament_reg_is_open(tournament):
        return render_template('public/tournaments/registration_closed.html', tournament=tournament)

    if request.method == 'POST':
        group_id = request.form.get('group_id')
        max_players = 4 if tournament.mode == 'Сквад' else 2 if tournament.mode == 'Дуо' else None

        # Создание новой группы, если не выбрана
        if tournament.mode in ['Дуо', 'Сквад'] and not group_id:
            max_group = db.session.query(func.max(PlayerGroup.group_number)) \
                .filter_by(tournament_id=tournament_id).scalar() or 0
            new_group = PlayerGroup(
                tournament_id=tournament_id,
                group_number=max_group + 1
            )
            db.session.add(new_group)
            db.session.flush()
            group_id = new_group.id

        # Определяем имя и никнейм
        if user:
            name = user.name
            nickname = user.pubg_nickname
            log_user_id = user.id
            
            if not user.name:
                user.name = name
                db.session.commit()
        else:
            name = request.form.get('name')
            nickname = request.form.get('nickname')
            log_user_id = None  # гость

        # Проверка на дубликат ника в текущем турнире
        existing_player = Player.query.filter_by(
            tournament_id=tournament_id,
            nickname=nickname
        ).first()

        if existing_player:
            flash('Игрок с таким ником уже зарегистрирован на этот турнир.', 'error')
            return redirect(url_for('user.player_form', tournament_id=tournament_id))

        # Создаём игрока
        new_player = Player(
            tournament_id=tournament_id,
            group_id=group_id if tournament.mode in ['Дуо', 'Сквад'] else None,
            name=name,
            nickname=nickname
        )

        # Логируем регистрацию
        action = f"Игрок {new_player.name} (ник: {new_player.nickname}) зарегистрировался на турнир '{tournament.name}'"
        log = AdminActionLog(
            user_id=log_user_id,
            action=action
        )

        db.session.add(new_player)
        db.session.add(log)
        db.session.commit()

        session['last_registered_tournament'] = tournament_id
        return redirect(url_for('public.view_players_public', tournament_id=tournament_id))


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
        max_players=max_players
    )
