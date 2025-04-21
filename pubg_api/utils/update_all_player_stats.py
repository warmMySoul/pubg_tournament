from zoneinfo import ZoneInfo
from pubg_api.client import PUBGApiClient
from models import User, PlayerStats
from db_connection import db
from datetime import datetime
import time

pubg_api = PUBGApiClient()

# Импорт логирования
from services.admin_log_service import log_admin_action as log

def update_all_player_stats(app):
    with app.app_context():
        # Правильный запрос для получения нужных пользователей
        users = User.query.filter(
            User.role.in_(["admin", "moderator", "clan_member"])
        ).all()
        
        request_count = 0
        total_users = len(users)-1
        processed_users = 0

        for user in users:
            try:
                # Пропускаем админа (если нужно)
                if user.username == "admin":
                    continue

                # Получаем кэш, если есть
                cached = PlayerStats.query.filter_by(user_id=user.id).first()

                # Если pubg_id ещё не сохранён — получаем его
                if not cached or not cached.pubg_id:
                    if request_count >= 10:
                        time.sleep(60)
                        request_count = 0
                    
                    player = pubg_api.get_player_by_name(user.pubg_nickname)
                    pubg_id = player.id
                    request_count += 1

                    if not cached:
                        cached = PlayerStats(user_id=user.id, pubg_id=pubg_id)
                        db.session.add(cached)
                    else:
                        cached.pubg_id = pubg_id

                    db.session.commit()

                # Получаем статистику по ID
                if request_count >= 10:
                    time.sleep(60)
                    request_count = 0
                
                stats = pubg_api.get_player_lifetime_stats_by_id(cached.pubg_id)
                cached.stats_json = stats.to_dict()
                cached.updated_at = datetime.now(ZoneInfo("Europe/Moscow"))
                db.session.commit()
                request_count += 1

                processed_users += 1

            except Exception as e:
                log(f"Ошибка обновления статистики для пользователя {user.username}: {str(e)}")
                db.session.rollback()
                processed_users += 1
                continue

            # Добавляем небольшую задержку между запросами
            time.sleep(1)

        log("Обновление статистики по участникам клана выполнено")