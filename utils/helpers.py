from datetime import datetime
import io
import pandas as pd
import xlsxwriter
import os

from models.match import Match

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
    # ... ваш существующий код generate_export_data без изменений ...
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
    if tournament.mode == 'SOLO':
        for player in tournament.players:
            players_data.append({
                "Команда": "-",
                "Игроки": player.user.pubg_nickname
            })
    else:
        for group in tournament.player_groups:
            players_in_group = [player.user.pubg_nickname for player in group.players]
            players_data.append({
                "Команда": f"Группа {group.group_number}",
                "Игроки": ", ".join(players_in_group)
            })
    sheets['Состав команд'] = pd.DataFrame(players_data)

    # 3. Итоговая статистика турнира
    final_stats = []
    if tournament.mode == 'SOLO':
        for player in tournament.players:
            player_stats = {
                "Команда": "-",
                "Игрок": player.user.pubg_nickname,
                "Убийства": 0,
                "Урон": 0.0,
                "Итоговые очки": 0.0
            }
            
            for match_stat in player.matches:
                player_stats["Убийства"] += match_stat.kills
                player_stats["Урон"] += match_stat.damage_dealt
                
                # Расчет очков по правилам турнира
                kill_points = match_stat.kills * (tournament.kill_points or 0)
                damage_points = (match_stat.damage_dealt / 100) * (tournament.damage_points or 0)
                place_points = 0
                
                if match_stat.placement == 1 and tournament.first_place_points:
                    place_points = tournament.first_place_points
                elif match_stat.placement == 2 and tournament.second_place_points:
                    place_points = tournament.second_place_points
                elif match_stat.placement == 3 and tournament.third_place_points:
                    place_points = tournament.third_place_points
                
                player_stats["Итоговые очки"] += kill_points + damage_points + place_points
            
            final_stats.append(player_stats)
    else:
        # Для командных режимов используем новый метод get_tournament_group_stats
        for group in tournament.player_groups:
            group_stats = group.get_tournament_group_stats()
            if not group_stats:
                continue
                
            # Сначала добавляем статистику команды
            final_stats.append({
                "Команда": f"Группа {group.group_number}",
                "Игрок": "ВСЕГО КОМАНДА",
                "Убийства": group_stats['total_kills'],
                "Урон": group_stats['total_damage'],
                "Итоговые очки": group_stats['total_points']
            })
            
            # Затем статистику каждого игрока
            for player_stat in group_stats['players']:
                player = next((p for p in group.players if p.id == player_stat['player_id']), None)
                if player:
                    final_stats.append({
                        "Команда": f"Группа {group.group_number}",
                        "Игрок": player.user.pubg_nickname,
                        "Убийства": player_stat['total_kills'],
                        "Урон": player_stat['total_damage'],
                        "Итоговые очки": player_stat['total_points']
                    })
    
    sheets['Итоги турнира'] = pd.DataFrame(final_stats)

    # 4. Детальная статистика по матчам
    match_details = []
    if tournament.mode == 'SOLO':
        for match in tournament.matches:
            for stat in match.players_stats:
                player = stat.player
                kill_points = stat.kills * (tournament.kill_points or 0)
                damage_points = (stat.damage_dealt / 100) * (tournament.damage_points or 0)
                place_points = 0
                
                if stat.placement == 1 and tournament.first_place_points:
                    place_points = tournament.first_place_points
                elif stat.placement == 2 and tournament.second_place_points:
                    place_points = tournament.second_place_points
                elif stat.placement == 3 and tournament.third_place_points:
                    place_points = tournament.third_place_points
                
                match_details.append({
                    "Карта №": match.map_number,
                    "Команда": "-",
                    "Игрок": player.user.pubg_nickname,
                    "Убийства": stat.kills,
                    "Очки за убийства": kill_points,
                    "Место": stat.placement,
                    "Очки за место": place_points,
                    "Урон": stat.damage_dealt,
                    "Очки за урон": damage_points,
                    "Всего очков": kill_points + damage_points + place_points
                })
    else:
        # Для командных режимов используем данные из group_stats
        for group in tournament.player_groups:
            group_stats = group.get_tournament_group_stats()
            if not group_stats:
                continue
                
            for match_stat in group_stats['matches']:
                match = Match.query.get(match_stat['match_id'])
                if not match:
                    continue
                
                # Добавляем общую статистику команды за матч
                match_details.append({
                    "Карта №": match.map_number,
                    "Команда": f"Группа {group.group_number}",
                    "Игрок": "КОМАНДА",
                    "Убийства": match_stat['total_kills'],
                    "Очки за убийства": match_stat['kills_points'],
                    "Место": match_stat['placement'],
                    "Очки за место": match_stat['placement_points'],
                    "Урон": match_stat['total_damage'],
                    "Очки за урон": match_stat['damage_points'],
                    "Всего очков": match_stat['total_points']
                })
                
                # Добавляем статистику игроков за этот матч
                for player in group.players:
                    player_match_stat = next(
                        (stat for stat in player.matches if stat.match_id == match.id),
                        None
                    )
                    if player_match_stat:
                        kill_points = player_match_stat.kills * (tournament.kill_points or 0)
                        damage_points = (player_match_stat.damage_dealt / 100) * (tournament.damage_points or 0)
                        
                        match_details.append({
                            "Карта №": match.map_number,
                            "Команда": f"Группа {group.group_number}",
                            "Игрок": player.user.pubg_nickname,
                            "Убийства": player_match_stat.kills,
                            "Очки за убийства": kill_points,
                            "Место": player_match_stat.placement,
                            "Очки за место": 0,  # В командных режимах очки за место идут команде
                            "Урон": player_match_stat.damage_dealt,
                            "Очки за урон": damage_points,
                            "Всего очков": kill_points + damage_points
                        })
    
    sheets['Матчи'] = pd.DataFrame(match_details)

    return sheets

def export_to_excel_styled(tournament):
    """Экспорт в Excel с расширенной стилизацией - в памяти"""
    sheets = generate_export_data(tournament)
    
    # Создаем файл в памяти
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # Палитра цветов
        colors = {
            'header': '#4472C4',
            'team_total': '#F2F2F2',
            'player': '#FFFFFF',
            'border': '#D9D9D9',
            'title': '#E6E6E6'
        }
        
        # Стили
        formats = {
            'header': workbook.add_format({
                'bold': True, 'bg_color': colors['header'], 'font_color': 'white',
                'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True
            }),
            'team_total': workbook.add_format({
                'bold': True, 'bg_color': colors['team_total'], 'border': 1,
                'align': 'left', 'valign': 'vcenter'
            }),
            'player': workbook.add_format({
                'bg_color': colors['player'], 'border': 1,
                'align': 'left', 'valign': 'vcenter'
            }),
            'number': workbook.add_format({
                'border': 1, 'align': 'right', 'valign': 'vcenter',
                'num_format': '0.00'
            }),
            'integer': workbook.add_format({
                'border': 1, 'align': 'right', 'valign': 'vcenter',
                'num_format': '0'
            }),
            'title': workbook.add_format({
                'bold': True, 'font_size': 16, 'align': 'center',
                'valign': 'vcenter', 'bg_color': colors['title']
            })
        }
        
        for sheet_name, df in sheets.items():
            # Записываем DataFrame с отступом для заголовка
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=2)
            worksheet = writer.sheets[sheet_name]
            
            # Заголовок листа
            title_text = f'{tournament.name} - {sheet_name}'
            last_col = chr(64 + len(df.columns))  # Последняя колонка в буквенном формате
            worksheet.merge_range(f'A1:{last_col}1', title_text, formats['title'])
            
            # Стилизация заголовков столбцов
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(2, col_num, value, formats['header'])
            
            # Стилизация данных
            for row_num in range(3, len(df) + 3):
                row_data = df.iloc[row_num-3]
                is_team_row = any(keyword in str(row_data.values) 
                                for keyword in ['ВСЕГО КОМАНДА', 'КОМАНДА', 'Сумма команды'])
                
                for col_num in range(len(df.columns)):
                    cell_value = row_data.iloc[col_num]
                    col_name = df.columns[col_num]
                    
                    # Выбираем формат в зависимости от типа данных и контекста
                    if is_team_row:
                        cell_format = formats['team_total']
                    else:
                        cell_format = formats['player']
                    
                    # Определяем числовой формат
                    if isinstance(cell_value, (int, float)) and not pd.isna(cell_value):
                        if 'урон' in col_name.lower() or 'очки' in col_name.lower():
                            cell_format = formats['number']
                        elif 'убийства' in col_name.lower() or 'место' in col_name.lower():
                            cell_format = formats['integer']
                        else:
                            cell_format = formats['number']
                    
                    worksheet.write(row_num, col_num, cell_value, cell_format)
            
            # Автоматическая ширина столбцов
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).str.len().max(), len(col)) + 3
                worksheet.set_column(i, i, min(max_len, 30))
            
            # Замораживаем заголовки
            worksheet.freeze_panes(3, 0)
            
            # Добавляем условное форматирование для очков
            points_columns = [col for col in df.columns if 'очки' in col.lower() or 'баллы' in col.lower()]
            for points_col in points_columns:
                if points_col in df.columns:
                    col_idx = df.columns.get_loc(points_col)
                    # Data bars для визуализации результатов
                    worksheet.conditional_format(3, col_idx, len(df) + 2, col_idx, {
                        'type': 'data_bar',
                        'bar_color': '#63C384',
                        'bar_solid': True
                    })
    
    # Важно: перемещаем указатель в начало файла
    output.seek(0)
    
    return output

# Функция для использования в контроллере Flask
def export_tournament_stats(tournament):
    """Основная функция для экспорта статистики турнира"""
    try:
        file_buffer = export_to_excel_styled(tournament)
        return file_buffer
    except Exception as e:
        print(f"Ошибка при экспорте: {e}")
        return None