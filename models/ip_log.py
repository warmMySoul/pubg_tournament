from datetime import datetime
from zoneinfo import ZoneInfo
from extensions.db_connection import db

class IPStatusEnum():
    REG = 'Зарегистрировался'
    LOGIN = 'Вошел'

    def __str__(self):
        return self.value

class IPLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    ip = db.Column(db.String(255))
    action = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))
    
    user = db.relationship(
        'User', 
        foreign_keys=[user_id],
        backref=db.backref('ip_log', cascade='all, delete-orphan'),
        lazy=True
    )
