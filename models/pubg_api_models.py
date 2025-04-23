from datetime import datetime
from extensions.db_connection import db
from zoneinfo import ZoneInfo

class PlayerStats(db.Model):
    __tablename__ = 'player_stats'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    pubg_id = db.Column(db.String(128), nullable=False)
    stats_json = db.Column(db.JSON, nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))

    user = db.relationship('User', backref=db.backref('cached_stats', uselist=False))
