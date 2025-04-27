from datetime import datetime
import pandas as pd

# Проверка доступности регистрации
def registration_open(tournament):
    now = datetime.now()
    return tournament.reg_start <= now <= tournament.reg_end

# Максировка email
def mask_email(email):
    if not email or '@' not in email:
        return email
        
    username, domain = email.split('@', 1)
    if len(username) <= 3:
        masked = '*' * len(username)
    else:
        masked = username[:3] + '*' * (len(username) - 3)
    
    return f"{masked}@{domain}"

# Генерация данный о турнире для экспорта
def generate_export_data(tournament):
    sheets = {}

    # 1. Информация о турнире
    info = {
        "Название турнира": [tournament.name],
        "Режим": [tournament.mode],
        "Количество карт": [tournament.maps_count],
        "Очки за килл": [tournament.kill_points or 'Не задано'],
        "Очки за 1 место": [tournament.first_place_points or 'Не задано'],
        "Очки за 2 место": [tournament.second_place_points or 'Не задано'],
        "Очки за 3 место": [tournament.third_place_points or 'Не задано'],
        "Очки за урон": [tournament.damage_points or 'Не задано'],
    }
    sheets['Информация'] = pd.DataFrame(info)

    # 2. Состав команд
    players_data = []
    for group in tournament.player_groups:
        players_in_group = [player.user.pubg_nickname for player in group.players]
        players_data.append({
            "Команда": f"Группа {group.group_number}",
            "Игроки": ", ".join(players_in_group)
        })
    if not players_data:  # если соло
        for player in tournament.players:
            players_data.append({
                "Команда": "-",
                "Игроки": player.user.pubg_nickname
            })
    sheets['Состав команд'] = pd.DataFrame(players_data)

    # 3. Итоговая статистика турнира
    final_stats = []
    for group in tournament.player_groups:
        total_points = 0
        for player in group.players:
            player_points = sum(stat.points for stat in player.matches)
            final_stats.append({
                "Команда": f"Группа {group.group_number}",
                "Игрок": player.user.pubg_nickname,
                "Итоговые очки": player_points
            })
            total_points += player_points
        final_stats.append({
            "Команда": f"Группа {group.group_number}",
            "Игрок": "Сумма команды",
            "Итоговые очки": total_points
        })
    if not final_stats:  # если соло
        for player in tournament.players:
            player_points = sum(stat.points for stat in player.matches)
            final_stats.append({
                "Команда": "-",
                "Игрок": player.user.pubg_nickname,
                "Итоговые очки": player_points
            })
    sheets['Итоги турнира'] = pd.DataFrame(final_stats)

    # 4. Детальная статистика по матчам
    match_details = []
    for match in tournament.matches:
        for stat in match.players_stats:
            player = stat.player.user.pubg_nickname
            group = stat.player.group.group_number if stat.player.group else "-"
            match_details.append({
                "Карта №": match.map_number,
                "Команда": f"Группа {group}" if group != "-" else "-",
                "Игрок": player,
                "Убийства": stat.kills,
                "Очки за убийства": stat.kills * (tournament.kill_points or 0),
                "Место": stat.placement,
                "Очки за место": calc_place_points(stat.placement, tournament),
                "Урон": stat.damage_dealt,
                "Очки за урон": stat.damage_dealt * (tournament.damage_points or 0),
                "Всего очков": stat.points
            })
    sheets['Матчи'] = pd.DataFrame(match_details)

    return sheets

def calc_place_points(placement, tournament):
    if not placement:
        return 0
    if placement == 1:
        return tournament.first_place_points or 0
    elif placement == 2:
        return tournament.second_place_points or 0
    elif placement == 3:
        return tournament.third_place_points or 0
    else:
        return 0