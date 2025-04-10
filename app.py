from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from functools import wraps
from sqlalchemy import func
from io import StringIO
from flask import make_response
import csv
from flask import send_file
from openpyxl import Workbook
from io import BytesIO

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tournament.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dd1119a7-a123-457d-add4-26b68f83f9f8'
db = SQLAlchemy(app)

# Модель администратора
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
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
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship('Admin', backref='action_logs')

# Система логирования
def log_admin_action(action):
    admin_id = session.get('admin_logged')
    if admin_id:
        log = AdminActionLog(admin_id=admin_id, action=action)
        db.session.add(log)
        db.session.commit()


# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged' not in session:
            flash('Требуется авторизация', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Проверка доступности регистрации
def registration_open(tournament):
    now = datetime.now()
    return tournament.reg_start <= now <= tournament.reg_end

# Добавляем функцию в контекст шаблонов
@app.context_processor
def utility_processor():
    return dict(
        registration_open=registration_open,
        now=datetime.now()
    )

# Инициализация БД
with app.app_context():
    db.create_all()
    if not Admin.query.first():
        admin = Admin(
            username='admin',
            password=generate_password_hash('Njk,tkdfhgfk')
        )
        db.session.add(admin)
        db.session.commit()

# Маршруты аутентификации
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and check_password_hash(admin.password, password):
            session['admin_logged'] = admin.id
            log_admin_action(f"Вход в систему")
            return redirect(url_for('admin'))
        flash('Неверные учетные данные', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('admin_logged', None)
    return redirect(url_for('login'))

@app.route('/register_admin', methods=['GET', 'POST'])
@login_required
def register_admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if Admin.query.filter_by(username=username).first():
            flash('Это имя пользователя уже занято', 'error')
        else:
            admin = Admin(
                username=username,
                password=generate_password_hash(password)
            )
            db.session.add(admin)
            db.session.commit()
            flash('Новый администратор успешно зарегистрирован', 'success')
            log_admin_action(f"Добавлен администратор '{username}'")
            return redirect(url_for('admin'))
    return render_template('register_admin.html')

# Защищенные маршруты
@app.route('/')
@login_required
def admin():
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
    return render_template('admin.html', tournaments=tournaments)

@app.route('/create', methods=['GET', 'POST'])
@login_required
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
@login_required
def view_players(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    max_players = 4 if tournament.mode == 'Сквад' else 2 if tournament.mode == 'Дуо' else None
    return render_template('players.html', 
                         tournament=tournament,
                         max_players=max_players)

@app.route('/copy_link/<tournament_id>')
@login_required
def copy_link(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    return jsonify({
        'link': url_for('player_form', tournament_id=tournament.id, _external=True)
    })

@app.route('/api/move_player', methods=['POST'])
@login_required
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
@login_required
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

# Публичные маршруты
@app.route('/form/<tournament_id>', methods=['GET', 'POST'])
def player_form(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if not registration_open(tournament):
        return render_template('registration_closed.html', tournament=tournament)
    
    if request.method == 'POST':
        group_id = request.form.get('group_id')
        max_players = 4 if tournament.mode == 'Сквад' else 2 if tournament.mode == 'Дуо' else None
        
        if tournament.mode in ['Дуо', 'Сквад'] and not group_id:
            # Создаем новую группу
            max_group = db.session.query(func.max(PlayerGroup.group_number))\
                          .filter_by(tournament_id=tournament_id).scalar() or 0
            new_group = PlayerGroup(
                tournament_id=tournament_id,
                group_number=max_group + 1
            )
            db.session.add(new_group)
            db.session.flush()
            group_id = new_group.id
        
        new_player = Player(
            tournament_id=tournament_id,
            group_id=group_id if tournament.mode in ['Дуо', 'Сквад'] else None,
            name=request.form['name'],
            nickname=request.form['nickname']
        )
        action = f"Игрок {new_player.name} (ник: {new_player.nickname}) зарегистрировался на турнир '{tournament.name}'"
        log = AdminActionLog(
        admin_id=None,  # пользователь не авторизован
        action=action)       
        db.session.add(log)
        db.session.add(new_player)
        db.session.commit()
        
        session['last_registered_tournament'] = tournament_id
        return redirect(url_for('view_players_public', tournament_id=tournament_id))
    
    groups = []
    max_players = None
    if tournament.mode in ['Дуо', 'Сквад']:
        groups = PlayerGroup.query\
            .filter_by(tournament_id=tournament_id)\
            .options(db.joinedload(PlayerGroup.players))\
            .all()
        max_players = 4 if tournament.mode == 'Сквад' else 2
    
    return render_template('form.html', 
                         tournament=tournament,
                         groups=groups,
                         max_players=max_players)

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



@app.route('/admins')
@login_required
def admins():
    admins = Admin.query.all()
    return render_template('admins_list.html', admins=admins)

@app.route('/api/delete_admin', methods=['POST'])
@login_required
def delete_admin():
    data = request.json
    admin_id = data.get('admin_id')
    confirm = data.get('confirm')

    if not confirm:
        return jsonify({'success': False, 'error': 'Требуется подтверждение'})

    admin = Admin.query.get_or_404(admin_id)
    db.session.delete(admin)
    log_admin_action(f"Удален администратор '{admin.username}'")
    db.session.commit()

    return jsonify({'success': True})

@app.route('/api/delete_player', methods=['POST'])
@login_required
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
@login_required
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
        query = query.filter(AdminActionLog.admin_id != None)
    elif filter_by == 'guests':
        query = query.filter(AdminActionLog.admin_id == None)

    if admin_username:
        query = query.join(Admin).filter(Admin.username.ilike(f'%{admin_username}%'))

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
@login_required
def export_logs():
    admin_username = request.args.get('admin')
    action_contains = request.args.get('action')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    filter_by = request.args.get('admin_filter', 'all')

    query = AdminActionLog.query.outerjoin(Admin).order_by(AdminActionLog.timestamp.desc())

    # Фильтры
    if filter_by == 'admins':
        query = query.filter(AdminActionLog.admin_id != None)
    elif filter_by == 'guests':
        query = query.filter(AdminActionLog.admin_id == None)

    if admin_username:
        query = query.filter(Admin.username.ilike(f'%{admin_username}%'))

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



if __name__ == '__main__':
    app.run(debug=False)