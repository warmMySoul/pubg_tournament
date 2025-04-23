from datetime import datetime
from extensions.db_connection import db

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey('tournament.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('player_group.id'), nullable=True)
    name = db.Column(db.String(50), nullable=False)
    nickname = db.Column(db.String(50), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
