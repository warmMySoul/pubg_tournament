from flask import session
from models import AdminActionLog
from extensions.db_connection import db

def log_admin_action(action):
    user_id = session.get('user_logged')
    if user_id:
        log = AdminActionLog(user_id=user_id, action=action)
    else:
        log = AdminActionLog(action=action)

    db.session.add(log)
    db.session.commit()