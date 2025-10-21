from datetime import datetime
from zoneinfo import ZoneInfo
from extensions.db_connection import db
import random
from flask import jsonify

from models.tournament import Tournament
from models.match import Match

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
                
            players_per_group = 4 if tournament.mode == 'SQUAD' else 2
            
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
    
    def get_tournament_group_stats(self):
        """Возвращает статистику группы для конкретного турнира"""
        # Получаем турнир
        tournament = Tournament.query.get(self.tournament_id)
        if not tournament:
            return None
        
        stats = {
            'tournament_id': self.tournament_id,
            'total_kills': 0,
            'total_damage': 0.0,
            'total_points': 0.0,
            'matches': {},  # Статистика по матчам
            'players': {}   # Статистика по игрокам
        }
        
        # Инициализируем статистику игроков
        for player in self.players:
            stats['players'][player.id] = {
                'player_id': player.id,
                'nickname': player.nickname,
                'total_kills': 0,
                'total_damage': 0.0,
                'total_points': 0.0
            }
        
        # Собираем статистику по всем матчам
        for player in self.players:
            for player_match_stat in player.matches:
                # Проверяем, что статистика принадлежит нужному турниру
                match = Match.query.get(player_match_stat.match_id)
                if not match or match.tournament_id != self.tournament_id:
                    continue
                
                match_id = player_match_stat.match_id
                
                # Инициализируем статистику матча если нужно
                if match_id not in stats['matches']:
                    stats['matches'][match_id] = {
                        'match_id': match_id,
                        'map_number': match.map_number,
                        'total_kills': 0,
                        'total_damage': 0.0,
                        'total_points': 0.0,
                        'placement': None,
                        'placement_points': 0.0,
                        'kills_points': 0.0,
                        'damage_points': 0.0
                    }
                
                match_stats = stats['matches'][match_id]
                player_stats = stats['players'][player.id]
                
                # Обновляем статистику матча
                match_stats['total_kills'] += player_match_stat.kills
                match_stats['total_damage'] += player_match_stat.damage_dealt
                
                # Обновляем статистику игрока
                player_stats['total_kills'] += player_match_stat.kills
                player_stats['total_damage'] += player_match_stat.damage_dealt
                
                # Очки за убийства в матче
                if tournament.kill_points:
                    kill_points = player_match_stat.kills * tournament.kill_points
                    match_stats['kills_points'] += kill_points
                    player_stats['total_points'] += kill_points
                
                # Очки за урон в матче
                if tournament.damage_points:
                    damage_points = (player_match_stat.damage_dealt / 100) * tournament.damage_points
                    match_stats['damage_points'] += damage_points
                    player_stats['total_points'] += damage_points
                
                # Обновляем лучшее место команды в матче
                if player_match_stat.placement:
                    if (match_stats['placement'] is None or 
                        player_match_stat.placement < match_stats['placement']):
                        match_stats['placement'] = player_match_stat.placement
        
        # Рассчитываем очки за места для каждого матча
        for match_id, match_stats in stats['matches'].items():
            placement_points = 0.0
            
            # Начисляем очки за место (один раз за матч для всей команды)
            if match_stats['placement'] == 1 and tournament.first_place_points:
                placement_points = tournament.first_place_points
            elif match_stats['placement'] == 2 and tournament.second_place_points:
                placement_points = tournament.second_place_points
            elif match_stats['placement'] == 3 and tournament.third_place_points:
                placement_points = tournament.third_place_points
            
            match_stats['placement_points'] = placement_points
            match_stats['total_points'] = (match_stats['kills_points'] + 
                                        match_stats['damage_points'] + 
                                        placement_points)
        
        # Суммируем общую статистику группы
        for match_stats in stats['matches'].values():
            stats['total_kills'] += match_stats['total_kills']
            stats['total_damage'] += match_stats['total_damage']
            stats['total_points'] += match_stats['total_points']
        
        # Преобразуем словари в списки для удобства
        stats['matches'] = list(stats['matches'].values())
        stats['players'] = list(stats['players'].values())
        
        # Сортируем матчи по номеру карты
        stats['matches'].sort(key=lambda x: x['map_number'])
        
        # Сортируем игроков по количеству очков (по убыванию)
        stats['players'].sort(key=lambda x: x['total_points'], reverse=True)
        
        return stats if stats['matches'] else None
    
    @property
    def total_points(self):
        """Общее количество очков группы"""
        stats = self.get_tournament_group_stats()
        if stats:
            return stats['total_points']
        return 0.0

    def player_tournament_stat(self, player_id):
        """Статистика игрока группы в турнире"""
        stats = self.get_tournament_group_stats()
        if stats and 'players' in stats:
            # Ищем статистику игрока
            for player_stat in stats['players']:
                if player_stat['player_id'] == player_id:
                    return player_stat
        return {
            'total_kills': 0,
            'total_damage': 0.0,
            'total_points': 0.0
        }
