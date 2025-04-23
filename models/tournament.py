from datetime import datetime
from extensions.db_connection import db

class Tournament(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    reg_start = db.Column(db.DateTime, nullable=False)
    reg_end = db.Column(db.DateTime, nullable=False)
    tournament_date = db.Column(db.DateTime, nullable=False)
    mode = db.Column(db.String(20), nullable=False)
    scoring_system = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    players = db.relationship('Player', backref='tournament', lazy=True, cascade='all, delete-orphan')
    player_groups = db.relationship('PlayerGroup', backref='tournament', lazy=True, cascade='all, delete-orphan')
