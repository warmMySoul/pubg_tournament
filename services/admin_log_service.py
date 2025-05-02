from flask import has_request_context, session
from models import AdminActionLog
from extensions.db_connection import db

def log_admin_action(action, force_admin=False):
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