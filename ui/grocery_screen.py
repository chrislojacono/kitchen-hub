import math
import time

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.utils import escape_markup

from ui import api
from ui.ui_common import ACCENT_TEXT, CardButton, GradientScreen, debounced, eyebrow, fit_text

BG_TOP = (0.06, 0.22, 0.16, 1)
BG_BOTTOM = (0.02, 0.04, 0.03, 1)
ROWS_PER_PAGE = 6
REFRESH_SECONDS = 30
TOGGLE_COOLDOWN_SECONDS = 3


def _qty(item):
    if item["qty"] is None:
        return ""
    qty = f"{item['qty']:g}"
    return f"{qty} {item['unit']}" if item["unit"] else qty


class GroceryScreen(GradientScreen):
    def __init__(self, **kwargs):
        super().__init__(BG_TOP, BG_BOTTOM, padding=[96, 22, 96, 22], spacing=10, **kwargs)
        self.items = []
        self.page = 0
        self._refresh_event = None
        self._last_toggle = 0.0

        header = BoxLayout(size_hint=(1, 0.08))
        header.add_widget(eyebrow("Grocery list", size_hint=(0.6, 1)))
        self.status = fit_text(Label(font_size=16, color=ACCENT_TEXT, size_hint=(0.4, 1)), "right")
        header.add_widget(self.status)
        self.root_box.add_widget(header)

        self.rows = []
        for index in range(ROWS_PER_PAGE):
            row = CardButton(font_size=28, halign="left", size_hint=(1, 0.12))
            row.bind(on_release=debounced(lambda _, i=index: self._toggle(i)))
            self.rows.append(row)
            self.root_box.add_widget(row)

        pager = BoxLayout(size_hint=(1, 0.12), spacing=12)
        self.prev_button = CardButton(text="Prev", font_size=22, size_hint=(0.22, 1))
        self.prev_button.bind(on_release=debounced(lambda _: self._turn_page(-1)))
        self.page_label = Label(font_size=20, color=ACCENT_TEXT, size_hint=(0.2, 1))
        self.next_button = CardButton(text="Next", font_size=22, size_hint=(0.22, 1))
        self.next_button.bind(on_release=debounced(lambda _: self._turn_page(1)))
        self.clear_button = CardButton(text="Clear checked", font_size=22, size_hint=(0.36, 1))
        self.clear_button.bind(on_release=debounced(lambda _: self._clear_checked()))
        for widget in (self.prev_button, self.page_label, self.next_button, self.clear_button):
            pager.add_widget(widget)
        self.root_box.add_widget(pager)

        self._render()

    def on_enter(self, *_):
        self._load()
        self._refresh_event = Clock.schedule_interval(lambda _: self._load(), REFRESH_SECONDS)

    def on_leave(self, *_):
        if self._refresh_event:
            self._refresh_event.cancel()
            self._refresh_event = None

    def _load(self):
        api.call("GET", "/api/grocery?include_checked=true", self._loaded, lambda _: self._set_status("Offline"))

    def _loaded(self, items):
        if time.monotonic() - self._last_toggle < TOGGLE_COOLDOWN_SECONDS:
            return
        self.items = items
        self._render()

    def _toggle(self, row_index):
        index = self.page * ROWS_PER_PAGE + row_index
        if index >= len(self.items):
            return
        item = self.items[index]
        item["checked"] = 0 if item["checked"] else 1
        self._last_toggle = time.monotonic()
        self._render()

        def failed(_):
            item["checked"] = 0 if item["checked"] else 1
            self._render()
            self._set_status("Couldn't save, try again")

        checked = "true" if item["checked"] else "false"
        api.call("POST", f"/api/grocery/{item['id']}/check?checked={checked}", lambda _: None, failed)

    def _clear_checked(self):
        api.call("POST", "/api/grocery/clear-checked", lambda _: self._load(),
                 lambda _: self._set_status("Couldn't clear, try again"))

    def _turn_page(self, step):
        self.page += step
        self._render()

    def _set_status(self, text):
        self.status.text = text

    def _render(self):
        pages = max(1, math.ceil(len(self.items) / ROWS_PER_PAGE))
        self.page = max(0, min(self.page, pages - 1))
        shown = self.items[self.page * ROWS_PER_PAGE:(self.page + 1) * ROWS_PER_PAGE]

        for index, row in enumerate(self.rows):
            if index >= len(shown):
                row.text, row.opacity, row.disabled = "", 0, True
                continue
            item = shown[index]
            text = escape_markup(item["name"])
            if _qty(item):
                text += f"   [size=22][color=9eadc2]{escape_markup(_qty(item))}[/color][/size]"
            row.text = f"[s]{text}[/s]" if item["checked"] else text
            row.opacity, row.disabled = (0.4 if item["checked"] else 1), False

        remaining = sum(1 for item in self.items if not item["checked"])
        self._set_status(f"{remaining} to get" if remaining else "All done")
        self.page_label.text = f"{self.page + 1} / {pages}"
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= pages - 1
        self.prev_button.opacity = 0.3 if self.prev_button.disabled else 1
        self.next_button.opacity = 0.3 if self.next_button.disabled else 1
