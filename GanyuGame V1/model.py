import json
import time
from pathlib import Path

# Привязываем путь к папке проекта, чтобы save.json всегда читался корректно
BASE_DIR = Path(__file__).resolve().parent
SAVE_FILE = BASE_DIR / "save.json"


def xp_for_level(level: int) -> int:
    return 50 + (level - 1) * 25  # 1 ур -> 50, 2 ур -> 75, 3 ур -> 100


class GanyuModel:
    def __init__(self):
        self.hunger = 80.0
        self.energy = 100.0
        self.happiness = 90.0

        # Прогрессия
        self.level = 1
        self.xp = 0             # опыт внутри текущего уровня
        self.total_clicks = 0   # всего кликов

        self.last_update_time = time.time()
        self.load_game()

    def add_xp(self, amount: int = 1):
        self.xp += amount
        self.total_clicks += amount

        while self.xp >= xp_for_level(self.level):
            self.xp -= xp_for_level(self.level)
            self.level += 1

    def xp_needed(self) -> int:
        return xp_for_level(self.level)

    # Показатели
    def update_stats(self):
        self.hunger = max(0.0, self.hunger - 0.25)
        if self.energy < 50:
            self.energy = max(0.0, self.energy - 0.1)
        else:
            self.energy = max(0.0, self.energy - 0.05)
        if self.happiness < 50:
            self.happiness = max(0.0, self.happiness - 0.25)
        else:
            self.happiness = max(0.0, self.happiness - 0.20)

    def feed(self):
        self.hunger = min(100.0, self.hunger + 25.0)
        self.happiness = min(100.0, self.happiness + 5.0)

    def sleep(self):
        self.energy = min(100.0, self.energy + 35.0)

    def play(self):
        self.happiness = min(100.0, self.happiness + 20.0)
        self.energy = max(0.0, self.energy - 5.0)

    def save_game(self):
        data = {
            "hunger": self.hunger,
            "energy": self.energy,
            "happiness": self.happiness,
            "level": self.level,
            "xp": self.xp,
            "total_clicks": self.total_clicks,
            "last_update_time": self.last_update_time,
        }
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def load_game(self):
        if SAVE_FILE.exists():
            try:
                with open(SAVE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.hunger = data.get("hunger", 80.0)
                    self.energy = data.get("energy", 100.0)
                    self.happiness = data.get("happiness", 90.0)
                    self.level = data.get("level", 1)
                    self.xp = data.get("xp", 0)
                    self.total_clicks = data.get("total_clicks", 0)
                    self.last_update_time = data.get("last_update_time", time.time())
            except Exception as e:
                print(f"Ошибка загрузки сохранения: {e}")