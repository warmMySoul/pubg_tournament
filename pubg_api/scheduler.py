from apscheduler.schedulers.background import BackgroundScheduler
from pubg_api.utils.update_all_player_stats import update_all_player_stats

def start_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=lambda: update_all_player_stats(app), trigger='interval', hours=3)
    scheduler.start()

#minutes=15 — каждые 15 минут
#hours=3 — каждые 3 часа
#days=1 — раз в день
#seconds=10 — каждые 10 секунд (удобно для тестов)