from typing import List, Optional

class Player:
    def __init__(self, data: dict):
        self.id: str = data.get("id")
        attributes = data.get("attributes", {})
        self.name: str = attributes.get("name")
        self.shard_id: str = attributes.get("shardId")
        self.created_at: str = attributes.get("createdAt")
        self.updated_at: str = attributes.get("updatedAt")
        self.title_id: str = attributes.get("titleId")
        self.clan_id: Optional[str] = attributes.get("clanId")
        self.match_ids: List[str] = [
            match.get("id")
            for match in data.get("relationships", {}).get("matches", {}).get("data", [])
        ]

class ParsedPlayerStats:
    def __init__(self, data: dict):
        self.original_data = data  # если тебе потом нужен исходный JSON
        attributes = data.get("data", {}).get("attributes", {})
        game_mode_stats = attributes.get("gameModeStats", {})

        self.stats = {}

        for mode, stats in game_mode_stats.items():
            if not mode.endswith("fpp"):
                continue  # Только FPP режимы

            self.stats[mode] = {
                "wins": stats.get("wins"),
                "losses": stats.get("losses"),
                "kills": stats.get("kills"),
                "assists": stats.get("assists"),
                "damage_dealt": stats.get("damageDealt"),
                "longest_kill": stats.get("longestKill"),
                "headshot_kills": stats.get("headshotKills"),
                "rounds_played": stats.get("roundsPlayed"),
                "kd": stats.get("kills") / stats.get("losses") if stats.get("losses") else None
            }

    def to_dict(self):
        return self.stats  # именно stats, не оригинальный JSON

    @classmethod
    def from_json(cls, json_data):
        """
        Принимает уже обработанные данные (как из to_dict())
        и создает объект с такой же структурой
        """
        obj = cls.__new__(cls)
        obj.original_data = None  # Исходные данные не сохраняем
        obj.stats = json_data
        return obj
