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
        
        # ВАЖНО: теперь данные лежат внутри ключа 'data'
        self._raw_data = api_data
        self._data = api_data.get("data", {})  # <-- сюда переносим
        self._included = api_data.get("included", [])  # included лежит на верхнем уровне
        self._parse_data()

    def _parse_data(self):
        """Основной метод парсинга данных"""
        data = self._data  # теперь используем это
        
        # Основные поля матча
        self.id = data.get("id", "")
        self.type = data.get("type", "match")
        
        # Атрибуты матча
        attributes = data.get("attributes", {})
        iso_created_at = attributes.get("createdAt", "")
        self.created_at = self._format_created_at(iso_created_at)
        self.duration = int(attributes.get("duration", 0))
        self.game_mode = attributes.get("gameMode", "")
        self.map_name = attributes.get("mapName", "")
        self.is_custom_match = bool(attributes.get("isCustomMatch", False))
        self.season_state = attributes.get("seasonState", "")
        self.shard_id = attributes.get("shardId", "")
        self.title_id = attributes.get("titleId", "")
        
        # Инициализация коллекций
        self.rosters = []
        self.participants = []
        self.assets = []
        self.telemetry_url = None
        
        # Обработка связей
        relationships = data.get("relationships", {})
        self._process_relationships(relationships)
        
        # Обработка включенных данных
        self._process_included(self._included)
        
        # Связывание данных
        self._link_team_ranks()

    def _format_created_at(self, iso_str):
        """Форматирование даты"""
        if not iso_str:
            return ""

        try:
            # Парсим ISO строку и переводим в МСК
            dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            dt_moscow = dt.astimezone(ZoneInfo("Europe/Moscow"))
            return dt_moscow.strftime("%d.%m.%Y %H:%M:%S")
        except Exception:
            return iso_str 

    def _process_relationships(self, relationships: dict):
        """Обработка связей матча согласно API"""
        # Обработка ассетов (телеметрия)
        assets = relationships.get("assets", {}).get("data", [])
        if assets and isinstance(assets, list):
            self.assets = assets
            self.telemetry_url = assets[0].get("attributes", {}).get("URL", None) if assets else None

    def _process_included(self, included: list):
        """Обработка включенных данных согласно API спецификации"""
        for item in included:
            if not isinstance(item, dict):
                continue
                
            item_type = item.get("type")
            attributes = item.get("attributes", {})
            relationships = item.get("relationships", {})
            
            if item_type == "roster":
                self._process_roster(item, attributes, relationships)
            elif item_type == "participant":
                self._process_participant(item, attributes, relationships)

    def _process_roster(self, item: dict, attributes: dict, relationships: dict):
        """Обработка данных команды/роста"""
        roster_stats = attributes.get("stats", {})
        
        roster = {
            "id": item.get("id"),
            "type": item.get("type"),
            "won": roster_stats.get("won", False),
            "rank": roster_stats.get("rank", 0),
            "team_id": roster_stats.get("teamId"),
            "participants": []
        }
        self.rosters.append(roster)

    def _process_participant(self, item: dict, attributes: dict, relationships: dict):
        """Обработка данных участника"""
        participant_stats = attributes.get("stats", {})
        
        participant = {
            "id": item.get("id"),
            "type": item.get("type"),
            "player_id": participant_stats.get("playerId"),
            "name": participant_stats.get("name"),
            "roster_id": relationships.get("roster", {}).get("data", {}).get("id"),
            "stats": {
                "kills": participant_stats.get("kills", 0),
                "assists": participant_stats.get("assists", 0),
                "damage_dealt": participant_stats.get("damageDealt", 0.0),
                "headshot_kills": participant_stats.get("headshotKills", 0),
                "longest_kill": participant_stats.get("longestKill", 0.0),
                "revives": participant_stats.get("revives", 0),
                "ride_distance": participant_stats.get("rideDistance", 0.0),
                "walk_distance": participant_stats.get("walkDistance", 0.0),
                "time_survived": participant_stats.get("timeSurvived", 0),
                "win_place": participant_stats.get("winPlace", 0),
                "death_type": participant_stats.get("deathType"),
                "vehicle_destroys": participant_stats.get("vehicleDestroys", 0),
                "dbnos": participant_stats.get("DBNOs", 0)
            }
        }
        self.participants.append(participant)

    def _link_team_ranks(self):
        """Связываем ранги команд с игроками"""
        roster_ranks = {roster["id"]: roster.get("rank", 0) for roster in self.rosters}
        
        for participant in self.participants:
            if "stats" in participant:
                participant["stats"]["team_rank"] = roster_ranks.get(participant["roster_id"], 0)

    def get_detailed_player_stats(self, player_name: str) -> Optional[PlayerMatchStats]:
        """Получение детальной статистики игрока"""
        for participant in self.participants:
            if participant.get("name") == player_name:
                stats = participant.get("stats", {})
                try:
                    return PlayerMatchStats(
                        kills=stats.get("kills", 0),
                        assists=stats.get("assists", 0),
                        damage_dealt=stats.get("damage_dealt", 0.0),
                        headshot_kills=stats.get("headshot_kills", 0),
                        longest_kill=stats.get("longest_kill", 0.0),
                        revives=stats.get("revives", 0),
                        ride_distance=stats.get("ride_distance", 0.0),
                        walk_distance=stats.get("walk_distance", 0.0),
                        time_survived=stats.get("time_survived", 0),
                        win_place=stats.get("win_place", 0),
                        weapons_acquired=stats.get("weapons_acquired", 0),
                        death_type=stats.get("death_type"),
                        vehicle_destroys=stats.get("vehicle_destroys", 0),
                        dbnos=stats.get("dbnos", 0),
                        team_rank=stats.get("team_rank", 0)
                    )
                except Exception as e:
                    logger.error(f"Failed to create PlayerMatchStats: {str(e)}")
                    return None
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