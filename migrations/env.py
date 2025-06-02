import logging
from logging.config import fileConfig
import os
import sys

# Добавляем путь к проекту в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import current_app
from alembic import context

config = context.config
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

# Явный импорт всех моделей
from models import (
    RoleEnum, Tournament, PlayerGroup, 
    Player, AdminActionLog, User,
    Match, PlayerMatchStats, ScheduledTask, MatchStats, JoinRequests, IPLog
)
from extensions.db_connection import db

# Принудительная регистрация моделей
_ = [RoleEnum, Tournament, PlayerGroup, Player, 
     AdminActionLog, User, Match, PlayerMatchStats, ScheduledTask, MatchStats, JoinRequests, IPLog]

# Настройка метаданных
target_metadata = db.metadata

def get_engine():
    try:
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        return current_app.extensions['migrate'].db.engine

def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace('%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')

config.set_main_option('sqlalchemy.url', get_engine_url())

def get_metadata():
    # Явный повторный импорт для надёжности
    from models import (
        RoleEnum, Tournament, PlayerGroup,
        Player, AdminActionLog, User,
        Match, PlayerMatchStats, ScheduledTask, MatchStats, JoinRequests, IPLog
    )
    return db.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,  # Включить сравнение типов
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    connectable = get_engine()
    
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
            compare_type=True,  # Включить сравнение типов
            compare_server_default=True,  # Сравнивать значения по умолчанию
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()