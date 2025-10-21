from zoneinfo import ZoneInfo
from flask import Blueprint, request, session, redirect, url_for, flash, render_template
from datetime import datetime, timezone

from sqlalchemy import and_, case, or_, func
from extensions.security import get_current_user
from models import User, RoleEnum, Tournament, Player, JoinRequests, RqStatusEnum, Match, PlayerGroup
from extensions.db_connection import db


public_bp = Blueprint('public', __name__)

# Главная страница сайта
@public_bp.route('/')
def home():

    user = get_current_user()

    # Создаем кастомный порядок сортировки
    role_ordering = case(
        {
            RoleEnum.ADMIN: 1,
            RoleEnum.MODERATOR: 2,
            RoleEnum.CLAN_MEMBER: 3
        },
        value=User.role
    )

    members = User.query.filter(
        or_(
            User.role == RoleEnum.CLAN_MEMBER,
            User.role == RoleEnum.ADMIN,
            User.role == RoleEnum.MODERATOR
        )
    ).filter(
        User.username != 'admin'
    ).order_by(role_ordering)
    now = datetime.now()

    # Ближайшие будущие турниры
    next_tournaments = db.session.query(
        Tournament,
        func.count(Player.id).label('player_count')
    ).outerjoin(
        Player, Tournament.id == Player.tournament_id
    ).filter(
        and_(
            Tournament.tournament_date > now
        )
    ).group_by(
        Tournament.id
    ).order_by(
        Tournament.tournament_date.asc()
    )

    # Создаем список для хранения турниров с дополнительной информацией
    tournaments_with_info = []

    # Проверка на наличие регистрации в турнире
    if user:
        for tournament_data in next_tournaments:
            tournament = tournament_data[0]  # Извлекаем объект Tournament
            player_count = tournament_data[1]  # Извлекаем количество игроков
            
            # Проверяем, зарегистрирован ли пользователь
            is_user_registered = Player.query.filter_by(
                tournament_id=tournament.id,
                user_id=user.id
            ).first() is not None
            
            # Создаем словарь с информацией о турнире
            tournament_info = {
                'tournament': tournament,
                'player_count': player_count,
                'is_user_registered': is_user_registered
            }
            
            tournaments_with_info.append(tournament_info)
    else:
        # Если пользователь не авторизован
        for tournament_data in next_tournaments:
            tournament = tournament_data[0]
            player_count = tournament_data[1]
            
            tournament_info = {
                'tournament': tournament,
                'player_count': player_count,
                'is_user_registered': False
            }
            
            tournaments_with_info.append(tournament_info)

    # Последние завершенные турниры
    last_tournaments = db.session.query(
        Tournament,
        func.count(Player.id).label('player_count')
    ).outerjoin(
        Player, Tournament.id == Player.tournament_id
    ).filter(
        and_(
            Tournament.tournament_date < now
        )
    ).group_by(
        Tournament.id
    ).order_by(
        Tournament.tournament_date.desc()
    )

    #Количество турниров
    all_tournaments = Tournament.query.outerjoin(
        Player, Tournament.id == Player.tournament_id
    ).all()


    return render_template('public/home.html',
                           members=members,
                           next_tournaments=tournaments_with_info,
                           last_tournaments=last_tournaments,
                           all_tournaments=all_tournaments)

# Публичный просмотр деталей турнира new
@public_bp.route('/public/tournament/<tournament_id>')
def tournament_details(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    players = Player.query.filter_by(tournament_id=tournament_id).order_by(Player.registered_at.desc()).all()
    now = datetime.now()

    # Получаем все матчи турнира для статистики по матчам
    matches = Match.query.filter_by(tournament_id=tournament_id).order_by(Match.map_number).all()

    # Рассчитываем общую статистику для каждого игрока
    for player in players:
        total_kills = 0
        total_damage = 0.0
        total_place_points = 0.0
        
        # Суммируем статистику по всем матчам игрока
        for match_stat in player.matches:
            total_kills += match_stat.kills
            total_damage += match_stat.damage_dealt

            # Расчет баллов за место
            if match_stat.placement == 1 and tournament.first_place_points:
                total_place_points += tournament.first_place_points
            elif match_stat.placement == 2 and tournament.second_place_points:
                total_place_points += tournament.second_place_points
            elif match_stat.placement == 3 and tournament.third_place_points:
                total_place_points += tournament.third_place_points
        
        # Добавляем вычисленные поля к объекту игрока
        player.total_kills = total_kills
        player.total_damage = total_damage
        player.total_place_points = total_place_points

    # Создаем структуру данных для статистики по матчам
    matches_stats = []

    # Рассчитываем общую статистику турнира
    total_tournament_players = len(players)
    total_tournament_damage = sum(player.total_damage for player in players)
    total_tournament_points = sum(player.total_points or 0 for player in players)
    
    # Для групповых режимов считаем количество команд
    if tournament.mode in ['DUO', 'SQUAD']:
        total_tournament_teams = len(tournament.player_groups)
    else:
        total_tournament_teams = total_tournament_players
    
    for match in matches:
        match_data = {
            'match': match,
            'players_stats': []
        }
        
        # Для каждого игрока находим статистику для этого матча
        for player in players:
            player_match_stat = next(
                (stat for stat in player.matches if stat.match_id == match.id), 
                None
            )
            
            if player_match_stat:
                # Рассчитываем очки за место для этого матча
                place_points = 0
                if player_match_stat.placement == 1 and tournament.first_place_points:
                    place_points = tournament.first_place_points
                elif player_match_stat.placement == 2 and tournament.second_place_points:
                    place_points = tournament.second_place_points
                elif player_match_stat.placement == 3 and tournament.third_place_points:
                    place_points = tournament.third_place_points
                
                match_data['players_stats'].append({
                    'player': player,
                    'kills': player_match_stat.kills,
                    'damage': player_match_stat.damage_dealt,
                    'placement': player_match_stat.placement,
                    'place_points': place_points,
                    'total_points': player_match_stat.points
                })
        
        # Сортируем игроков по набранным очкам в матче
        match_data['players_stats'].sort(key=lambda x: x['placement'])
        matches_stats.append(match_data)

    # Определяем статус турнира
    if tournament.reg_start < now and tournament.reg_end > now:
        registration_status = 'open'
    elif tournament.reg_end < now:
        if tournament.tournament_date < now:
            registration_status = "ended"
        else:
            registration_status = 'closed'
    else:
        registration_status = 'soon'

    max_players = 4 if tournament.mode == 'SQUAD' else 2 if tournament.mode == 'DUO' else 1

    # Проверка существующей регистрации пользователя
    user = get_current_user()
    if user:
        existing_player = Player.query.filter_by(
            tournament_id=tournament_id,
            user_id=user.id
        ).first()
    else:
        existing_player = None

    return render_template('public/tournaments/tournament_details.html', 
                         tournament=tournament, 
                         registration_status=registration_status,
                         players=players,
                         matches_stats=matches_stats,
                         existing_player=existing_player,
                         total_tournament_players=total_tournament_players,
                         total_tournament_teams=total_tournament_teams,
                         total_tournament_damage=total_tournament_damage,
                         total_tournament_points=total_tournament_points,
                         max_players=max_players,
                         now=datetime.now(ZoneInfo("Europe/Moscow")))

# Пользовательское соглашение
@public_bp.route('/public/privacy')
def view_privacy():
    return render_template('public/privacy.html')