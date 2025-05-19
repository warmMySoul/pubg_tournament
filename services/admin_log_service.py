from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import has_request_context, session
from models import AdminActionLog
from extensions.db_connection import db

def log_admin_action(action, force_admin=False):
    """
    Логирование действий в базу данных
    """
    if force_admin or not has_request_context():
        user_id = 1  # Для фоновых задач или при явном указании
    else:
        user_id = session.get('user_logged')  # Только в HTTP-контексте

    if user_id:
        log = AdminActionLog(user_id=user_id, action=action)
    else:
        log = AdminActionLog(action=action)

    db.session.add(log)
    db.session.commit()

    clear_old_logs()


def clear_old_logs():
    """
    Очищает логи старше 30 дней
    """
    # Получаем текущее время в московской временной зоне
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    
    # Вычисляем дату, которая была ровно месяц назад
    one_month_ago = now - timedelta(days=30)
    
    # Находим и удаляем старые записи
    AdminActionLog.query.filter(AdminActionLog.timestamp < one_month_ago).delete()
    
    # Коммитим изменения
    db.session.commit()