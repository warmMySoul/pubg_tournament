from datetime import datetime
from zoneinfo import ZoneInfo
from extensions.db_connection import db

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey('tournament.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Связь с пользователем
    group_id = db.Column(db.Integer, db.ForeignKey('player_group.id'), nullable=True)
    name = db.Column(db.String(50), nullable=False)
    nickname = db.Column(db.String(50), nullable=False)
    registered_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))
    
    # Статистика игрока (может быть NULL)
    total_points = db.Column(db.Float, nullable=True, default=0.0)  # Общее количество очков
    matches = db.relationship('PlayerMatchStats', backref='player', lazy=True, cascade='all, delete-orphan')