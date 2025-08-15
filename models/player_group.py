from datetime import datetime
from zoneinfo import ZoneInfo
from extensions.db_connection import db
import random
from flask import jsonify

from models.tournament import Tournament

class PlayerGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey('tournament.id'), nullable=False)
    group_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))
    players = db.relationship('Player', backref='group', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'group_number', name='unique_group_number'),
    )

    @classmethod
    def shuffle_players(cls, tournament_id):
        """Случайно перемешивает игроков между группами в турнире"""
        try:
            # Получаем все группы и игроков турнира
            groups = cls.query.filter_by(tournament_id=tournament_id).all()
            all_players = []
            
            # Собираем всех игроков из всех групп
            for group in groups:
                all_players.extend(group.players)
            
            if not all_players:
                return {'success': False, 'error': 'Нет игроков для перемешивания'}
            
            # Перемешиваем игроков
            random.shuffle(all_players)
            
            # Определяем режим турнира (сколько игроков в группе)
            tournament = Tournament.query.get(tournament_id)
            if not tournament:
                return {'success': False, 'error': 'Турнир не найден'}
                
            players_per_group = 4 if tournament.mode == 'Сквад' else 2
            
            # Создаем новые группы (удаляем старые)
            for group in groups:
                db.session.delete(group)
            
            db.session.commit()
            
            # Распределяем игроков по новым группам
            for i in range(0, len(all_players), players_per_group):
                group_players = all_players[i:i + players_per_group]
                new_group = cls(
                    tournament_id=tournament_id,
                    group_number=i // players_per_group + 1
                )
                db.session.add(new_group)
                db.session.flush()
                
                for player in group_players:
                    player.group_id = new_group.id
            
            db.session.commit()
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
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

