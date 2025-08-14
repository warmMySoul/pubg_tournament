import json
from flask import Flask, jsonify, request
from datetime import datetime
from flask_migrate import Migrate
import pika
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv
import os

def create_app():
    load_dotenv("secrets.env")

    app = Flask(__name__)

    # Основные настройки
    app.config.update(
        SQLALCHEMY_DATABASE_URI='sqlite:///tournament.db',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.getenv('SECRET_KEY'),
        FERNET_KEY=os.getenv('FERNET_KEY'),


        # Почта
        MAIL_SERVER='smtp.mail.ru',
        MAIL_PORT=465,
        MAIL_USE_SSL=True,
        MAIL_USERNAME=os.getenv('MAIL_LOGIN'),
        MAIL_PASSWORD=os.getenv('MAIL_PASS'),
        MAIL_TIMEOUT=10,
        
    )

    # Проверка ключей
    if not app.config['SECRET_KEY']:
        raise ValueError("SECRET_KEY is not set in the environment variables")

    # Инициализация расширений
    from extensions.db_connection import db
    Migrate(app, db)
    db.init_app(app)

    from extensions.mail_connect import mail
    mail.init_app(app)

    # Регистрация Blueprint'ов
    from routes.public_routes import public_bp
    from routes.admin_routes import admin_bp
    from routes.user_routes import user_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)

    # Добавляем переменные в шаблоны
    from utils.helpers import registration_open as tournament_reg_is_open
    from extensions.security import get_current_user

    @app.context_processor
    def utility_processor():
        return dict(
            registration_open=tournament_reg_is_open,
            now=datetime.now(),
            current_user=get_current_user()
        )

    # Инициализация БД и создание администратора
    from models import User, RoleEnum
    with app.app_context():
        db.create_all()
        create_default_admin()

    # Инициализация планировщика задач
    from pubg_api.scheduler import init_scheduler
    app.config['SCHEDULER_TIMEZONE'] = 'Europe/Moscow'
    init_scheduler(app)

    return app


def create_default_admin():
    from models import User, RoleEnum
    from extensions.db_connection import db

    admin_username = 'admin'
    if not User.query.filter_by(username=admin_username).first():
        admin = User(
            username=admin_username,
            password=generate_password_hash(os.getenv('ADMIN_PASS')),
            role=RoleEnum.ADMIN,
            pubg_nickname="admin_user",
            email=os.getenv('ADMIN_MAIL'),
            is_verified=True
        )
        db.session.add(admin)
        db.session.commit()


app = create_app()

@app.route('/api/add_task', methods=['POST'])
def add_pubg_task():
    task_data = request.json
        
    # Валидация задачи
    if not task_data.get("type"):
        return jsonify({"error": "Task type is required"}), 400
        
    # Отправка в RabbitMQ
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    channel.basic_publish(
        exchange='',
        routing_key='pubg_tasks',
        body=json.dumps(task_data),
        properties=pika.BasicProperties(delivery_mode=2)  # Сохраняем задачи
    )
    connection.close()
        
    return jsonify({"status": f"Task {task_data.get("type")} added"}), 200

if __name__ == '__main__':
    app.run(debug=True)
