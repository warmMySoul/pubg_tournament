from inspect import getmembers, getsourcefile, isfunction
from io import BytesIO
import io
from pathlib import Path
import pkgutil
import uuid
import pandas as pd
from zoneinfo import ZoneInfo
from flask import Blueprint, flash, url_for, redirect, request, render_template, jsonify
from datetime import datetime
from flask import send_file
from openpyxl import Workbook
from sqlalchemy import case, func
from extensions.security import get_current_user, role_required
from models import RoleEnum, Tournament, PlayerGroup, Player, AdminActionLog, User, Match, PlayerMatchStats, ScheduledTask, JoinRequests, RqStatusEnum
from extensions.db_connection import db

# Импорт логирования
from pubg_api.models import MatchData
from services.admin_log_service import log_admin_action as log

from models.pubg_api_models import MatchStats, PlayerStats
from pubg_api.models.player import ParsedPlayerStats
from pubg_api.scheduler import *

# Импорт PUBG API
from pubg_api.client import PUBGApiClient
from utils.helpers import generate_export_data
client = PUBGApiClient()


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Админ-панель
@admin_bp.route('/')
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def admin():
    join_requests = JoinRequests.query.filter_by(status = RqStatusEnum.REVIEW).all()

    return render_template('admin/admin.html',
                           join_requests=join_requests)

# Турниры
@admin_bp.route('/tournaments')
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def tournaments():
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
    return render_template('admin/tournaments/tournaments.html', tournaments=tournaments)

# Создать трунир
@admin_bp.route('/tournament/create', methods=['GET', 'POST'])
@role_required([RoleEnum.ADMIN])
def create_tournament():
    if request.method == 'POST':
        try:
            # Основные параметры турнира
            new_tournament = Tournament(
                id=str(uuid.uuid4()),
                name=request.form['name'],
                reg_start=datetime.strptime(request.form['reg_start'], '%Y-%m-%dT%H:%M'),
                reg_end=datetime.strptime(request.form['reg_end'], '%Y-%m-%dT%H:%M'),
                tournament_date=datetime.strptime(request.form['tournament_date'], '%Y-%m-%dT%H:%M'),
                mode=request.form['mode'],
                maps_count=int(request.form['maps_count'])
            )
            
            # Параметры подсчета очков (могут быть пустыми)
            if request.form.get('kill_points'):
                new_tournament.kill_points = float(request.form['kill_points'])
            if request.form.get('first_place_points'):
                new_tournament.first_place_points = float(request.form['first_place_points'])
            if request.form.get('second_place_points'):
                new_tournament.second_place_points = float(request.form['second_place_points'])
            if request.form.get('third_place_points'):
                new_tournament.third_place_points = float(request.form['third_place_points'])
            if request.form.get('damage_points'):
                new_tournament.damage_points = float(request.form['damage_points'])
            
            # Валидация дат
            if new_tournament.reg_start >= new_tournament.reg_end:
                flash('Дата окончания регистрации должна быть позже даты начала', 'error')
                return redirect(url_for('admin.create_tournament'))
            
            if new_tournament.reg_end >= new_tournament.tournament_date:
                flash('Дата проведения турнира должна быть позже окончания регистрации', 'error')
                return redirect(url_for('admin.create_tournament'))
            
            db.session.add(new_tournament)
            db.session.commit()
            
            log(f"Создан турнир {new_tournament.name}")
            flash('Турнир успешно создан', 'success')
            return redirect(url_for('admin.tournaments'))
            
        except ValueError as e:
            db.session.rollback()
            flash(f'Ошибка в формате данных: {str(e)}', 'error')
        except Exception as e:
            db.session.rollback()
            flash('Произошла ошибка при создании турнира', 'error')
    
    return render_template('admin/tournaments/create.html')

# Просмотр деталей турнира
@admin_bp.route('/tournament/<tournament_id>')
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def view_players(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    max_players = 4 if tournament.mode == 'Сквад' else 2 if tournament.mode == 'Дуо' else None
    return render_template('admin/tournaments/tournament_info.html', 
                         tournament=tournament,
                         max_players=max_players)

# Экспорт турнира в Excell
@admin_bp.route('/tournament/<tournament_id>/export', methods=['GET'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def export_tournament_data(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Составляем данные для выгрузки
    export_data = generate_export_data(tournament)

    # Генерируем Excel в памяти
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in export_data.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)

    # Отдаём файл пользователю
    filename = f"{tournament.name}_выгрузка.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# api перемещения игроков между команд
@admin_bp.route('/api/move_player', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def move_player():
    player_id = request.json.get('player_id')
    new_group_id = request.json.get('new_group_id')

    player = Player.query.get_or_404(player_id)
    tournament = Tournament.query.get_or_404(player.tournament_id)

    if tournament.mode not in ['Дуо', 'Сквад']:
        return jsonify({'success': False, 'error': 'Только для режимов Дуо/Сквад'})

    old_group_id = player.group_id

    # Если new_group_id не указан — создаём новую группу с минимально возможным номером
    if not new_group_id:
        used_numbers = set(g.group_number for g in PlayerGroup.query.filter_by(tournament_id=tournament.id).all())
        new_number = 1
        while new_number in used_numbers:
            new_number += 1

        new_group = PlayerGroup(
            tournament_id=tournament.id,
            group_number=new_number
        )
        db.session.add(new_group)
        db.session.flush()  # Получаем ID новой группы
        new_group_id = new_group.id
    else:
        group = PlayerGroup.query.filter_by(id=new_group_id, tournament_id=player.tournament_id).first()
        if not group:
            return jsonify({'success': False, 'error': 'Группа не найдена'})

        max_players = 4 if tournament.mode == 'Сквад' else 2
        if len(group.players) >= max_players:
            return jsonify({'success': False, 'error': 'Группа уже заполнена'})

    player.group_id = new_group_id
    log(f"В трунирне {tournament.name} игрок {player.name} ({player.nickname}) перемещен в группу '{player.group_id }'")
    db.session.commit()
    
    # Проверка и удаление старой группы, если она пуста
    if old_group_id:
        old_group = PlayerGroup.query.get(old_group_id)
        if old_group and len(old_group.players) == 0:
            db.session.delete(old_group)
            db.session.commit()

    return jsonify({'success': True})

# Удалить игрока из турнира
@admin_bp.route('/api/delete_player', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def delete_player():
    data = request.get_json()
    player_id = data.get('player_id')

    player = Player.query.get(player_id)
    if not player:
        return jsonify({'success': False, 'error': 'Игрок не найден'})

    tournament = player.tournament
    group = player.group  # Может быть None (в режиме Соло)

    db.session.delete(player)

    # Проверка на удаление пустой группы для Дуо и Сквад
    if group and tournament.mode in ['Дуо', 'Сквад']:
        remaining_players = Player.query.filter_by(group_id=group.id).count()
        if remaining_players == 0:
            db.session.delete(group)

    log(f"Удален игрок {player.name} ({player.nickname}) из турнира {tournament.name}")

    db.session.commit()
    return jsonify({'success': True})

# Создание матча
@admin_bp.route('/tournament/<tournament_id>/create_match', methods=['GET', 'POST'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def create_match(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if request.method == 'POST':
        try:
            map_number = int(request.form['map_number'])
            started_at = datetime.strptime(request.form['started_at'], '%Y-%m-%dT%H:%M')
            
            # Проверка на уникальность номера карты
            existing_match = Match.query.filter_by(
                tournament_id=tournament_id,
                map_number=map_number
            ).first()
            
            if existing_match:
                flash('Матч для этой карты уже существует', 'error')
                return redirect(url_for('admin.create_match', tournament_id=tournament_id))
            
            new_match = Match(
                tournament_id=tournament_id,
                map_number=map_number,
                started_at=started_at
            )
            
            db.session.add(new_match)
            db.session.commit()
            
            flash('Матч успешно создан', 'success')
            return redirect(url_for('admin.view_players', tournament_id=tournament_id))
            
        except ValueError as e:
            flash('Ошибка в формате данных', 'error')
    
    # Для GET-запроса
    return render_template('admin/tournaments/create_match.html', tournament=tournament)

# Статистика матча
@admin_bp.route('/match/<int:match_id>/stats', methods=['GET', 'POST'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def match_stats(match_id):
    match = Match.query.get_or_404(match_id)
    tournament = match.tournament
    
    if request.method == 'POST':
        try:
            # Обработка формы остается без изменений
            for player in tournament.players:
                kills = int(request.form.get(f'kills_{player.id}', 0))
                damage = float(request.form.get(f'damage_{player.id}', 0))
                placement = request.form.get(f'placement_{player.id}')
                
                stats = PlayerMatchStats.query.filter_by(
                    player_id=player.id,
                    match_id=match.id
                ).first()
                
                if not stats:
                    stats = PlayerMatchStats(
                        player_id=player.id,
                        match_id=match.id
                    )
                    db.session.add(stats)
                
                stats.kills = kills
                stats.damage_dealt = damage
                stats.placement = int(placement) if placement else None
                
                # Расчет очков остается без изменений
                stats.points = 0
                if tournament.kill_points:
                    stats.points += kills * tournament.kill_points
                if tournament.damage_points:
                    stats.points += (damage // 100) * tournament.damage_points
                if placement:
                    if placement == '1' and tournament.first_place_points:
                        stats.points += tournament.first_place_points
                    elif placement == '2' and tournament.second_place_points:
                        stats.points += tournament.second_place_points
                    elif placement == '3' and tournament.third_place_points:
                        stats.points += tournament.third_place_points
                
                player.total_points = db.session.query(
                    func.sum(PlayerMatchStats.points)
                    .filter(PlayerMatchStats.player_id == player.id)).scalar() or 0
            
            if not match.ended_at:
                match.ended_at = datetime.now()
            
            db.session.commit()
            flash('Статистика успешно сохранена', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при сохранении статистики: {str(e)}', 'error')
    
    return render_template('admin/tournaments/match_stats.html', 
                         match=match, 
                         tournament=tournament)

# API для удаления матча
@admin_bp.route('/api/delete_match', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def api_delete_match():
    data = request.get_json()
    match = Match.query.get_or_404(data['match_id'])
    
    try:
        # Пересчитываем очки для игроков
        for stats in match.players_stats:
            player = stats.player
            db.session.delete(stats)
            player.total_points = db.session.query(
                func.sum(PlayerMatchStats.points)).filter_by(player_id=player.id).scalar() or 0
        
        db.session.delete(match)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# Удалить турнир
@admin_bp.route('/api/delete_tournament', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def delete_tournament():
    data = request.json
    tournament_id = data.get('tournament_id')
    confirm = data.get('confirm')

    if not confirm:
        return jsonify({'success': False, 'error': 'Требуется подтверждение'})

    tournament = Tournament.query.get_or_404(tournament_id)
    db.session.delete(tournament)
    db.session.commit()
    log(f"Удален турнир {tournament.name}")

    return jsonify({'success': True})

# Отредактировать турнир
@admin_bp.route('/api/edit_tournament', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def edit_tournament():
    data = request.json
    if not data.get('confirm'):
        return jsonify({'success': False, 'error': 'Требуется подтверждение'})

    tournament = Tournament.query.get_or_404(data['tournament_id'])

    try:
        tournament.name = data['name']
        tournament.mode = data['mode']
        tournament.reg_start = datetime.strptime(data['reg_start'], '%Y-%m-%dT%H:%M')
        tournament.reg_end = datetime.strptime(data['reg_end'], '%Y-%m-%dT%H:%M')
        tournament.tournament_date = datetime.strptime(data['tournament_date'], '%Y-%m-%dT%H:%M')

        db.session.commit()
        log(f"Изменён турнир {tournament.name}")
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Просмотр логов
@admin_bp.route('/logs')
@role_required([RoleEnum.ADMIN])
def view_logs():
    admin_username = request.args.get('admin')
    action_contains = request.args.get('action')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    filter_by = request.args.get('admin_filter', 'all')

    query = AdminActionLog.query

    if filter_by == 'admins':
        query = query.join(User).filter(User.role == RoleEnum.ADMIN)
    elif filter_by == 'moderator':
        query = query.join(User).filter(User.role == RoleEnum.MODERATOR)
    elif filter_by == 'clan_member':
        query = query.join(User).filter(User.role == RoleEnum.CLAN_MEMBER)
    elif filter_by == 'system':
        query = query.filter(AdminActionLog.user_id == None)

    if admin_username:
        query = query.join(User).filter(User.username.ilike(f'%{admin_username}%'))

    if action_contains:
        query = query.filter(AdminActionLog.action.ilike(f'%{action_contains}%'))

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AdminActionLog.timestamp >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(AdminActionLog.timestamp <= dt_to)
        except ValueError:
            pass

    query = query.order_by(AdminActionLog.timestamp.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    logs = pagination.items

    return render_template('admin/logs.html', logs=logs, pagination=pagination)

# Экспорт логов в Excell
@admin_bp.route('/export_logs')
@role_required([RoleEnum.ADMIN])
def export_logs():
    admin_username = request.args.get('admin')
    action_contains = request.args.get('action')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    filter_by = request.args.get('admin_filter', 'all')

    query = AdminActionLog.query.outerjoin(User).order_by(AdminActionLog.timestamp.desc())

    # Фильтры
    if filter_by == 'admins':
        query = query.filter(AdminActionLog.admin_id != None)
    elif filter_by == 'guests':
        query = query.filter(AdminActionLog.admin_id == None)

    if admin_username:
        query = query.filter(User.username.ilike(f'%{admin_username}%'))

    if action_contains:
        query = query.filter(AdminActionLog.action.ilike(f'%{action_contains}%'))

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AdminActionLog.timestamp >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(AdminActionLog.timestamp <= dt_to)
        except ValueError:
            pass

    logs = query.all()

    # Создаём Excel-файл
    wb = Workbook()
    ws = wb.active
    ws.title = "Журнал действий"

    # Заголовки
    ws.append(['Дата и время', 'Пользователь', 'Действие'])

    for log_info in logs:
        ws.append([
            log_info.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log_info.user.username if log_info.user else 'Гость',
            log_info.action
        ])

    # Сохраняем в байтовый поток
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='admin_logs.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# Пользователи с пагинацией и фильтрами
@admin_bp.route('/users')
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def users_list():
    # Параметры фильтрации
    username_filter = request.args.get('username', '').strip()
    pubg_nickname_filter = request.args.get('pubg_nickname', '').strip()
    name_filter = request.args.get('name', '').strip()
    role_filter = request.args.get('role_filter', 'all')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    
    # Пагинация
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Базовый запрос
    query = User.query
    
    # Фильтр по роли 
    if role_filter == 'admins':
        query = query.filter(User.role == RoleEnum.ADMIN)
    elif role_filter == 'moderators':
        query = query.filter(User.role == RoleEnum.MODERATOR)
    elif role_filter == 'clan_members':
        query = query.filter(User.role == RoleEnum.CLAN_MEMBER)
    elif role_filter == 'clan_friend':
        query = query.filter(User.role == RoleEnum.CLAN_FRIEND)
    elif role_filter == 'guests':
        query = query.filter(User.role == RoleEnum.GUEST)
    
    # Остальные фильтры без изменений
    if username_filter:
        query = query.filter(User.username.ilike(f'%{username_filter}%'))
    
    if pubg_nickname_filter:
        query = query.filter(User.pubg_nickname.ilike(f'%{pubg_nickname_filter}%'))
    
    if name_filter:
        query = query.filter(User.name.ilike(f'%{name_filter}%'))
    
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(User.created_at >= dt_from)
        except ValueError:
            pass
    
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(User.created_at <= dt_to)
        except ValueError:
            pass
    
    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template(
        'admin/users/users_list.html',
        users=pagination.items,
        pagination=pagination,
        current_filters={
            'username': username_filter,
            'pubg_nickname': pubg_nickname_filter,
            'name': name_filter,
            'role_filter': role_filter,
            'from': date_from,
            'to': date_to
        },
        RoleEnum=RoleEnum  # Передаем enum в шаблон
    )

# Удалить пользователя
@admin_bp.route('/api/delete_user', methods=['POST'])
@role_required([RoleEnum.ADMIN])
def delete_user():
    data = request.json
    user_id = data.get('user_id')
    confirm = data.get('confirm')

    if not confirm:
        return jsonify({'success': False, 'error': 'Требуется подтверждение'})

    user = User.query.get_or_404(user_id)
    stat = PlayerStats.query.filter_by(user_id=user.id).first()
    # Начинаем транзакцию
    if (stat):
        db.session.delete(stat)
        
    db.session.delete(user)
    
    log(f"Удален пользователь {user.username} и его статистика")
    db.session.commit()

    return jsonify({'success': True})

# API редактирования пользователя
@admin_bp.route('/api/edit_user', methods=['POST'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def edit_user():
    data = request.json
    user = User.query.get_or_404(data['user_id'])

    if user.id == get_current_user().id:
        return jsonify({'success': False, 'error': 'Нельзя редактировать самого себя через это окно.'})

    user.pubg_nickname = data.get('pubg_nickname', user.pubg_nickname)
    user.name = data.get('name')
    user.role = data.get('role')

    birthday = data.get('birthday')
    if birthday:
        try:
            user.birthday = datetime.strptime(birthday, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Неверный формат даты'})

    db.session.commit()
    log(f"Изменены данные пользователя {user.username}")
    return jsonify({'success': True})

# Профиль пользователя
@admin_bp.route('/profile/<user_id>', methods=['GET', 'POST'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    player_stats = None
    updated_at = None
    match_ids = []

    # Получаем или создаем запись в PlayerStats
    cached_stats = PlayerStats.query.filter_by(user_id=user.id).first()
    
    # Обработка POST запроса (обновление статистики)
    if request.method == 'POST':
        try:
            if not cached_stats:
                cached_stats = PlayerStats(user_id=user.id)
                db.session.add(cached_stats)
            
            # Получаем свежие данные из API
            player = client.get_player_by_name(user.pubg_nickname)
            if not player:
                return jsonify({"success": False, "error": "Игрок не найден"}), 404
            
            stats = client.get_player_lifetime_stats_by_id(player.id)
            
            # Обновляем данные
            cached_stats.pubg_id = player.id
            cached_stats.stats_json = stats.to_dict() if stats else {}
            cached_stats.match_ids = getattr(player, 'match_ids', [])
            cached_stats.updated_at = datetime.now(ZoneInfo("Europe/Moscow"))
            
            db.session.commit()
            
            # Обновляем переменные для отображения
            player_stats = ParsedPlayerStats.from_json(cached_stats.stats_json) if cached_stats.stats_json else None
            match_ids = cached_stats.match_ids or []
            updated_at = cached_stats.updated_at
            
            return jsonify({
                "success": True,
                "updated_at": updated_at.isoformat(),
                "stats": player_stats.to_dict() if player_stats else {},
                "match_ids": match_ids
            })
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating stats: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
    
    # Обработка GET запроса
    if cached_stats:
        try:
            player_stats = ParsedPlayerStats.from_json(cached_stats.stats_json) if cached_stats.stats_json else None
            updated_at = cached_stats.updated_at
            match_ids = cached_stats.match_ids or []
        except Exception as e:
            current_app.logger.error(f"Error loading stats: {str(e)}", exc_info=True)
            flash("Ошибка при загрузке статистики", "error")
    else:
        # Первоначальная загрузка данных, если их нет в БД
        try:
            player = client.get_player_by_name(user.pubg_nickname)
            if player:
                stats = client.get_player_lifetime_stats_by_id(player.id)
                
                cached_stats = PlayerStats(
                    user_id=user.id,
                    pubg_id=player.id,
                    stats_json=stats.to_dict() if stats else {},
                    match_ids=getattr(player, 'match_ids', [])
                )
                db.session.add(cached_stats)
                db.session.commit()
                
                player_stats = ParsedPlayerStats.from_json(cached_stats.stats_json) if cached_stats.stats_json else None
                updated_at = cached_stats.updated_at
                match_ids = cached_stats.match_ids or []
                
        except Exception as e:
            current_app.logger.error(f"Error fetching initial stats: {str(e)}", exc_info=True)
            flash(f"Ошибка при получении данных: {str(e)}", "error")

    return render_template('admin/users/user_profile.html', 
                         user=user, 
                         stats=player_stats, 
                         updated_at=updated_at,
                         match_ids=match_ids)

# Страница со списком задач
@admin_bp.route('/tasks')
@role_required(RoleEnum.ADMIN)
def tasks():
    tasks_dir = Path("pubg_api/tasks")  # Путь к папке с задачами
    task_functions = []
    job_list = [] # Список текущих задач в планировщике

    # Импортируем модуль tasks и получаем все функции
    for module_info in pkgutil.iter_modules([str(tasks_dir)]):
        
        module_name = f"pubg_api.tasks.{module_info.name}"
        try:
            module = importlib.import_module(module_name)
            
            functions = getmembers(module, isfunction)
            
            for func_name, func_obj in functions:
                if (
                    not func_name.startswith("_") 
                    and func_obj.__module__ == module_name
                ):
                    task_functions.append(func_name)
        except Exception as e:
            print(f"Ошибка в модуле {module_name}: {e}")

    jobs = scheduler.get_jobs()

    for job in jobs:
        # Получаем следующую запланированную дату запуска через триггер
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        next_run = job.trigger.get_next_fire_time(None, now)
        formatted_date = next_run.strftime('%d.%m.%Y %H:%M:%S') if next_run else 'Не запланировано'
        job_list.append(
            f"ID: {job.id}<br> Функция: {job.name}<br> Триггер: {job.trigger}<br> Следующий запуск: {formatted_date or 'Не запланировано'}"
        )

    tasks = ScheduledTask.query.all()
    return render_template('admin/tasks/tasks.html', tasks=tasks, funcs = task_functions, jobs = job_list)

# Добавление новой задачи
@admin_bp.route('/add_task', methods=['POST'])
@role_required(RoleEnum.ADMIN)
def add_task():
    name = request.form['name']
    function_name = request.form['function_name']
    interval_minutes = int(request.form['interval_minutes'])
    
    # Сохраняем в БД
    new_task = ScheduledTask(
        name=name,
        function_name=function_name,
        interval_minutes=interval_minutes,
        is_active=True
    )
    db.session.add(new_task)
    db.session.commit()
    
    # Запускаем задачу динамически
    add_periodic_task(new_task, current_app)
    
    return redirect('/admin/tasks')

# Удаление задачи
@admin_bp.route('/delete_task/<int:task_id>', methods=['POST'])
@role_required(RoleEnum.ADMIN)
def delete_task(task_id):
    task = ScheduledTask.query.get_or_404(task_id)
    
    # Останавливаем и удаляем из APScheduler
    remove_periodic_task(task)
    
    # Удаляем из БД
    db.session.delete(task)
    db.session.commit()
    
    return redirect('/admin/tasks')

# Включение/выключение задачи
@admin_bp.route('/toggle_task/<int:task_id>', methods=['POST'])
@role_required(RoleEnum.ADMIN)
def toggle_task_route(task_id):
    task = ScheduledTask.query.get_or_404(task_id)
    
    # Переключаем состояние в БД + в APScheduler
    toggle_task(task, not task.is_active, current_app)
    
    return redirect('/admin/tasks')

# Ручной запуск задачи
@admin_bp.route('/run_task/<int:task_id>', methods=['POST'])
@role_required(RoleEnum.ADMIN)
def run_task(task_id):
    task = ScheduledTask.query.get_or_404(task_id)
    run_task_now(task, current_app)
    return redirect('/admin/tasks')

# Просмотр деталей матча
@admin_bp.route('/match/<match_id>', methods=['GET'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def match_details(match_id):
    try:
        # Проверяем кеш в БД
        db_match = MatchStats.query.filter_by(match_id=match_id).first()
        
        if db_match:
            # Используем данные из БД
            match_data = MatchData(db_match.data_json)
        else:
            # Загружаем из API если нет в кеше
            try:
                match_data = client.get_match_by_id(match_id)
                if not match_data.raw_data or 'data' not in match_data.raw_data:
                    flash("Матч не найден", "danger")
                    return redirect(url_for('admin.admin'))
            except Exception as e:
                flash("Ошибка загрузки матча", "danger")
                current_app.logger.error(str(e))
                return redirect(url_for('admin.admin'))
            
            try:
                # Сохраняем в БД
                new_match = MatchStats(
                    match_id=match_id,
                    data_json=match_data.raw_data,
                    processed_at=datetime.now(ZoneInfo("Europe/Moscow"))
                )
                db.session.add(new_match)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Ошибка сохранения матча: {str(e)}")
                flash("Данные матча не сохранены в БД", "warning")
        
        # Получаем статистику игрока если указан
        player_name = request.args.get('player')
        player_stats = None
        
        if player_name:
            player_stats = match_data.get_detailed_player_stats(player_name)
        else:
            player_name = ""
        
        return render_template('public/matches/match_details.html', 
                            match=match_data,
                            player_stats=player_stats,
                            player_name=player_name)
                            
    except Exception as e:
        flash("Ошибка при загрузке данных матча", "error")

# Загрузка статистики по матчу в турнир через id матча
@admin_bp.route('/match/load_api_stats', methods=['POST'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def load_api_stats():
    match_id = request.form.get('match_id')
    current_match_id = request.form.get('current_match_id')
    
    if not match_id:
        return jsonify({'error': 'Не указан ID матча'}), 400
    
    try:
        # Получаем текущий матч из БД
        current_match = Match.query.get_or_404(current_match_id)
        tournament = current_match.tournament
        
        # Получаем данные матча из API
        match_data = client.get_match_by_id(match_id)
        if not match_data.raw_data or 'data' not in match_data.raw_data:
            return jsonify({'error': 'Матч не найден'}), 404
        
        # Собираем статистику для игроков турнира
        players_stats = []
        tournament_player_names = {p.nickname.lower(): p for p in tournament.players}
        
        for participant in match_data.participants:
            player_name = participant.get("name", "").lower()
            if player_name in tournament_player_names:
                stats = participant.get("stats", {})
                player = tournament_player_names[player_name]
                
                players_stats.append({
                    'player_id': player.id,
                    'kills': stats.get('kills', 0),
                    'damage': stats.get('damage_dealt', 0),
                    'placement': stats.get('win_place', 0)
                })
        
        return jsonify({
            'success': True,
            'players_stats': players_stats,
            'api_match_id': match_data.id,
            'map_name': match_data.map_name
        })
        
    except Exception as e:
        current_app.logger.error(f"Ошибка загрузки статистики: {str(e)}")
        return jsonify({'error': f'Ошибка сервера: {str(e)}'}), 500
    
# Список всех заявкок на вступление в клан
@admin_bp.route('/join_requests', methods=['GET'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def join_requests():
    try:
        # Создаем кастомный порядок сортировки
        status_ordering = case(
            {
                RqStatusEnum.REVIEW: 1,
                RqStatusEnum.DECLINED: 2,
                RqStatusEnum.ACCEPTED: 3
            },
            value=JoinRequests.status
        )
        
        join_requests = JoinRequests.query.order_by(status_ordering).order_by(JoinRequests.created_at.asc()).all()

    except Exception as e:
        return jsonify({'error': f'Ошибка сервера: {str(e)}'}), 500

    return render_template('admin/join_requests/all_requests.html',
                           join_requests=join_requests)

# API запрос для обновления заявки в клан
@admin_bp.route('/api/join_requests', methods=['GET'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def api_join_requests():
    try:
        status_ordering = case(
            {
                RqStatusEnum.REVIEW: 1,
                RqStatusEnum.DECLINED: 2,
                RqStatusEnum.ACCEPTED: 3
            },
            value=JoinRequests.status
        )
        
        join_requests = JoinRequests.query.order_by(status_ordering).order_by(JoinRequests.created_at.asc()).all()
        
        # Преобразуем данные в JSON-формат
        requests_data = []
        for req in join_requests:
            requests_data.append({
                'id': req.id,
                'username': req.user.username,
                'status': req.status,
                'created_at': req.created_at.strftime('%d.%m.%Y %H:%M:%S'),
                # Добавьте другие нужные поля
            })
            
        return jsonify(requests_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Принятие заявки в клан
@admin_bp.route('/accept_join_request/<int:join_request_id>', methods=['POST'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def accept_join_request(join_request_id):
    try:
        user = get_current_user()
        join_request = JoinRequests.query.get_or_404(join_request_id)
        join_request.status = RqStatusEnum.ACCEPTED
        join_request.moderator_id = user.id
        join_request.moderate_at = datetime.now(ZoneInfo("Europe/Moscow"))

        join_request.user.role = RoleEnum.CLAN_MEMBER
        
        db.session.flush()
        log(f"{user.username} принял заявку в клан от {join_request.user.username}")
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f"Заявка от {join_request.user.username} принята!",
            'request_id': join_request_id,
            'new_status': 'Принята',
            'moderator': user.username
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    

# Отклонение заявки в клан
@admin_bp.route('/decline_join_request/<int:join_request_id>', methods=['POST'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def decline_join_request(join_request_id):
    try:
        user = get_current_user()
        reason = request.json.get('reason')
        
        if not reason:
            return jsonify({'error': 'Укажите причину отказа'}), 400
            
        join_request = JoinRequests.query.get_or_404(join_request_id)
        join_request.status = RqStatusEnum.DECLINED
        join_request.moderator_id = user.id
        join_request.moderate_at = datetime.now(ZoneInfo("Europe/Moscow"))
        join_request.reason = reason
        
        db.session.flush()
        log(f"{user.username} отклонил заявку в клан от {join_request.user.username}")
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f"Заявка от {join_request.user.username} отклонена",
            'request_id': join_request_id,
            'new_status': 'Отклонена',
            'moderator': user.username,
            'reason': reason
        })

    except Exception as e:
        return jsonify({'error': f'Ошибка сервера: {str(e)}'}), 500
    
# Удаление заявки в клан
@admin_bp.route('/delete_join_request/<int:join_request_id>', methods=['POST'])
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def delete_join_request(join_request_id):
    try:
        user = get_current_user()
        join_request = JoinRequests.query.get_or_404(join_request_id)
        
        
        log(f"{user.username} удалил заявку {join_request.user.username}")
        db.session.delete(join_request)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f"Заявка № {join_request_id} удалена"
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500