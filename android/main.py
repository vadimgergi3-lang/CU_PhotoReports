# -*- coding: utf-8 -*-
"""
CONTROL UNION — полноценное offline Android-приложение для фото-отчётов.

Не использует Telegram. Все шаблоны, логотип, шрифты и оформление
документа — точно те же, что в боте (config.py + docgen.py).

Экраны:
  Start → Template → Meta → Containers → Collect → Preview → Result
  + Продолжение из существующего .docx (continue_report.parse_report)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
import uuid
from datetime import datetime

# -------------------------------------------------------------------------
# Пути хранилища (приватный каталог приложения на Android)
# -------------------------------------------------------------------------
def _app_dir() -> str:
    try:
        from android.storage import app_storage_path  # type: ignore
        return app_storage_path()
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".fotoreportcu")


APP_DIR = _app_dir()
os.makedirs(APP_DIR, exist_ok=True)

WORK_DIR = os.path.join(APP_DIR, "work")
OUT_DIR = os.path.join(APP_DIR, "out")
STATE_FILE = os.path.join(APP_DIR, "last_state.json")
os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

# Каталог с кодом (на Android рядом с main.py)
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from docgen import build_slots, generate_report
from continue_report import parse_report, ContinueError

# Логотип — из assets рядом с кодом
_logo = os.path.join(ROOT, "assets", "logo.png")
if os.path.isfile(_logo):
    config.LOGO_PATH = _logo
    os.environ["LOGO_PATH"] = _logo


# -------------------------------------------------------------------------
# Вспомогательные функции состояния
# -------------------------------------------------------------------------
def _new_session_dir() -> str:
    path = os.path.join(WORK_DIR, datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    os.makedirs(path, exist_ok=True)
    return path


def save_state(data: dict) -> None:
    """Сохраняет текущее состояние (без больших бинарных данных)."""
    try:
        slim = {
            "template_key": data.get("template_key"),
            "meta": data.get("meta"),
            "containers": data.get("containers"),
            "index": data.get("index", 0),
            "session_dir": data.get("session_dir"),
            "photos": data.get("photos", {}),
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(slim, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_state() -> dict | None:
    try:
        if not os.path.isfile(STATE_FILE):
            return None
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            slim = json.load(f)
        key = slim.get("template_key")
        if key not in config.TEMPLATES:
            return None
        tpl = config.TEMPLATES[key]
        containers = slim.get("containers") or []
        slots = build_slots(tpl, containers)
        photos = {k: v for k, v in (slim.get("photos") or {}).items() if os.path.isfile(v)}
        return {
            "template_key": key,
            "meta": slim.get("meta") or dict(tpl["meta"]),
            "containers": containers,
            "slots": slots,
            "photos": photos,
            "index": slim.get("index", 0),
            "session_dir": slim.get("session_dir") or _new_session_dir(),
        }
    except Exception:
        return None


def clear_state() -> None:
    try:
        if os.path.isfile(STATE_FILE):
            os.remove(STATE_FILE)
    except Exception:
        pass


def filled_count(data: dict) -> int:
    return sum(1 for s in data.get("slots", []) if os.path.isfile(data.get("photos", {}).get(s["id"], "")))


def progress_text(data: dict) -> str:
    total = len(data.get("slots", []))
    filled = filled_count(data)
    return f"Заполнено {filled} из {total}"


# -------------------------------------------------------------------------
# Выбор файла / камера (Android + desktop fallback)
# -------------------------------------------------------------------------
def pick_image(callback, multiple: bool = False):
    """Открывает галерею. callback(list_of_paths)."""
    try:
        from plyer import filechooser  # type: ignore
        filechooser.open_file(
            on_selection=callback,
            filters=["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"],
            multiple=multiple,
            title="Выберите фото",
        )
        return
    except Exception:
        pass

    # Desktop / fallback
    try:
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button

        content = BoxLayout(orientation="vertical")
        fc = FileChooserListView(filters=["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"],
                                 path=os.path.expanduser("~"))
        content.add_widget(fc)
        btns = BoxLayout(size_hint_y=None, height=48, spacing=8)
        ok = Button(text="Выбрать")
        cancel = Button(text="Отмена")
        btns.add_widget(ok)
        btns.add_widget(cancel)
        content.add_widget(btns)
        popup = Popup(title="Выберите фото", content=content, size_hint=(0.95, 0.9))

        def _ok(*_):
            sel = fc.selection
            popup.dismiss()
            if sel:
                callback(sel)

        def _cancel(*_):
            popup.dismiss()

        ok.bind(on_release=_ok)
        cancel.bind(on_release=_cancel)
        popup.open()
    except Exception:
        callback([])


def pick_docx(callback):
    """Выбор .docx для продолжения."""
    try:
        from plyer import filechooser  # type: ignore
        filechooser.open_file(
            on_selection=callback,
            filters=["*.docx"],
            title="Выберите отчёт .docx",
        )
        return
    except Exception:
        pass

    try:
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button

        content = BoxLayout(orientation="vertical")
        fc = FileChooserListView(filters=["*.docx"], path=os.path.expanduser("~"))
        content.add_widget(fc)
        btns = BoxLayout(size_hint_y=None, height=48, spacing=8)
        ok = Button(text="Выбрать")
        cancel = Button(text="Отмена")
        btns.add_widget(ok)
        btns.add_widget(cancel)
        content.add_widget(btns)
        popup = Popup(title="Выберите .docx", content=content, size_hint=(0.95, 0.9))

        def _ok(*_):
            sel = fc.selection
            popup.dismiss()
            if sel:
                callback(sel)

        def _cancel(*_):
            popup.dismiss()

        ok.bind(on_release=_ok)
        cancel.bind(on_release=_cancel)
        popup.open()
    except Exception:
        callback([])


def take_photo(callback):
    """Сделать фото (plyer.camera или Intent). callback(path_or_None)."""
    try:
        from plyer import camera  # type: ignore
        dest = os.path.join(WORK_DIR, f"cam_{uuid.uuid4().hex}.jpg")
        camera.take_picture(filename=dest, on_complete=lambda p: callback(p if p and os.path.isfile(p) else None))
        return
    except Exception:
        pass
    # fallback — просто открыть галерею
    pick_image(lambda paths: callback(paths[0] if paths else None))


def share_or_open_file(path: str):
    """Попытаться открыть/поделиться файлом на Android."""
    try:
        from jnius import autoclass  # type: ignore
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        File = autoclass("java.io.File")
        Uri = autoclass("android.net.Uri")
        activity = PythonActivity.mActivity
        f = File(path)
        try:
            FileProvider = autoclass("androidx.core.content.FileProvider")
            uri = FileProvider.getUriForFile(activity, activity.getPackageName() + ".fileprovider", f)
        except Exception:
            uri = Uri.fromFile(f)
        intent = Intent(Intent.ACTION_SEND)
        intent.setType("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        intent.putExtra(Intent.EXTRA_STREAM, uri)
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        chooser = Intent.createChooser(intent, "Отправить отчёт")
        activity.startActivity(chooser)
        return True
    except Exception:
        return False


# -------------------------------------------------------------------------
# Kivy UI
# -------------------------------------------------------------------------
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle


BG = (0.96, 0.96, 0.97, 1)
PRIMARY = (0.12, 0.35, 0.55, 1)
ACCENT = (0.15, 0.55, 0.35, 1)
TEXT = (0.15, 0.15, 0.18, 1)


def styled_btn(text, bg=PRIMARY, height=dp(48), **kw):
    return Button(
        text=text,
        size_hint_y=None,
        height=height,
        background_normal="",
        background_color=bg,
        color=(1, 1, 1, 1),
        bold=True,
        **kw,
    )


def title_label(text, size=18):
    return Label(
        text=f"[b]{text}[/b]",
        markup=True,
        size_hint_y=None,
        height=dp(36),
        color=TEXT,
        font_size=size,
        halign="left",
        valign="middle",
    )


def info_label(text):
    lbl = Label(
        text=text,
        size_hint_y=None,
        color=TEXT,
        font_size=14,
        halign="left",
        valign="top",
        text_size=(None, None),
    )
    lbl.bind(width=lambda *_: setattr(lbl, "text_size", (lbl.width, None)))
    lbl.bind(texture_size=lambda *_: setattr(lbl, "height", max(dp(24), lbl.texture_size[1])))
    return lbl


class BaseScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

    def _upd_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    @property
    def app(self):
        return App.get_running_app()


class StartScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(name="start", **kw)
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))

        logo_path = os.path.join(ROOT, "assets", "logo.png")
        if os.path.isfile(logo_path):
            logo = Image(source=logo_path, size_hint_y=None, height=dp(80),
                         allow_stretch=True, keep_ratio=True)
            root.add_widget(logo)

        root.add_widget(title_label("CONTROL UNION", 22))
        root.add_widget(info_label("Фото-отчёты (offline)\nШаблоны и оформление — как в Telegram-боте."))
        root.add_widget(Label(size_hint_y=None, height=dp(12)))

        btn_new = styled_btn("Новый отчёт", ACCENT)
        btn_new.bind(on_release=self._new)
        root.add_widget(btn_new)

        btn_cont = styled_btn("Продолжить из .docx", PRIMARY)
        btn_cont.bind(on_release=self._continue)
        root.add_widget(btn_cont)

        btn_resume = styled_btn("Восстановить последний", (0.4, 0.4, 0.45, 1))
        btn_resume.bind(on_release=self._resume)
        root.add_widget(btn_resume)

        self.status = info_label("")
        root.add_widget(self.status)
        root.add_widget(Label())
        root.add_widget(info_label("Android 13+ · только русский интерфейс"))
        self.add_widget(root)

    def on_enter(self, *_):
        st = load_state()
        if st and filled_count(st) > 0:
            self.status.text = f"Есть незавершённый отчёт ({progress_text(st)})."
        else:
            self.status.text = ""

    def _new(self, *_):
        self.app.data = {
            "template_key": None, "meta": {}, "containers": [],
            "slots": [], "photos": {}, "index": 0,
            "session_dir": _new_session_dir(),
        }
        clear_state()
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "template"

    def _continue(self, *_):
        def on_sel(paths):
            if not paths:
                return
            path = paths[0]
            try:
                session = _new_session_dir()
                parsed = parse_report(path, session)
                self.app.data = {
                    "template_key": parsed["template_key"],
                    "meta": parsed["meta"],
                    "containers": parsed["containers"],
                    "slots": parsed["slots"],
                    "photos": parsed["photos"],
                    "index": parsed["index"],
                    "session_dir": session,
                }
                save_state(self.app.data)
                self.manager.transition = SlideTransition(direction="left")
                self.manager.current = "collect"
            except ContinueError as e:
                self._alert(str(e))
            except Exception as e:
                self._alert(f"Ошибка: {e}")

        pick_docx(on_sel)

    def _resume(self, *_):
        st = load_state()
        if not st:
            self._alert("Нет сохранённого состояния.")
            return
        self.app.data = st
        self.manager.transition = SlideTransition(direction="left")
        if not st.get("template_key"):
            self.manager.current = "template"
        elif not st.get("containers"):
            self.manager.current = "meta"
        else:
            self.manager.current = "collect"

    def _alert(self, text):
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        content.add_widget(Label(text=text, text_size=(dp(280), None)))
        btn = styled_btn("OK", height=dp(40))
        content.add_widget(btn)
        popup = Popup(title="Сообщение", content=content, size_hint=(0.85, None), height=dp(180))
        btn.bind(on_release=popup.dismiss)
        popup.open()


class TemplateScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(name="template", **kw)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        root.add_widget(title_label("Выберите шаблон"))

        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=dp(8), size_hint_y=None, padding=dp(4))
        grid.bind(minimum_height=grid.setter("height"))

        for key, tpl in config.TEMPLATES.items():
            n_intro = sum(c for _, c in tpl.get("intro", []))
            n_per = len(tpl.get("per_container", []))
            title = tpl.get("title", key)
            desc = f"{title}\nВводный блок: {n_intro} фото · На контейнер: {n_per} фото"
            btn = Button(
                text=desc, size_hint_y=None, height=dp(64),
                background_normal="", background_color=PRIMARY,
                color=(1, 1, 1, 1), halign="left", valign="middle", text_size=(None, None),
            )
            btn.bind(size=lambda b, *_: setattr(b, "text_size", (b.width - dp(16), None)))
            btn.bind(on_release=lambda _, k=key: self._choose(k))
            grid.add_widget(btn)

        scroll.add_widget(grid)
        root.add_widget(scroll)

        back = styled_btn("← Назад", (0.45, 0.45, 0.5, 1))
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        root.add_widget(back)
        self.add_widget(root)

    def _choose(self, key):
        tpl = config.TEMPLATES[key]
        self.app.data["template_key"] = key
        self.app.data["meta"] = dict(tpl["meta"])
        self.app.data["containers"] = []
        self.app.data["slots"] = []
        self.app.data["photos"] = {}
        self.app.data["index"] = 0
        save_state(self.app.data)
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "meta"


META_FIELDS = [
    ("report_no", "№ отчёта (PHOTO REPORT No.)"),
    ("place", "PLACE OF INSPECTION"),
    ("goods", "DESCRIPTION OF GOODS"),
    ("scope", "SCOPE OF SERVICES"),
    ("date", "DATE OF INSPECTION"),
    ("footer", "Подпись в конце (дата + CONTROL UNION…)"),
]


class MetaScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(name="meta", **kw)
        self.inputs = {}
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(6))
        root.add_widget(title_label("Метаданные отчёта"))

        scroll = ScrollView()
        form = GridLayout(cols=1, spacing=dp(6), size_hint_y=None, padding=dp(4))
        form.bind(minimum_height=form.setter("height"))

        for key, label in META_FIELDS:
            form.add_widget(Label(
                text=label, size_hint_y=None, height=dp(22),
                color=TEXT, font_size=13, halign="left", text_size=(None, None),
            ))
            ti = TextInput(
                multiline=(key == "scope"), size_hint_y=None,
                height=dp(40) if key != "scope" else dp(70), font_size=14,
            )
            self.inputs[key] = ti
            form.add_widget(ti)

        scroll.add_widget(form)
        root.add_widget(scroll)

        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        back = styled_btn("← Назад", (0.45, 0.45, 0.5, 1))
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "template"))
        next_btn = styled_btn("Далее →", ACCENT)
        next_btn.bind(on_release=self._next)
        btns.add_widget(back)
        btns.add_widget(next_btn)
        root.add_widget(btns)
        self.add_widget(root)

    def on_enter(self, *_):
        meta = self.app.data.get("meta") or {}
        for key, ti in self.inputs.items():
            ti.text = str(meta.get(key, "") or "")

    def _next(self, *_):
        meta = {k: ti.text.strip() for k, ti in self.inputs.items()}
        self.app.data["meta"] = meta
        save_state(self.app.data)
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "containers"


class ContainersScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(name="containers", **kw)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        root.add_widget(title_label("Контейнеры"))
        root.add_widget(info_label(
            "Выберите режим:\n"
            "• Количество — контейнеры будут 1, 2, 3…\n"
            "• Серийные номера — введите через запятую или точку с запятой"
        ))

        self.mode = "count"
        mode_box = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.btn_count = styled_btn("Количество", ACCENT, height=dp(44))
        self.btn_serial = styled_btn("Серийные №", (0.45, 0.45, 0.5, 1), height=dp(44))
        self.btn_count.bind(on_release=lambda *_: self._set_mode("count"))
        self.btn_serial.bind(on_release=lambda *_: self._set_mode("serial"))
        mode_box.add_widget(self.btn_count)
        mode_box.add_widget(self.btn_serial)
        root.add_widget(mode_box)

        self.hint = info_label("Введите число контейнеров (например 3)")
        root.add_widget(self.hint)
        self.input = TextInput(multiline=False, size_hint_y=None, height=dp(44), font_size=16)
        root.add_widget(self.input)
        root.add_widget(Label())

        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        back = styled_btn("← Назад", (0.45, 0.45, 0.5, 1))
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "meta"))
        next_btn = styled_btn("Начать сбор фото →", ACCENT)
        next_btn.bind(on_release=self._next)
        btns.add_widget(back)
        btns.add_widget(next_btn)
        root.add_widget(btns)
        self.add_widget(root)

    def on_enter(self, *_):
        conts = self.app.data.get("containers") or []
        if conts and all(str(c).isdigit() for c in conts):
            self._set_mode("count")
            self.input.text = str(len(conts))
        elif conts:
            self._set_mode("serial")
            self.input.text = "; ".join(str(c) for c in conts)
        else:
            self._set_mode("count")
            self.input.text = ""

    def _set_mode(self, mode):
        self.mode = mode
        if mode == "count":
            self.btn_count.background_color = ACCENT
            self.btn_serial.background_color = (0.45, 0.45, 0.5, 1)
            self.hint.text = "Введите число контейнеров (например 3)"
        else:
            self.btn_count.background_color = (0.45, 0.45, 0.5, 1)
            self.btn_serial.background_color = ACCENT
            self.hint.text = "Введите номера через запятую или ; (например MSKU123; MRKU456)"

    def _next(self, *_):
        raw = self.input.text.strip()
        if not raw:
            self._alert("Введите значение")
            return
        if self.mode == "count":
            try:
                n = int(raw)
                if n < 1 or n > 50:
                    raise ValueError
                containers = [str(i) for i in range(1, n + 1)]
            except ValueError:
                self._alert("Введите целое число от 1 до 50")
                return
        else:
            parts = [x.strip() for x in raw.replace(",", ";").split(";")]
            containers = [p for p in parts if p]
            if not containers:
                self._alert("Не найдено ни одного номера")
                return

        tpl = config.TEMPLATES[self.app.data["template_key"]]
        slots = build_slots(tpl, containers)
        self.app.data["containers"] = containers
        self.app.data["slots"] = slots
        self.app.data["photos"] = {}
        self.app.data["index"] = 0
        save_state(self.app.data)
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "collect"

    def _alert(self, text):
        content = BoxLayout(orientation="vertical", padding=dp(12))
        content.add_widget(Label(text=text))
        btn = styled_btn("OK", height=dp(40))
        content.add_widget(btn)
        popup = Popup(title="Ошибка", content=content, size_hint=(0.8, None), height=dp(160))
        btn.bind(on_release=popup.dismiss)
        popup.open()


class CollectScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(name="collect", **kw)
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        self.header = title_label("Сбор фото")
        root.add_widget(self.header)
        self.progress = info_label("")
        root.add_widget(self.progress)
        self.slot_info = info_label("")
        root.add_widget(self.slot_info)

        self.preview = Image(source="", size_hint_y=None, height=dp(220),
                             allow_stretch=True, keep_ratio=True)
        root.add_widget(self.preview)

        act = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        self.btn_gallery = styled_btn("Галерея", PRIMARY, height=dp(48))
        self.btn_gallery.bind(on_release=self._gallery)
        self.btn_camera = styled_btn("Камера", PRIMARY, height=dp(48))
        self.btn_camera.bind(on_release=self._camera)
        act.add_widget(self.btn_gallery)
        act.add_widget(self.btn_camera)
        root.add_widget(act)

        nav = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.btn_prev = styled_btn("← Пред.", (0.45, 0.45, 0.5, 1), height=dp(44))
        self.btn_prev.bind(on_release=self._prev)
        self.btn_next = styled_btn("След. →", (0.45, 0.45, 0.5, 1), height=dp(44))
        self.btn_next.bind(on_release=self._next_slot)
        self.btn_skip = styled_btn("Пропуск", (0.55, 0.4, 0.2, 1), height=dp(44))
        self.btn_skip.bind(on_release=self._skip)
        nav.add_widget(self.btn_prev)
        nav.add_widget(self.btn_next)
        nav.add_widget(self.btn_skip)
        root.add_widget(nav)

        bottom = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        btn_list = styled_btn("Список слотов", (0.35, 0.35, 0.4, 1))
        btn_list.bind(on_release=self._show_list)
        btn_done = styled_btn("К итогу →", ACCENT)
        btn_done.bind(on_release=self._to_preview)
        bottom.add_widget(btn_list)
        bottom.add_widget(btn_done)
        root.add_widget(bottom)
        self.add_widget(root)

    def on_enter(self, *_):
        self._refresh()

    def _refresh(self):
        data = self.app.data
        slots = data.get("slots") or []
        if not slots:
            self.slot_info.text = "Нет слотов. Вернитесь и задайте контейнеры."
            return
        idx = max(0, min(data.get("index", 0), len(slots) - 1))
        data["index"] = idx
        slot = slots[idx]
        self.progress.text = progress_text(data)
        section = "Вводный блок" if slot["section"] == "intro" else f"Контейнер {slot['container']}"
        self.slot_info.text = (
            f"Слот {idx + 1} / {len(slots)}\n"
            f"{section}\n"
            f"[b]{slot['caption']}[/b]"
        )
        self.slot_info.markup = True

        path = data.get("photos", {}).get(slot["id"], "")
        if path and os.path.isfile(path):
            self.preview.source = path
            self.preview.reload()
        else:
            self.preview.source = ""

        self.btn_prev.disabled = idx <= 0
        self.btn_next.disabled = idx >= len(slots) - 1
        save_state(data)

    def _set_photo(self, path: str):
        if not path or not os.path.isfile(path):
            return
        data = self.app.data
        slots = data["slots"]
        idx = data["index"]
        slot = slots[idx]
        session = data.get("session_dir") or _new_session_dir()
        data["session_dir"] = session
        ext = os.path.splitext(path)[1].lower() or ".jpg"
        dest = os.path.join(session, f"{slot['id']}{ext}")
        try:
            shutil.copy2(path, dest)
        except Exception:
            dest = path
        data.setdefault("photos", {})[slot["id"]] = dest
        next_idx = idx + 1
        while next_idx < len(slots) and slots[next_idx]["id"] in data["photos"]:
            next_idx += 1
        if next_idx < len(slots):
            data["index"] = next_idx
        save_state(data)
        self._refresh()

    def _gallery(self, *_):
        pick_image(lambda paths: self._set_photo(paths[0]) if paths else None)

    def _camera(self, *_):
        take_photo(lambda p: self._set_photo(p) if p else None)

    def _prev(self, *_):
        data = self.app.data
        if data["index"] > 0:
            data["index"] -= 1
            self._refresh()

    def _next_slot(self, *_):
        data = self.app.data
        if data["index"] < len(data["slots"]) - 1:
            data["index"] += 1
            self._refresh()

    def _skip(self, *_):
        data = self.app.data
        if data["index"] < len(data["slots"]) - 1:
            data["index"] += 1
            self._refresh()

    def _to_preview(self, *_):
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "preview"

    def _show_list(self, *_):
        data = self.app.data
        slots = data.get("slots") or []
        photos = data.get("photos") or {}
        content = BoxLayout(orientation="vertical", padding=dp(8))
        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))

        for i, s in enumerate(slots):
            has = "✓" if os.path.isfile(photos.get(s["id"], "")) else "○"
            section = "Intro" if s["section"] == "intro" else f"C {s['container']}"
            btn = Button(
                text=f"{has} {i+1}. [{section}] {s['caption']}",
                size_hint_y=None, height=dp(40), background_normal="",
                background_color=(0.25, 0.45, 0.3, 1) if has == "✓" else (0.4, 0.4, 0.45, 1),
                color=(1, 1, 1, 1), font_size=13, halign="left", text_size=(None, None),
            )
            btn.bind(size=lambda b, *_: setattr(b, "text_size", (b.width - 8, None)))

            def go(_, index=i):
                data["index"] = index
                popup.dismiss()
                self._refresh()

            btn.bind(on_release=go)
            grid.add_widget(btn)

        scroll.add_widget(grid)
        content.add_widget(scroll)
        close = styled_btn("Закрыть", height=dp(40))
        content.add_widget(close)
        popup = Popup(title="Слоты", content=content, size_hint=(0.95, 0.85))
        close.bind(on_release=popup.dismiss)
        popup.open()


class PreviewScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(name="preview", **kw)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        root.add_widget(title_label("Итог и генерация"))
        self.summary = info_label("")
        root.add_widget(self.summary)
        self.status = info_label("")
        root.add_widget(self.status)
        root.add_widget(Label())

        btn_gen = styled_btn("Сформировать Word (.docx)", ACCENT, height=dp(52))
        btn_gen.bind(on_release=self._generate)
        root.add_widget(btn_gen)

        btn_back = styled_btn("← Вернуться к фото", (0.45, 0.45, 0.5, 1))
        btn_back.bind(on_release=lambda *_: setattr(self.manager, "current", "collect"))
        root.add_widget(btn_back)

        btn_meta = styled_btn("Изменить метаданные", PRIMARY)
        btn_meta.bind(on_release=lambda *_: setattr(self.manager, "current", "meta"))
        root.add_widget(btn_meta)

        btn_home = styled_btn("На главную", (0.5, 0.3, 0.3, 1))
        btn_home.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        root.add_widget(btn_home)
        self.add_widget(root)

    def on_enter(self, *_):
        data = self.app.data
        key = data.get("template_key", "")
        title = config.TEMPLATES.get(key, {}).get("title", key)
        meta = data.get("meta") or {}
        self.summary.text = (
            f"Шаблон: {title}\n"
            f"№ отчёта: {meta.get('report_no', '')}\n"
            f"Контейнеры: {', '.join(data.get('containers') or [])}\n"
            f"{progress_text(data)}"
        )

    def _generate(self, *_):
        self.status.text = "Генерация документа…"
        Clock.schedule_once(lambda dt: self._do_generate(), 0.1)

    def _do_generate(self):
        data = self.app.data
        try:
            key = data["template_key"]
            tpl = config.TEMPLATES[key]
            meta = data["meta"]
            containers = data["containers"]
            photos = {k: v for k, v in (data.get("photos") or {}).items() if os.path.isfile(v)}
            report_no = (meta.get("report_no") or "report").replace("/", "-").replace("\\", "-")
            out_name = f"Photo_Report_{report_no}.docx"
            out_path = os.path.join(OUT_DIR, out_name)
            generate_report(tpl, meta, containers, photos, out_path)
            data["last_docx"] = out_path
            save_state(data)
            self.app.last_docx = out_path
            self.manager.transition = SlideTransition(direction="left")
            self.manager.current = "result"
        except Exception as e:
            self.status.text = f"Ошибка генерации:\n{e}\n{traceback.format_exc()[:400]}"


class ResultScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(name="result", **kw)
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        root.add_widget(title_label("Готово!", 22))
        self.info = info_label("")
        root.add_widget(self.info)

        btn_share = styled_btn("Отправить / Поделиться", ACCENT, height=dp(52))
        btn_share.bind(on_release=self._share)
        root.add_widget(btn_share)

        btn_new = styled_btn("Новый отчёт", PRIMARY)
        btn_new.bind(on_release=self._new)
        root.add_widget(btn_new)

        btn_home = styled_btn("На главную", (0.45, 0.45, 0.5, 1))
        btn_home.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        root.add_widget(btn_home)
        root.add_widget(Label())
        self.add_widget(root)

    def on_enter(self, *_):
        path = getattr(self.app, "last_docx", None) or self.app.data.get("last_docx")
        if path and os.path.isfile(path):
            size_kb = os.path.getsize(path) // 1024
            self.info.text = (
                f"Документ сохранён:\n{path}\n\n"
                f"Размер: {size_kb} КБ\n\n"
                "Нажмите «Отправить / Поделиться», чтобы открыть или отправить файл."
            )
        else:
            self.info.text = "Файл не найден."

    def _share(self, *_):
        path = getattr(self.app, "last_docx", None) or self.app.data.get("last_docx")
        if not path or not os.path.isfile(path):
            return
        ok = share_or_open_file(path)
        if not ok:
            self.info.text += "\n\nНе удалось открыть системный диалог. Файл лежит в:\n" + path

    def _new(self, *_):
        clear_state()
        self.app.data = {
            "template_key": None, "meta": {}, "containers": [],
            "slots": [], "photos": {}, "index": 0,
            "session_dir": _new_session_dir(),
        }
        self.manager.current = "start"


class FotoReportApp(App):
    def build(self):
        self.title = "CONTROL UNION — Фото-отчёты"
        self.data = {
            "template_key": None, "meta": {}, "containers": [],
            "slots": [], "photos": {}, "index": 0,
            "session_dir": _new_session_dir(),
        }
        self.last_docx = None

        sm = ScreenManager(transition=SlideTransition())
        sm.add_widget(StartScreen())
        sm.add_widget(TemplateScreen())
        sm.add_widget(MetaScreen())
        sm.add_widget(ContainersScreen())
        sm.add_widget(CollectScreen())
        sm.add_widget(PreviewScreen())
        sm.add_widget(ResultScreen())
        return sm

    def on_pause(self):
        save_state(self.data)
        return True

    def on_resume(self):
        pass


if __name__ == "__main__":
    FotoReportApp().run()
