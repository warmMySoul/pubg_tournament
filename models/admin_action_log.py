from datetime import datetime
from extensions.db_connection import db
from zoneinfo import ZoneInfo

class AdminActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))

    user = db.relationship('User', backref='action_logs')
