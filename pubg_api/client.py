import os
import time
import requests
from flask import has_request_context, flash
from dotenv import load_dotenv
from datetime import datetime
from models import Player, PlayerStats

# Импорт логирования
from services.admin_log_service import log_admin_action as log

from pubg_api.models import Player, ParsedPlayerStats

load_dotenv("secrets.env")

class PUBGApiException(Exception):
    pass

class PUBGApiClient:
    BASE_URL = "https://api.pubg.com"
    RATE_LIMIT = 10  # максимум 10 запросов в минуту
    MAX_QUEUE_SIZE = 30 # максимум в очереди

    def __init__(self):
        self.api_key = os.getenv("PUBG_API_KEY")
        if not self.api_key:
            raise PUBGApiException("PUBG_API_KEY не задан в .env файле")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/vnd.api+json"
        }
        
        self.request_timestamps = []


    def _rate_limit_guard(self):
        now = datetime.now()

        # Очистим старые таймстемпы (старше 60 секунд)
        self.request_timestamps = [
            ts for ts in self.request_timestamps if (now - ts).total_seconds() < 60
        ]

        if len(self.request_timestamps) < self.RATE_LIMIT:
            # Можно делать запрос
            self.request_timestamps.append(now)
            return

        # Если очередь переполнена
        if len(self.request_timestamps) >= self.RATE_LIMIT + self.MAX_QUEUE_SIZE:
            if has_request_context():
                flash("Очередь обновлений переполнена. Попробуйте позже.", "error")
            raise PUBGApiException("Очередь переполнена")

        # В очереди, ждём
        earliest = self.request_timestamps[0]
        delta = (now - earliest).total_seconds()
        sleep_time = 60 - delta

        if has_request_context():
            flash(f"[Обновление игровых данных] Вы добавлены в очередь. Примерное время ожидания: {sleep_time:.1f} сек...", "success")

        time.sleep(sleep_time)

        # После ожидания снова пробуем
        self._rate_limit_guard()


    def _get(self, endpoint: str):
        self._rate_limit_guard()
        url = f"{self.BASE_URL}{endpoint}"
        response = requests.get(url, headers=self.headers)

        if response.status_code == 429:
            raise PUBGApiException("Rate limit exceeded (429)")
        if not response.ok:
            raise PUBGApiException(f"Ошибка при запросе к PUBG API: {response.status_code}, {response.text}")

        return response.json()

    # Получить данные по игроку
    def get_player_by_name(self, player_name: str, shard: str = "steam") -> Player:
        endpoint = f"/shards/{shard}/players?filter[playerNames]={player_name}"
        response = self._get(endpoint)
        data = response.get("data")
        if not data:
            raise PUBGApiException(f"Игрок с именем '{player_name}' не найден.")
        return Player(data[0])
    
    # Получить статистик за все время по нику игрока
    def get_player_lifetime_stats_by_id(self, player_id: str, shard="steam") -> PlayerStats:
        endpoint = f"/shards/{shard}/players/{player_id}/seasons/lifetime"
        data = self._get(endpoint)
        return ParsedPlayerStats(data)


    # Получить матч по ID
    def get_match_by_id(self, match_id, shard="steam"):
        endpoint = f"/shards/{shard}/matches/{match_id}"
        return self._get(endpoint)
