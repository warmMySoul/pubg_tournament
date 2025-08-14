from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

@dataclass
class PlayerMatchStats:
    """Детальная статистика игрока в матче"""
    kills: int = 0
    assists: int = 0
    damage_dealt: float = 0.0
    headshot_kills: int = 0
    longest_kill: float = 0.0
    revives: int = 0
    ride_distance: float = 0.0
    walk_distance: float = 0.0
    time_survived: float = 0.0  # в секундах
    win_place: int = 0  # занятое место
    weapons_acquired: int = 0
    death_type: Optional[str] = None
    vehicle_destroys: int = 0
    dbnos: int = 0  # нокдауны
    team_rank: int = 0  # место команды


class MatchData:
    def __init__(self, api_data: dict):
        """
        Полная модель матча из PUBG API
        
        Args:
            api_data: Сырой JSON-ответ от API /matches/{match_id}
        """
        if not isinstance(api_data, dict):
            raise ValueError("Input must be a dictionary")
        
        self._raw_data = api_data
        self._data = api_data.get("data", {})
        self._included = api_data.get("included", [])
        
        # Инициализация всех полей по умолчанию
        self.id = ""
        self.type = ""
        self.created_at = ""
        self.duration = 0
        self.game_mode = ""
        self.map_name = ""
        self.is_custom_match = False
        self.season_state = ""
        self.shard_id = ""
        self.title_id = ""
        self.rosters = []
        self.participants = []
        self.assets = []
        self.telemetry_url = None
        
        self._parse_data()

    def _parse_data(self):
        """Основной метод парсинга данных"""
        if not self._data:
            logger.error("Empty data in match response")
            return
            
        # Основные поля матча
        self.id = self._data.get("id", "")
        self.type = self._data.get("type", "match")
        
        # Атрибуты матча
        attributes = self._data.get("attributes", {})
        self._parse_attributes(attributes)
        
        # Обработка связей
        relationships = self._data.get("relationships", {})
        self._process_relationships(relationships)
        
        # Обработка включенных данных
        self._process_included()
        
        # Связывание данных
        self._link_team_ranks()

    def _parse_attributes(self, attributes: dict):
        """Парсинг атрибутов матча"""
        iso_created_at = attributes.get("createdAt", "")
        self.created_at = self._format_created_at(iso_created_at)
        self.duration = int(attributes.get("duration", 0))
        self.game_mode = attributes.get("gameMode", "")
        self.map_name = attributes.get("mapName", "")
        self.is_custom_match = bool(attributes.get("isCustomMatch", False))
        self.season_state = attributes.get("seasonState", "")
        self.shard_id = attributes.get("shardId", "")
        self.title_id = attributes.get("titleId", "")

    def _format_created_at(self, iso_str):
        """Форматирование даты"""
        if not iso_str:
            return ""

        try:
            dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            dt_moscow = dt.astimezone(ZoneInfo("Europe/Moscow"))
            return dt_moscow.strftime("%d.%m.%Y %H:%M:%S")
        except Exception as e:
            logger.error(f"Error parsing date: {e}")
            return iso_str 

    def _process_relationships(self, relationships: dict):
        """Обработка связей матча"""
        assets = relationships.get("assets", {}).get("data", [])
        if assets and isinstance(assets, list):
            self.assets = assets
            # Находим URL телеметрии в included данных
            self._find_telemetry_url()

    def _find_telemetry_url(self):
        """Поиск URL телеметрии в included данных"""
        for item in self._included:
            if isinstance(item, dict) and item.get("type") == "asset":
                attributes = item.get("attributes", {})
                if "URL" in attributes:
                    self.telemetry_url = attributes["URL"]
                    break

    def _process_included(self):
        """Обработка включенных данных"""
        if not self._included:
            return
            
        # Сначала обрабатываем ростеры
        rosters = [item for item in self._included 
                  if isinstance(item, dict) and item.get("type") == "roster"]
        
        for roster_item in rosters:
            self._process_roster(roster_item)
        
        # Затем участников
        participants = [item for item in self._included 
                       if isinstance(item, dict) and item.get("type") == "participant"]
        
        for participant_item in participants:
            self._process_participant(participant_item)

    def _process_roster(self, roster_item: dict):
        """Обработка данных команды/роста"""
        attributes = roster_item.get("attributes", {})
        stats = attributes.get("stats", {})
        
        roster = {
            "id": roster_item.get("id"),
            "won": stats.get("won", False),
            "rank": stats.get("rank", 0),
            "team_id": stats.get("teamId"),
            "participants": []
        }
        self.rosters.append(roster)

    def _process_participant(self, participant_item: dict):
        """Обработка данных участника"""
        attributes = participant_item.get("attributes", {})
        stats = attributes.get("stats", {})
        relationships = participant_item.get("relationships", {})
        
        participant = {
            "id": participant_item.get("id"),
            "player_id": stats.get("playerId"),
            "name": stats.get("name"),
            "roster_id": relationships.get("roster", {}).get("data", {}).get("id"),
            "stats": PlayerMatchStats(
                kills=stats.get("kills", 0),
                assists=stats.get("assists", 0),
                damage_dealt=stats.get("damageDealt", 0.0),
                headshot_kills=stats.get("headshotKills", 0),
                longest_kill=stats.get("longestKill", 0.0),
                revives=stats.get("revives", 0),
                ride_distance=stats.get("rideDistance", 0.0),
                walk_distance=stats.get("walkDistance", 0.0),
                time_survived=stats.get("timeSurvived", 0),
                win_place=stats.get("winPlace", 0),
                death_type=stats.get("deathType"),
                vehicle_destroys=stats.get("vehicleDestroys", 0),
                dbnos=stats.get("DBNOs", 0),
                team_rank=0  # Временное значение, будет обновлено в _link_team_ranks
            )
        }
        self.participants.append(participant)

    def _link_team_ranks(self):
        """Связываем ранги команд с игроками"""
        roster_ranks = {roster["id"]: roster.get("rank", 0) for roster in self.rosters}
        
        for participant in self.participants:
            if isinstance(participant.get("stats"), PlayerMatchStats):
                participant["stats"].team_rank = roster_ranks.get(participant["roster_id"], 0)

    def get_detailed_player_stats(self, player_name: str) -> Optional[PlayerMatchStats]:
        """Получение детальной статистики игрока"""
        if not player_name:
            return None
            
        for participant in self.participants:
            if participant.get("name") == player_name:
                return participant.get("stats")
        return None

    def get_player_performance_summary(self, player_id: str) -> Optional[Dict]:
        """Сводка производительности игрока"""
        stats = self.get_detailed_player_stats(player_id)
        if not stats:
            return None

        try:
            total_distance = stats.ride_distance + stats.walk_distance
            return {
                "kills": stats.kills,
                "damage": round(stats.damage_dealt),
                "headshots": stats.headshot_kills,
                "team_place": stats.team_rank,
                "survival_time": self._format_time(stats.time_survived),
                "distance_traveled": f"{total_distance/1000:.1f} km",
                "longest_kill": f"{stats.longest_kill:.0f} m",
                "revives": stats.revives,
                "position": stats.win_place
            }
        except Exception as e:
            logger.error(f"Failed to generate performance summary: {str(e)}")
            return None

    def _format_time(self, seconds: float) -> str:
        """Форматирование времени"""
        try:
            minutes, sec = divmod(int(seconds), 60)
            return f"{minutes}:{sec:02d}"
        except:
            return "0:00"

    def get_top_players(self, count: int = 5) -> List[Tuple[str, int]]:
        """Топ игроков по убийствам"""
        players = []
        for participant in self.participants:
            stats = participant.get("stats", {})
            players.append((
                participant.get("name", "Unknown"),
                stats.get("kills", 0),
                stats.get("damage_dealt", 0)
            ))
        
        players.sort(key=lambda x: (-x[1], -x[2]))
        return [(name, kills) for name, kills, _ in players[:count]]

    def get_winner(self) -> Optional[Dict]:
        """Победившая команда"""
        for roster in self.rosters:
            if roster.get("won"):
                return roster
        return None

    def get_player_stats(self, player_id: str) -> Optional[Dict]:
        """Статистика игрока"""
        for participant in self.participants:
            if participant.get("player_id") == player_id:
                return participant.get("stats")
        return None

    def to_dict(self) -> Dict:
        """Сериализация в словарь"""
        return {
            "id": self.id,
            "type": self.type,
            "created_at": self.created_at,
            "duration": self.duration,
            "game_mode": self.game_mode,
            "map_name": self.map_name,
            "is_custom_match": self.is_custom_match,
            "season_state": self.season_state,
            "shard_id": self.shard_id,
            "telemetry_url": self.telemetry_url,
            "rosters": self.rosters,
            "participants": self.participants
        }

    @classmethod
    def from_json(cls, json_data: Dict) -> 'MatchData':
        """Десериализация из JSON"""
        return cls(json_data)

    @property
    def raw_data(self) -> dict:
        """Оригинальные данные API"""
        return self._raw_data