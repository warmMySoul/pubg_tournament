from io import BytesIO
import uuid
from zoneinfo import ZoneInfo
from flask import Blueprint, flash, url_for, redirect, request, render_template, jsonify
from datetime import datetime
from flask import send_file
from openpyxl import Workbook
from sqlalchemy import func
from extensions.security import get_current_user, role_required
from models import RoleEnum, Tournament, PlayerGroup, Player, AdminActionLog, User, Match, PlayerMatchStats
from extensions.db_connection import db

# Импорт логирования
from services.admin_log_service import log_admin_action as log

from models.pubg_api_models import PlayerStats
from pubg_api.models.player import ParsedPlayerStats

# Импорт PUBG API
from pubg_api.client import PUBGApiClient
client = PUBGApiClient()


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Админ-панель
@admin_bp.route('/')
@role_required([RoleEnum.ADMIN, RoleEnum.MODERATOR])
def admin():
    return render_template('admin/admin.html')

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
    return render_template('admin/tournaments/players.html', 
                         tournament=tournament,
                         max_players=max_players)

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
            for player in tournament.players:
                kills = int(request.form.get(f'kills_{player.id}', 0))
                damage = float(request.form.get(f'damage_{player.id}', 0))
                placement = request.form.get(f'placement_{player.id}')
                
                # Ищем существующую статистику или создаем новую
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
                
                # Обновляем статистику
                stats.kills = kills
                stats.damage_dealt = damage
                stats.placement = int(placement) if placement else None
                
                # Рассчитываем очки
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
                
                # Обновляем общие очки игрока
                player.total_points = db.session.query(
                    func.sum(PlayerMatchStats.points)
                    .filter(PlayerMatchStats.player_id == player.id)).scalar() or 0
            
            # Помечаем матч как завершенный
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

    # Проверяем, есть ли сохраненные данные в PlayerStats
    cached_stats = PlayerStats.query.filter_by(user_id=user.id).first()
    
    if cached_stats:
        # Если есть кешированная статистика, берем pubg_id из таблицы
        try:
            player_stats = ParsedPlayerStats.from_json(cached_stats.stats_json)
            updated_at = cached_stats.updated_at            
        except Exception as e:
            flash(f"Возникли ошибки при загрузке статистики. Попробуйте позже.", 'warning')
    else:
        # Если нет кешированных данных, получаем через API
        try:
            player = client.get_player_by_name(user.pubg_nickname)
            if player:
                try:
                    player_stats = client.get_player_lifetime_stats_by_id(player.id)
                    
                    # Сохраняем данные в PlayerStats
                    cached_stats = PlayerStats(
                        user_id=user.id,
                        pubg_id=player.id,
                        stats_json=player_stats.to_dict()
                    )
                    db.session.add(cached_stats)
                    db.session.commit()
                    updated_at = cached_stats.updated_at
                except Exception as e:
                    db.session.rollback()
                    flash(f"Статистика временно недоступна.", 'error')
        except Exception as e:
            flash(f"Игрока с таким ником не найдено. Проверьте ник.", 'error')

    if request.method == 'POST':
        try:
            # Получаем свежую статистику
            stats = client.get_player_lifetime_stats_by_id(cached_stats.pubg_id)

            cached_stats.stats_json = stats.to_dict()
            cached_stats.updated_at = datetime.now(ZoneInfo("Europe/Moscow"))

            db.session.commit()
            flash(f"Статистика обновлена", 'success')
            return jsonify({"success": True})

        except Exception as e:
                flash(f"Ошибка для пользователя {user.username}: {str(e)}")
                db.session.rollback()
                return jsonify({"success": False})
        


    return render_template('admin/users/user_profile.html', 
                         user=user, 
                         stats=player_stats, 
                         updated_at=updated_at)

