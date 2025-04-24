from extensions.db_connection import db

class PlayerMatchStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    
    # Статистические данные
    kills = db.Column(db.Integer, nullable=False, default=0)
    damage_dealt = db.Column(db.Float, nullable=False, default=0.0)
    placement = db.Column(db.Integer, nullable=True)  # Занятое место (может быть NULL если не финишировал)
    points = db.Column(db.Float, nullable=False, default=0.0)  # Набранные очки в этом матче
    
    __table_args__ = (
        db.UniqueConstraint('player_id', 'match_id', name='unique_player_match'),
    )