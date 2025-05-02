from zoneinfo import ZoneInfo
from pubg_api.client import PUBGApiClient
from models import User, PlayerStats
from extensions.db_connection import db
from datetime import datetime
import time

from flask import Flask

# Импорт логирования
from services.admin_log_service import log_admin_action as log

pubg_api = PUBGApiClient()

def update_all_player_stats(app: Flask):
    print("Func is work!")
    with app.app_context():  # Используем существующий app

        users = User.query.filter(
            User.role.in_(["admin", "moderator", "clan_member"])
        ).all()
        
        request_count = 0
        total_users = len(users)
        processed_users = 0

        for user in users:
            try:
                if user.username == "admin":
                    continue

                cached = PlayerStats.query.filter_by(user_id=user.id).first()

                # Получение pubg_id
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

                # Получение статистики
                if request_count >= 10:
                    time.sleep(60)
                    request_count = 0
                
                stats = pubg_api.get_player_lifetime_stats_by_id(cached.pubg_id)
                cached.stats_json = stats.to_dict()
                cached.updated_at = datetime.now(ZoneInfo("Europe/Moscow"))
                db.session.commit()
                request_count += 1

                processed_users += 1  # ✅ Увеличиваем счётчик

                time.sleep(1)

            except Exception as e:
                log(f"Ошибка обновления статистики для {user.username}: {str(e)}", True)
                db.session.rollback()
                continue

        log("Обновление статистики по участникам клана прошло успешно", True)
        return {
            "status": "success",
            "processed": processed_users,
            "total": total_users
        }
