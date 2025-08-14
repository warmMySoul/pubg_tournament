from datetime import datetime
import os
from pathlib import Path
import sys
import time
from collections import deque
from zoneinfo import ZoneInfo
import requests
from dotenv import load_dotenv

# Добавляем родительскую директорию в Python path
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from extensions.db_connection import db
from models import *
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Настройка SQLAlchemy
engine = create_engine('sqlite:///instance/tournament.db')
Session = sessionmaker(bind=engine)

class PUBGApiClient:
    BASE_URL = "https://api.pubg.com"
    RATE_LIMIT = 10  # Максимум 10 запросов в минуту

    def __init__(self, api_key: str = os.getenv("PUBG_API_KEY_1")):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/vnd.api+json"
        }
        self.request_timestamps = deque(maxlen=self.RATE_LIMIT)
    
    def _check_rate_limit(self):
        """Проверяет, не превышен ли лимит запросов."""
        if len(self.request_timestamps) >= self.RATE_LIMIT:
            time_elapsed = time.time() - self.request_timestamps[0]
            if time_elapsed < 60:
                raise Exception("Rate limit exceeded. Wait 60 seconds.")
    
    def _get(self, endpoint: str):
        self._check_rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        response = requests.get(url, headers=self.headers)
        self.request_timestamps.append(time.time())  # Фиксируем время запроса

        if response.status_code == 429:
            raise Exception("Rate limit exceeded (429)")
        if not response.ok:
            raise Exception(f"API Error: {response.status_code}, {response.text}")

        return response.json()

    # Получение данных игрока по нику
    def get_player_by_name(self, player_name: str, shard: str = "steam"):
        endpoint = f"/shards/{shard}/players?filter[playerNames]={player_name}"
        response = self._get(endpoint)
        player_data = response["data"][0]
        
        player_id = player_data.get("id")
        player_name = player_data["attributes"].get("name")
        clan_id = player_data["attributes"].get("clanId")
        matches = [match["id"] for match in player_data["relationships"]["matches"]["data"]]

        session = Session()  # Создаем новую сессию
        try:
            user = session.query(User).filter_by(pubg_nickname=player_name).first()
            if not user:
                raise Exception(f"Пользователь с ником {player_name} не найден в БД")

            if clan_id == "clan.ad9293ce262f4c9e847ef73b3f2190b3":
                user.role = "clan_member"
                session.add(user)

            player_stats = session.query(PlayerStats).filter_by(pubg_id=player_id).first()
            if player_stats:
                player_stats.match_ids = matches
                player_stats.updated_at = datetime.now(ZoneInfo("Europe/Moscow"))
            else:
                new_player_stats = PlayerStats(
                    user_id=user.id,
                    pubg_id=player_id,
                    stats_json={},
                    match_ids=matches,
                    updated_at=datetime.now(ZoneInfo("Europe/Moscow"))
                )
                session.add(new_player_stats)

            session.commit()
            return "200 OK"

        except Exception as e:
            session.rollback()
            print(f"Error: {str(e)}")
            raise
        finally:
            session.close()
    
    # Получение статистики игрока за все время по id
    def get_player_lifetime_stats_by_id(self, player_id: str, shard="steam"):
        endpoint = f"/shards/{shard}/players/{player_id}/seasons/lifetime"
        response = self._get(endpoint)
        player_data = response["data"]["attributes"]["gameModeStats"]

        # Фильтруем только FPP-режимы (заканчиваются на "-fpp")
        fpp_stats = {
            mode: stats 
            for mode, stats in player_data.items() 
            if mode.endswith("-fpp")
        }
        session = Session()  # Создаем новую сессию
        try:
            player_stats = session.query(PlayerStats).filter_by(pubg_id=player_id).first()
            if player_stats:
                player_stats.stats_json = fpp_stats
                player_stats.updated_at = datetime.now(ZoneInfo("Europe/Moscow"))
            else:
                raise Exception(f"Пользователь с pubg_id {player_id} не найден в БД")

            session.commit()
            return "200 OK"

        except Exception as e:
            session.rollback()
            print(f"Error: {str(e)}")
            raise
        finally:
            session.close()

    # Получение данных матча по id
    def get_match_by_id(self, match_id, shard="steam"):
        endpoint = f"/shards/{shard}/matches/{match_id}"
        response = self._get(endpoint)
        match_data = response

        session = Session()  # Создаем новую сессию
        try:
            match_stats = session.query(MatchStats).filter_by(match_id=match_id).first()
            if (match_stats):
                raise Exception(f"Статика этого матча уже сохранена")
            
            new_match_stats = MatchStats(
                    match_id=match_id,
                    data_json=match_data,
                    processed_at=datetime.now(ZoneInfo("Europe/Moscow"))
                )
            session.add(new_match_stats)

            session.commit()
            return match_data

        except Exception as e:
            session.rollback()
            print(f"Error: {str(e)}")
            raise
        finally:
            session.close()