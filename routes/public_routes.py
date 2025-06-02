from zoneinfo import ZoneInfo
from flask import Blueprint, request, session, redirect, url_for, flash, render_template
from datetime import datetime

from sqlalchemy import case, or_
from extensions.security import get_current_user
from models import User, RoleEnum, Tournament, Player, JoinRequests, RqStatusEnum
from extensions.db_connection import db

# Импорт логирования
from services.admin_log_service import log_admin_action as log

public_bp = Blueprint('public', __name__)

# Главная страница сайта
@public_bp.route('/')
def home():

    user = get_current_user()
    if user:
        join_request = JoinRequests.query.filter_by(user_id = user.id).order_by(JoinRequests.created_at.desc()).first()
    else:
        join_request = None

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

    # Ближайший будущий турнир
    next_tournament = Tournament.query.filter(
        Tournament.tournament_date > now
    ).order_by(
        Tournament.tournament_date.asc()
    ).first()

    # Последний завершенный турнир
    last_tournament = Tournament.query.filter(
        Tournament.tournament_date <= now
    ).order_by(
        Tournament.tournament_date.desc()
    ).first()

    datetime_now = datetime.now()

    return render_template('public/home.html',
                           members=members,
                           next_tournament=next_tournament,
                           last_tournament=last_tournament,
                           join_request=join_request,
                           datetime_now=datetime_now)

#Публичный просмотр деталей турнира
@public_bp.route('/public/tournament/<tournament_id>')
def view_players_public(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    players = Player.query.filter_by(tournament_id=tournament_id).order_by(Player.registered_at.desc()).all()
    just_registered = session.get('last_registered_tournament') == tournament_id
    if just_registered:
        session.pop('last_registered_tournament', None)
    
    max_players = 4 if tournament.mode == 'Сквад' else 2 if tournament.mode == 'Дуо' else None
    
    return render_template('public/tournaments/players_public.html', 
                         tournament=tournament, 
                         players=players,
                         max_players=max_players,
                         now=datetime.now(ZoneInfo("Europe/Moscow")))

#Публичный просмотр деталей турнира
@public_bp.route('/public/privacy')
def view_privacy():
    return render_template('public/privacy.html')