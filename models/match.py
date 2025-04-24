from extensions.db_connection import db

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey('tournament.id'), nullable=False)
    map_number = db.Column(db.Integer, nullable=False)  # Номер карты в турнире (1, 2, 3...)
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)  # Может быть NULL если матч еще идет
    
    # Статистика по матчу
    players_stats = db.relationship('PlayerMatchStats', backref='match', lazy=True, cascade='all, delete-orphan')