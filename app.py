from flask import Flask
from datetime import datetime
from werkzeug.security import generate_password_hash

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
from extensions.security import get_current_user

# Импорт кастомных страниц ошибок
from errors.handlers import errors

# Импорт роутов
from routes.public_routes import public_bp
from routes.admin_routes import admin_bp
from routes.user_routes import user_bp


# Регистрация Blueprints
app.register_blueprint(public_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)
app.register_blueprint(errors)

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

# импорт планировщика
from pubg_api.scheduler import start_scheduler

if __name__ == '__main__':

    # Запуск планироващика
    start_scheduler(app)

    app.run(debug=False)