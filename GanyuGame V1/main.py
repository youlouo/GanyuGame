import sys
import time
import random
import json
import urllib.request
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QProgressBar, QLabel,
    QGraphicsOpacityEffect, QTextBrowser, QLineEdit, QFrame
)
from PyQt6.QtCore import (
    QTimer, Qt, QPoint, QPropertyAnimation, QEasingCurve,
    QUrl, QObject, pyqtSignal
)
from PyQt6.QtGui import (
    QMovie, QIcon, QFont
)
from PyQt6.QtMultimedia import QSoundEffect

from model import GanyuModel

BASE_DIR = Path(__file__).resolve().parent


# =====================================================================
# 1. ВИДЖЕТ АВАТАРА С ПОДДЕРЖКОЙ ГИФОК И КЛИКЕРА
# =====================================================================
class AvatarLabel(QLabel):
    """
    Наследник QLabel для отображения GIF-анимаций Гань Юй.
    """
    clicked = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("avatarLabel")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.clicked.emit(event)
        super().mousePressEvent(event)


# =====================================================================
# 2. КОНТРОЛЛЕР АНИМАЦИЙ, СЕРДЕЧКИ И МЕНЕДЖЕР ЗВУКОВ
# =====================================================================
class AnimationController:
    """Управляет сменой GIF-анимаций Гань Юй"""

    def __init__(self, avatar_label: QLabel):
        self.avatar_label = avatar_label
        self.default_gif = str(BASE_DIR / "idle.gif")
        self.current_movie: QMovie | None = None

        self.reset_timer = QTimer()
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.play_idle)

        self.play_idle()

    def play_idle(self):
        self._set_movie(self.default_gif)

    def play_action(self, gif_path: str, duration_ms: int = 3000):
        full_path = str(BASE_DIR / gif_path) if not Path(gif_path).is_absolute() else gif_path
        self._set_movie(full_path)
        self.reset_timer.start(duration_ms)

    def _set_movie(self, path: str):
        if Path(path).exists():
            if self.current_movie is not None:
                self.current_movie.stop()
                self.current_movie.deleteLater()

            movie = QMovie(path)
            self.current_movie = movie
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
        self.folder = BASE_DIR / folder
        self.cache: dict[str, QSoundEffect] = {}
        self.enabled = True
        self.volume = 0.7

    def _load(self, name: str) -> QSoundEffect | None:
        if name in self.cache:
            return self.cache[name]

        path = self.folder / name
        if not path.exists():
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
        if not self.enabled:
            return
        existing = [n for n in names if (self.folder / n).exists()]
        if existing:
            self.play(random.choice(existing))


# =====================================================================
# 3. БЕЗОПАСНЫЙ ПОТОК ЗАПРОСОВ К OLLAMA (Через urllib + threading)
# =====================================================================
class LLMWorker(QObject):
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, user_text: str, chat_history: list, stats_summary: str):
        super().__init__()
        self.user_text = user_text
        self.chat_history = chat_history
        self.stats_summary = stats_summary

    def start(self):
        # Запускаем в стандартном защищенном потоке Python (без падений QThread)
        threading.Thread(target=self._run_request, daemon=True).start()

    def load_lore(self) -> str:
        lore_path = BASE_DIR / "ganyu_lore.txt"
        if lore_path.exists():
            try:
                with open(lore_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"Не удалось прочитать файл лора: {e}")
        return "Ты - Гань Юй."

    def _run_request(self):
        try:
            lore_content = self.load_lore()

            system_prompt = (
                f"{lore_content}\n\n"
                f"Текущие показатели: {self.stats_summary}. "
                "Отвечай коротко (1-2 предложения), живо, без markdown-разметки. "
                "Если хочешь есть — упомяни слово «кушать», если спать — «спать», если радоваться — «танцевать»."
            )

            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self.chat_history[-10:])
            messages.append({"role": "user", "content": self.user_text})

            payload = {
                "model": "qwen2.5:7b",
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7, "num_ctx": 2048}
            }

            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/chat",
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                reply = res_json.get("message", {}).get("content", "").strip()
                self.response_ready.emit(reply)

        except Exception as e:
            self.error_occurred.emit(f"Ошибка Ollama: {e}")



class GanyuApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = GanyuModel()
        self.sound = SoundManager("sounds")

        self.last_click_time = 0.0
        self.click_cooldown = 0.15

        self.chat_history: list[dict] = []
        self.llm_worker: LLMWorker | None = None

        self.init_ui()
        self.load_stylesheet()

        self.anim_controller = AnimationController(self.avatar_label)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(1000)

    def load_stylesheet(self):
        qss_path = BASE_DIR / "style.qss"
        if qss_path.exists():
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def init_ui(self):
        self.setWindowTitle("Ганьюйность")
        self.setFixedSize(780, 700)
        icon_path = BASE_DIR / "app_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(16)

        pet_container = QWidget()
        pet_container.setFixedWidth(368)
        main_layout = QVBoxLayout(pet_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
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

        self.avatar_label = AvatarLabel(self)
        self.avatar_label.clicked.connect(self.on_avatar_click)
        main_layout.addWidget(self.avatar_label, stretch=1)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        btn_feed = QPushButton("Покормить")
        btn_feed.clicked.connect(lambda: self.on_feed(play_sfx=True))

        btn_sleep = QPushButton("Отдохнуть")
        btn_sleep.clicked.connect(lambda: self.on_sleep(play_sfx=True))

        btn_play = QPushButton("Поиграть")
        btn_play.clicked.connect(lambda: self.on_play(play_sfx=True))

        buttons_layout.addWidget(btn_feed)
        buttons_layout.addWidget(btn_sleep)
        buttons_layout.addWidget(btn_play)

        main_layout.addLayout(buttons_layout)

        # Правая колонка (чат с нейросетью)
        chat_frame = QFrame()
        chat_frame.setObjectName("chatFrame")
        chat_layout = QVBoxLayout(chat_frame)
        chat_layout.setContentsMargins(12, 12, 12, 12)
        chat_layout.setSpacing(8)

        chat_header = QLabel("Чат с Гань Юй")
        chat_header.setObjectName("chatHeaderLabel")
        chat_layout.addWidget(chat_header)

        self.chat_browser = QTextBrowser()
        self.chat_browser.setObjectName("chatBrowser")
        chat_layout.addWidget(self.chat_browser, stretch=1)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chatInput")
        self.chat_input.setPlaceholderText("Напишите что-нибудь Гань Юй...")
        self.chat_input.returnPressed.connect(self.on_send_message)

        self.btn_send = QPushButton("Отправить")
        self.btn_send.setObjectName("sendButton")
        self.btn_send.clicked.connect(self.on_send_message)

        input_layout.addWidget(self.chat_input, stretch=1)
        input_layout.addWidget(self.btn_send)

        chat_layout.addLayout(input_layout)

        self.status_label = QLabel("Готова к диалогу")
        self.status_label.setObjectName("statusLabel")
        chat_layout.addWidget(self.status_label)

        root_layout.addWidget(pet_container)
        root_layout.addWidget(chat_frame, stretch=1)

        self.append_chat_message(
            "Гань Юй",
            "Привет, Путешественник! Мы можем поболтать, покушать, поспать или потанцевать!"
        )

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

        if random.random() < 0.35:
            self.sound.play_random(["click_1.wav", "click_2.wav", "click_3.wav"])

        if self.model.level > old_level:
            self.sound.play("levelup.wav")

    def on_feed(self, play_sfx: bool = True):
        self.model.feed()
        self.update_ui()
        self.anim_controller.play_action("eat.gif", duration_ms=3000)
        if play_sfx:
            self.sound.play_random(["feed_1.wav", "feed_2.wav", "feed_3.wav"])

    def on_sleep(self, play_sfx: bool = True):
        self.model.sleep()
        self.update_ui()
        self.anim_controller.play_action("sleep.gif", duration_ms=4000)
        if play_sfx:
            self.sound.play_random(["sleep_1.wav", "sleep_2.wav"])

    def on_play(self, play_sfx: bool = True):
        self.model.play()
        self.update_ui()
        self.anim_controller.play_action("play.gif", duration_ms=6000)
        if play_sfx:
            self.sound.play_random(["play_1.wav", "play_2.wav"])

    def append_chat_message(self, author: str, text: str):
        color = "#ffd76e" if author == "Вы" else "#80deea"
        self.chat_browser.append(
            f'<div style="margin-bottom: 6px;"><b style="color: {color};">{author}:</b> {text}</div>'
        )

    def on_send_message(self):
        user_text = self.chat_input.text().strip()
        if not user_text:
            return

        self.chat_input.clear()
        self.chat_input.setEnabled(False)
        self.btn_send.setEnabled(False)

        self.append_chat_message("Вы", user_text)
        self.status_label.setText("Гань Юй думает ...")

        stats_summary = (
            f"вкусность {int(self.model.hunger)}%, "
            f"энергия {int(self.model.energy)}%, "
            f"веселость {int(self.model.happiness)}%, "
            f"уровень {self.model.level}"
        )

        self.llm_worker = LLMWorker(
            user_text=user_text,
            chat_history=self.chat_history,
            stats_summary=stats_summary
        )
        self.llm_worker.response_ready.connect(
            lambda reply: self.on_llm_response(user_text, reply)
        )
        self.llm_worker.error_occurred.connect(self.on_llm_error)
        self.llm_worker.start()

    def on_llm_response(self, user_text: str, reply_text: str):
        self.chat_history.append({"role": "user", "content": user_text})
        self.chat_history.append({"role": "assistant", "content": reply_text})

        self.append_chat_message("Гань Юй", reply_text)
        self.trigger_animation_by_keywords(reply_text)

        self.chat_input.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.chat_input.setFocus()
        self.status_label.setText("Готова к диалогу")

    def trigger_animation_by_keywords(self, text: str):
        lower_text = text.lower()

        eat_words = ("куша", "покуша", "поест", "поем", "перекус", "вкусн", "голодн")
        sleep_words = ("спать", "поспат", "отдохн", "вздремн", "сонн", "устал")
        dance_words = ("танц", "потанц", "поигра", "играт", "весел", "плясат")

        if any(w in lower_text for w in eat_words):
            self.on_feed(play_sfx=True)
        elif any(w in lower_text for w in sleep_words):
            self.on_sleep(play_sfx=True)
        elif any(w in lower_text for w in dance_words):
            self.on_play(play_sfx=True)

    def on_llm_error(self, error_text: str):
        self.append_chat_message("Система", f'<span style="color:#ff5252;">{error_text}</span>')
        self.status_label.setText("Ошибка подключения к Ollama")
        self.chat_input.setEnabled(True)
        self.btn_send.setEnabled(True)

    def closeEvent(self, event):
        self.model.save_game()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GanyuApp()
    window.show()
    sys.exit(app.exec())