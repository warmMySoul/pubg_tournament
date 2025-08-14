from datetime import datetime
from extensions.db_connection import db
from zoneinfo import ZoneInfo

from pubg_api.pubg_models.match import MatchData
from pubg_api.pubg_models.player import ParsedPlayerStats

class PlayerStats(db.Model):
    __tablename__ = 'player_stats'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    pubg_id = db.Column(db.String(128), nullable=False)
    stats_json = db.Column(db.JSON, nullable=False)
    match_ids = db.Column(db.JSON)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))

    user = db.relationship('User', backref=db.backref('cached_stats', uselist=False))

    def to_player_stats_data(self):
        """Конвертирует запись БД в объект MatchData"""
        return ParsedPlayerStats(self.stats_json)

class MatchStats(db.Model):
    __tablename__ = 'match_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.String(64), nullable=False, unique=True)
    data_json = db.Column(db.JSON, nullable=False)
    processed_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))

    def to_match_data(self):
        """Конвертирует запись БД в объект MatchData"""
        return MatchData(self.data_json)
