from datetime import datetime
from db_connection import db

class PlayerGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey('tournament.id'), nullable=False)
    group_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    players = db.relationship('Player', backref='group', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'group_number', name='unique_group_number'),
    )
