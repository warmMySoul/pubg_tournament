from flask import Blueprint, request, session, redirect, url_for, flash, render_template
from datetime import datetime
from models import User, RoleEnum, Tournament, Player
from extensions.db_connection import db

# Импорт логирования
from services.admin_log_service import log_admin_action as log

public_bp = Blueprint('public', __name__)

# Главная страница сайта
@public_bp.route('/')
def home():
    member_count = User.query.filter(User.role == RoleEnum.CLAN_MEMBER).count()
    upcoming_tournaments = Tournament.query.filter(Tournament.tournament_date >= datetime.now()) \
                                           .order_by(Tournament.tournament_date).all()
    return render_template('public/home.html',
                           member_count=member_count,
                           upcoming_tournaments=upcoming_tournaments)

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
                         just_registered=just_registered,
                         max_players=max_players)
