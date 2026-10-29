import sys
import time
import random
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QProgressBar, QLabel,
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import (
    QTimer, Qt, QPoint, QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtGui import QMovie, QIcon, QFont
from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QSoundEffect

from model import GanyuModel


# Контроллер анимаций
class AnimationController:
    """Управляет сменой GIF-анимаций Ганьюй"""

    def __init__(self, avatar_label: QLabel):
        self.avatar_label = avatar_label
        self.default_gif = "idle.gif"

        self.reset_timer = QTimer()
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.play_idle)

        self.play_idle()

    def play_idle(self):
        self._set_movie(self.default_gif)

    def play_action(self, gif_path: str, duration_ms: int = 3000):
        self._set_movie(gif_path)
        self.reset_timer.start(duration_ms)

    def _set_movie(self, path: str):
        if Path(path).exists():
            movie = QMovie(path)
            self.avatar_label.setMovie(movie)
            movie.start()
        else:
            print(f"Предупреждение: Файл {path} не найден!")


class FloatingHeart(QLabel):

    def __init__(self, parent, pos: QPoint):
        super().__init__("❤", parent)
        self.setStyleSheet("color: #ff4081; background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        self.setFont(font)
        self.adjustSize()
        self.move(pos)
        self.show()

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(900)
        self.anim.setStartValue(pos)
        self.anim.setEndValue(QPoint(pos.x() - 5, pos.y() - 60))
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.fade = QPropertyAnimation(self.opacity, b"opacity")
        self.fade.setDuration(900)
        self.fade.setStartValue(1.0)
        self.fade.setEndValue(0.0)

        self.anim.finished.connect(self.deleteLater)
        self.anim.start()
        self.fade.start()

class SoundManager:
    """Загружает и проигрывает звуки из папки sounds/."""

    def __init__(self, folder: str = "sounds"):
        self.folder = Path(folder)
        self.cache: dict[str, QSoundEffect] = {}
        self.enabled = True
        self.volume = 0.7  # 0.0 .. 1.0

    def _load(self, name: str) -> QSoundEffect | None:
        if name in self.cache:
            return self.cache[name]

        path = self.folder / name
        if not path.exists():
            print(f"Звук не найден: {path}")
            return None

        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(str(path.resolve())))
        effect.setVolume(self.volume)
        self.cache[name] = effect
        return effect

    def play(self, name: str):
        if not self.enabled:
            return
        effect = self._load(name)
        if effect is not None:
            effect.play()

    def play_random(self, names: list[str]):
        self.play(random.choice(names))
class GanyuApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = GanyuModel()
        self.sound = SoundManager("sounds")

        self.last_click_time = 0.0
        self.click_cooldown = 0.15  # 150 мс

        self.init_ui()
        self.load_stylesheet()

        self.anim_controller = AnimationController(self.avatar_label)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(1000)

    def load_stylesheet(self):
        qss_path = Path("style.qss")
        if qss_path.exists():
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def init_ui(self):
        self.setWindowTitle("Ганьюйность")
        self.setFixedSize(400, 700)
        self.setWindowIcon(QIcon("app_icon.png"))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        level_layout = QVBoxLayout()
        level_layout.setSpacing(2)

        self.level_label = QLabel("Уровень 1")
        self.level_label.setObjectName("levelLabel")

        self.xp_bar = QProgressBar()
        self.xp_bar.setObjectName("xpBar")
        self.xp_bar.setRange(0, 50)
        self.xp_bar.setValue(0)
        self.xp_bar.setFormat("0 / 50")

        self.clicks_label = QLabel("Кликов: 0")
        self.clicks_label.setObjectName("clicksLabel")

        level_layout.addWidget(self.level_label)
        level_layout.addWidget(self.xp_bar)
        level_layout.addWidget(self.clicks_label)

        main_layout.addLayout(level_layout)

        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(4)

        self.bar_hunger = self._create_bar("Вкусность", "hungerBar", stats_layout)
        self.bar_energy = self._create_bar("Сонливость", "energyBar", stats_layout)
        self.bar_happiness = self._create_bar("Веселость", "happinessBar", stats_layout)

        main_layout.addLayout(stats_layout)

        self.avatar_label = QLabel(self)
        self.avatar_label.setObjectName("avatarLabel")
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setCursor(Qt.CursorShape.PointingHandCursor)

        self.avatar_label.mousePressEvent = self.on_avatar_click

        main_layout.addWidget(self.avatar_label, stretch=1)


        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        btn_feed = QPushButton("Покормить")
        btn_feed.clicked.connect(self.on_feed)

        btn_sleep = QPushButton("Отдохнуть")
        btn_sleep.clicked.connect(self.on_sleep)

        btn_play = QPushButton("Поиграть")
        btn_play.clicked.connect(self.on_play)

        buttons_layout.addWidget(btn_feed)
        buttons_layout.addWidget(btn_sleep)
        buttons_layout.addWidget(btn_play)

        main_layout.addLayout(buttons_layout)

        self.update_ui()

    def _create_bar(self, title: str, object_name: str, parent_layout: QVBoxLayout):
        label = QLabel(title)
        bar = QProgressBar()
        bar.setObjectName(object_name)
        bar.setRange(0, 100)

        parent_layout.addWidget(label)
        parent_layout.addWidget(bar)
        return bar

    def on_tick(self):
        self.model.update_stats()
        self.update_ui()

    def update_ui(self):

        self.bar_hunger.setValue(int(self.model.hunger))
        self.bar_energy.setValue(int(self.model.energy))
        self.bar_happiness.setValue(int(self.model.happiness))

        needed = self.model.xp_needed()
        self.xp_bar.setRange(0, needed)
        self.xp_bar.setValue(self.model.xp)
        self.xp_bar.setFormat(f"{self.model.xp} / {needed}")

        self.level_label.setText(f"Уровень {self.model.level}")
        self.clicks_label.setText(f"Кликов: {self.model.total_clicks}")

    def on_avatar_click(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        now = time.time()
        if now - self.last_click_time < self.click_cooldown:
            return
        self.last_click_time = now

        old_level = self.model.level
        self.model.add_xp(1)
        self.update_ui()

        pos = event.position().toPoint()
        heart_pos = QPoint(pos.x() - 10, pos.y() - 25)
        heart = FloatingHeart(self.avatar_label, heart_pos)
        heart.raise_()

        # Звук клика
        if random.random() < 0.35:  # 35% шанс
            self.sound.play_random(["click_1.wav", "click_2.wav", "click_3.wav"])

        # Звук левел-апа
        if self.model.level > old_level:
            self.sound.play("levelup.wav")

    def on_feed(self):
        self.model.feed()
        self.update_ui()
        self.anim_controller.play_action("eat.gif", duration_ms=3000)
        self.sound.play_random(["feed_1.wav", "feed_2.wav", "feed_3.wav"])

    def on_sleep(self):
        self.model.sleep()
        self.update_ui()
        self.anim_controller.play_action("sleep.gif", duration_ms=4000)
        self.sound.play_random(["sleep_1.wav", "sleep_2.wav"])

    def on_play(self):
        self.model.play()
        self.update_ui()
        self.anim_controller.play_action("play.gif", duration_ms=6000)
        self.sound.play_random(["play_1.wav", "play_2.wav"])

    def closeEvent(self, event):
        self.model.save_game()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GanyuApp()
    window.show()
    sys.exit(app.exec())
