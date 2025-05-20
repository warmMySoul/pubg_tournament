from datetime import datetime
from zoneinfo import ZoneInfo
from extensions.db_connection import db

class PlayerGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey('tournament.id'), nullable=False)
    group_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))
    players = db.relationship('Player', backref='group', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'group_number', name='unique_group_number'),
    )
    
def get_match_stats(self, match_id):
    """Возвращает статистику группы для конкретного матча"""
    stats = {
        'total_kills': 0,
        'total_damage': 0,
        'total_points': 0,
        'best_placement': None
    }
    
    for player in self.players:
        for stat in player.matches:
            if stat.match_id == match_id:
                stats['total_kills'] += stat.kills
                stats['total_damage'] += stat.damage_dealt
                stats['total_points'] += stat.points
                
                if stat.placement:
                    if stats['best_placement'] is None or stat.placement < stats['best_placement']:
                        stats['best_placement'] = stat.placement
    
    return stats if stats['total_points'] > 0 else None

@property
def total_points(self):
    """Общее количество очков группы"""
    return sum(player.total_points or 0 for player in self.players)