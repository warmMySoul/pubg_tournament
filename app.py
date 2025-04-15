from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from werkzeug.security import generate_password_hash
from sqlalchemy import func
from dotenv import load_dotenv
import os

load_dotenv("secrets.env")  # Загрузить переменные окружения из .env файла

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tournament.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # Получить SECRET_KEY из переменной окружения

# Проверка, если SECRET_KEY не загружен
if not app.config['SECRET_KEY']:
    raise ValueError("SECRET_KEY is not set in the environment variables")

# Подключение к БД
from db_connection import db
db.init_app(app)

# Импорт моделей
from models import *

# Импорт логирования
from services.admin_log_service import log_admin_action as log

# Импорт утилитов
from utils.helpers import registration_open as tournament_reg_is_open

# Импорт инструментов безопасности (определение ролей и авторизованного пользователя)
from extensions.security import get_current_user, role_required

# Импорт роутов для авторизации
from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from routes.user_routes import user_bp

# Регистрация Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)

# Добавляем в шаблоны
@app.context_processor
def utility_processor():
    return dict(
        registration_open=tournament_reg_is_open,
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

# Защищенные маршруты
@app.route('/')
def home():
    member_count = User.query.filter(User.role == RoleEnum.CLAN_MEMBER).count()
    upcoming_tournaments = Tournament.query.filter(Tournament.tournament_date >= datetime.now()) \
                                           .order_by(Tournament.tournament_date).all()
    return render_template('home.html',
                           member_count=member_count,
                           upcoming_tournaments=upcoming_tournaments)

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

    if not tournament_reg_is_open(tournament):
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



if __name__ == '__main__':
    app.run(debug=True)