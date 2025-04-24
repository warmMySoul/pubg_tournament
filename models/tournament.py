from datetime import datetime
from zoneinfo import ZoneInfo
from extensions.db_connection import db

class Tournament(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    reg_start = db.Column(db.DateTime, nullable=False)
    reg_end = db.Column(db.DateTime, nullable=False)
    tournament_date = db.Column(db.DateTime, nullable=False)
    mode = db.Column(db.String(20), nullable=False)  # 'Solo', 'Duo', 'Squad'
    maps_count = db.Column(db.Integer, nullable=False, default=3)  # Количество карт в турнире
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))
    
    # Параметры подсчета очков (могут быть NULL)
    kill_points = db.Column(db.Float, nullable=True)  # Очки за убийство
    first_place_points = db.Column(db.Float, nullable=True)  # Очки за 1 место
    second_place_points = db.Column(db.Float, nullable=True)  # Очки за 2 место
    third_place_points = db.Column(db.Float, nullable=True)  # Очки за 3 место
    damage_points = db.Column(db.Float, nullable=True)  # Очки за единицу урона
    
    # Связи
    players = db.relationship('Player', backref='tournament', lazy=True, cascade='all, delete-orphan')
    player_groups = db.relationship('PlayerGroup', backref='tournament', lazy=True, cascade='all, delete-orphan')
    matches = db.relationship('Match', backref='tournament', lazy=True, cascade='all, delete-orphan')