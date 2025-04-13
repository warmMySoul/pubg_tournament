from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from functools import wraps
from sqlalchemy import func
from flask import send_file
from openpyxl import Workbook
from dotenv import load_dotenv
import os
from io import BytesIO

load_dotenv("secrets.env")  # Загрузить переменные окружения из .env файла

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tournament.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # Получить SECRET_KEY из переменной окружения

# Проверка, если SECRET_KEY не загружен
if not app.config['SECRET_KEY']:
    raise ValueError("SECRET_KEY is not set in the environment variables")

db = SQLAlchemy(app)

# Роли
class RoleEnum:
    ADMIN = 'admin'
    MODERATOR = 'moderator'
    CLAN_MEMBER = 'clan_member'
    GUEST = 'guest'

# Универсальная модель пользователя
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(50), unique=True, nullable=True)
    name = db.Column(db.String(70), nullable=True)
    pubg_nickname = db.Column(db.String(70), unique=True, nullable=False)
    birthday = db.Column(db.DateTime, nullable=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default=RoleEnum.GUEST)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Модель группы
class PlayerGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey('tournament.id'), nullable=False)
    group_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    players = db.relationship('Player', backref='group', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'group_number', name='unique_group_number'),
    )

# Модель турнира
class Tournament(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    reg_start = db.Column(db.DateTime, nullable=False)
    reg_end = db.Column(db.DateTime, nullable=False)
    tournament_date = db.Column(db.DateTime, nullable=False)
    mode = db.Column(db.String(20), nullable=False)
    scoring_system = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    players = db.relationship('Player', backref='tournament', lazy=True, cascade='all, delete-orphan')
    player_groups = db.relationship('PlayerGroup', backref='tournament', lazy=True, cascade='all, delete-orphan')

# Модель игрока
class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey('tournament.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('player_group.id'), nullable=True)
    name = db.Column(db.String(50), nullable=False)
    nickname = db.Column(db.String(50), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)

# Модель логов
class AdminActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='action_logs')

# Система логирования

def log_admin_action(action):
    user_id = session.get('user_logged')
    if user_id:
        log = AdminActionLog(user_id=user_id, action=action)
        db.session.add(log)
        db.session.commit()

# Получение текущего пользователя

def get_current_user():
    user_id = session.get('user_logged')
    return User.query.get(user_id) if user_id else None

# Декоратор для проверки роли

def role_required(required_roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user or user.role not in required_roles:
                flash('Недостаточно прав доступа', 'error')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

# Проверка доступности регистрации

def registration_open(tournament):
    now = datetime.now()
    return tournament.reg_start <= now <= tournament.reg_end

# Добавляем в шаблоны

@app.context_processor
def utility_processor():
    return dict(
        registration_open=registration_open,
        now=datetime.now(),
        current_user=get_current_user()
    )

# Инициализация БД
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password=generate_password_hash(os.getenv('ADMIN_PASS')),
            role=RoleEnum.ADMIN,
            pubg_nickname="admin_user"
        )
        db.session.add(admin)
        db.session.commit()

# Универсальный вход
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_logged'] = user.id
            flash(f"Добро пожаловать, {user.username} ({user.role})", 'success')
            if user.role == RoleEnum.ADMIN:
                return redirect(url_for('admin'))
            return redirect(url_for('home'))
        else:
            flash('Неверные учетные данные', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_logged', None)
    return redirect(url_for('login'))

@app.route('/user_dashboard')
@role_required([RoleEnum.CLAN_MEMBER, RoleEnum.MODERATOR, RoleEnum.GUEST, RoleEnum.ADMIN])
def user_dashboard():
    return render_template('user_dashboard.html', user=get_current_user())

@app.route('/admin')
@role_required([RoleEnum.ADMIN])
def admin():
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
    return render_template('admin.html', tournaments=tournaments)

@app.route('/register', methods=['GET', 'POST'])
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
            log_admin_action(f"Зарегистрирован новый пользователь (гость) '{username}'")
            return redirect(url_for('login'))
    return render_template('register_user.html')

# Защищенные маршруты
@app.route('/')
def home():
    member_count = User.query.filter(User.role == RoleEnum.CLAN_MEMBER).count()
    upcoming_tournaments = Tournament.query.filter(Tournament.tournament_date >= datetime.now()) \
                                           .order_by(Tournament.tournament_date).all()
    return render_template('home.html',
                           member_count=member_count,
                           upcoming_tournaments=upcoming_tournaments)

@app.route('/create', methods=['GET', 'POST'])
@role_required([RoleEnum.ADMIN])
def create_tournament():
    if request.method == 'POST':
        try:
            new_tournament = Tournament(
                id=str(uuid.uuid4()),
                name=request.form['name'],
                reg_start=datetime.strptime(request.form['reg_start'], '%Y-%m-%dT%H:%M'),
                reg_end=datetime.strptime(request.form['reg_end'], '%Y-%m-%dT%H:%M'),
                tournament_date=datetime.strptime(request.form['tournament_date'], '%Y-%m-%dT%H:%M'),
                mode=request.form['mode'],
                scoring_system=request.form['scoring_system']
            )
            
            if new_tournament.reg_start >= new_tournament.reg_end:
                flash('Дата окончания регистрации должна быть позже даты начала', 'error')
                return redirect(url_for('create_tournament'))
            
            db.session.add(new_tournament)
            db.session.commit()
            log_admin_action(f"Создан турнир '{request.form['name'],}'")
            return redirect(url_for('admin'))
        except ValueError as e:
            flash('Ошибка в формате даты', 'error')
    return render_template('create.html')

@app.route('/tournament/<tournament_id>')
@role_required([RoleEnum.ADMIN])
def view_players(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    max_players = 4 if tournament.mode == 'Сквад' else 2 if tournament.mode == 'Дуо' else None
    return render_template('players.html', 
                         tournament=tournament,
                         max_players=max_players)

@app.route('/copy_link/<tournament_id>')
@role_required([RoleEnum.ADMIN])
def copy_link(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    return jsonify({
        'link': url_for('player_form', tournament_id=tournament.id, _external=True)
    })

@app.route('/api/move_player', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def move_player():
    player_id = request.json.get('player_id')
    new_group_id = request.json.get('new_group_id')

    player = Player.query.get_or_404(player_id)
    tournament = Tournament.query.get_or_404(player.tournament_id)

    if tournament.mode not in ['Дуо', 'Сквад']:
        return jsonify({'success': False, 'error': 'Только для режимов Дуо/Сквад'})

    old_group_id = player.group_id

    # Если new_group_id не указан — создаём новую группу с минимально возможным номером
    if not new_group_id:
        used_numbers = set(g.group_number for g in PlayerGroup.query.filter_by(tournament_id=tournament.id).all())
        new_number = 1
        while new_number in used_numbers:
            new_number += 1

        new_group = PlayerGroup(
            tournament_id=tournament.id,
            group_number=new_number
        )
        db.session.add(new_group)
        db.session.flush()  # Получаем ID новой группы
        new_group_id = new_group.id
    else:
        group = PlayerGroup.query.filter_by(id=new_group_id, tournament_id=player.tournament_id).first()
        if not group:
            return jsonify({'success': False, 'error': 'Группа не найдена'})

        max_players = 4 if tournament.mode == 'Сквад' else 2
        if len(group.players) >= max_players:
            return jsonify({'success': False, 'error': 'Группа уже заполнена'})

    player.group_id = new_group_id
    log_admin_action(f"В трунирне '{tournament.name}' игрок '{player.name}' ({player.nickname}) перемещен в '{player.group_id }'")
    db.session.commit()

    # Проверка и удаление старой группы, если она пуста
    if old_group_id:
        old_group = PlayerGroup.query.get(old_group_id)
        if old_group and len(old_group.players) == 0:
            db.session.delete(old_group)
            db.session.commit()

    return jsonify({'success': True})


@app.route('/api/delete_tournament', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def delete_tournament():
    data = request.json
    tournament_id = data.get('tournament_id')
    confirm = data.get('confirm')

    if not confirm:
        return jsonify({'success': False, 'error': 'Требуется подтверждение'})

    tournament = Tournament.query.get_or_404(tournament_id)
    db.session.delete(tournament)
    db.session.commit()
    log_admin_action(f"Удален турнир {tournament.name}'")

    return jsonify({'success': True})

@app.route('/form/<tournament_id>', methods=['GET', 'POST'])
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
            flash(f'Вы уже зарегистрированы на турнир "{tournament.name}" как {existing_player.nickname}.', 'info')
            return render_template('tournament_register_already.html', tournament=tournament, player=existing_player)

    if not registration_open(tournament):
        return render_template('registration_closed.html', tournament=tournament)

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
        if user and user.role == RoleEnum.CLAN_MEMBER:
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
            return redirect(url_for('player_form', tournament_id=tournament_id))

        # Создаём игрока
        new_player = Player(
            tournament_id=tournament_id,
            group_id=group_id if tournament.mode in ['Дуо', 'Сквад'] else None,
            name=name,
            nickname=nickname,
            user_id=log_user_id  # Здесь привязываем игрока к текущему пользователю
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
        return redirect(url_for('view_players_public', tournament_id=tournament_id))


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
        'form.html',
        tournament=tournament,
        groups=groups,
        max_players=max_players
    )

@app.route('/public/tournament/<tournament_id>')
def view_players_public(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    players = Player.query.filter_by(tournament_id=tournament_id).order_by(Player.registered_at.desc()).all()
    just_registered = session.get('last_registered_tournament') == tournament_id
    if just_registered:
        session.pop('last_registered_tournament', None)
    
    max_players = 4 if tournament.mode == 'Сквад' else 2 if tournament.mode == 'Дуо' else None
    
    return render_template('players_public.html', 
                         tournament=tournament, 
                         players=players,
                         just_registered=just_registered,
                         max_players=max_players)



@app.route('/users')
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def users_list():
    users = User.query.all()
    return render_template('users_list.html', users=users)

@app.route('/api/delete_user', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def delete_user():
    data = request.json
    user_id = data.get('user_id')
    confirm = data.get('confirm')

    if not confirm:
        return jsonify({'success': False, 'error': 'Требуется подтверждение'})

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    log_admin_action(f"Удален пользователь '{user.username}'")
    db.session.commit()

    return jsonify({'success': True})

@app.route('/api/delete_player', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def delete_player():
    data = request.get_json()
    player_id = data.get('player_id')

    player = Player.query.get(player_id)
    if not player:
        return jsonify({'success': False, 'error': 'Игрок не найден'})

    tournament = player.tournament
    group = player.group  # Может быть None (в режиме Соло)

    db.session.delete(player)

    # Проверка на удаление пустой группы для Дуо и Сквад
    if group and tournament.mode in ['Дуо', 'Сквад']:
        remaining_players = Player.query.filter_by(group_id=group.id).count()
        if remaining_players == 0:
            db.session.delete(group)

    log_admin_action(f"Удален игрок '{player.name}' ({player.nickname}) из турнира '{tournament.name}'")

    db.session.commit()
    return jsonify({'success': True})


@app.route('/logs')
@role_required([RoleEnum.ADMIN])
def view_logs():
    admin_username = request.args.get('admin')
    action_contains = request.args.get('action')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    filter_by = request.args.get('admin_filter', 'all')

    query = AdminActionLog.query

    if filter_by == 'admins':
        query = query.join(User).filter(User.role == RoleEnum.ADMIN)
    elif filter_by == 'moderator':
        query = query.join(User).filter(User.role == RoleEnum.MODERATOR)
    elif filter_by == 'clan_member':
        query = query.join(User).filter(User.role == RoleEnum.CLAN_MEMBER)
    elif filter_by == 'guests':
        query = query.filter(AdminActionLog.user_id == None)

    if admin_username:
        query = query.join(User).filter(User.username.ilike(f'%{admin_username}%'))

    if action_contains:
        query = query.filter(AdminActionLog.action.ilike(f'%{action_contains}%'))

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AdminActionLog.timestamp >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(AdminActionLog.timestamp <= dt_to)
        except ValueError:
            pass

    query = query.order_by(AdminActionLog.timestamp.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    logs = pagination.items

    return render_template('logs.html', logs=logs, pagination=pagination)


@app.route('/export_logs')
@role_required([RoleEnum.ADMIN])
def export_logs():
    admin_username = request.args.get('admin')
    action_contains = request.args.get('action')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    filter_by = request.args.get('admin_filter', 'all')

    query = AdminActionLog.query.outerjoin(User).order_by(AdminActionLog.timestamp.desc())

    # Фильтры
    if filter_by == 'admins':
        query = query.filter(AdminActionLog.admin_id != None)
    elif filter_by == 'guests':
        query = query.filter(AdminActionLog.admin_id == None)

    if admin_username:
        query = query.filter(User.username.ilike(f'%{admin_username}%'))

    if action_contains:
        query = query.filter(AdminActionLog.action.ilike(f'%{action_contains}%'))

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AdminActionLog.timestamp >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(AdminActionLog.timestamp <= dt_to)
        except ValueError:
            pass

    logs = query.all()

    # Создаём Excel-файл
    wb = Workbook()
    ws = wb.active
    ws.title = "Журнал действий"

    # Заголовки
    ws.append(['Дата и время', 'Администратор', 'Действие'])

    for log in logs:
        ws.append([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.admin.username if log.admin else 'Гость',
            log.action
        ])

    # Сохраняем в байтовый поток
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='admin_logs.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/profile', methods=['GET', 'POST'])
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
                return redirect(url_for('profile'))

        if current_password and new_password:
            if not check_password_hash(user.password, current_password):
                flash('Текущий пароль неверен', 'error')
                return redirect(url_for('profile'))
            elif len(new_password) < 6 or len(new_password) > 30:
                flash('Новый пароль должен быть от 6 до 30 символов', 'error')
                return redirect(url_for('profile'))
            else:
                user.password = generate_password_hash(new_password)
                log_admin_action(f"Пользователь {user.username} сменил пароль")

        db.session.commit()
        flash('Профиль успешно обновлён', 'success')
        log_admin_action(f"Обновил свой профиль")
        return redirect(url_for('profile'))

    return render_template('profile.html', user=user)

@app.route('/api/edit_user', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def edit_user():
    data = request.json
    user = User.query.get_or_404(data['user_id'])

    if user.id == get_current_user().id:
        return jsonify({'success': False, 'error': 'Нельзя редактировать самого себя через это окно.'})

    user.pubg_nickname = data.get('pubg_nickname', user.pubg_nickname)
    user.name = data.get('name')
    user.role = data.get('role')

    birthday = data.get('birthday')
    if birthday:
        try:
            user.birthday = datetime.strptime(birthday, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Неверный формат даты'})

    db.session.commit()
    log_admin_action(f"Изменены данные пользователя {user.username}")
    return jsonify({'success': True})

@app.route('/api/edit_tournament', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def edit_tournament():
    data = request.json
    if not data.get('confirm'):
        return jsonify({'success': False, 'error': 'Требуется подтверждение'})

    tournament = Tournament.query.get_or_404(data['tournament_id'])

    try:
        tournament.name = data['name']
        tournament.mode = data['mode']
        tournament.reg_start = datetime.strptime(data['reg_start'], '%Y-%m-%dT%H:%M')
        tournament.reg_end = datetime.strptime(data['reg_end'], '%Y-%m-%dT%H:%M')
        tournament.tournament_date = datetime.strptime(data['tournament_date'], '%Y-%m-%dT%H:%M')

        db.session.commit()
        log_admin_action(f"Изменён турнир '{tournament.name}'")
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True)