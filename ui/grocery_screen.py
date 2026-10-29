import math
import time

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line
from kivy.properties import BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.utils import escape_markup

from ui import api
from ui.panels import PhonePanel, QuickAddPanel
from ui.ui_common import (ACCENT, ACCENT_TEXT, BODY_TEXT, ON_ACCENT, CardButton, GradientScreen, debounced,
                          fit_text)

BG_TOP = (0.06, 0.22, 0.16, 1)
BG_BOTTOM = (0.02, 0.04, 0.03, 1)
COLUMNS = 2
ROWS = 5
PER_PAGE = COLUMNS * ROWS
REFRESH_SECONDS = 30
TOGGLE_COOLDOWN_SECONDS = 3


def _qty(item):
    if item["qty"] is None:
        return ""
    qty = f"{item['qty']:g}"
    return f"{qty} {item['unit']}" if item["unit"] else qty


class CheckRow(CardButton):
    checked = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(halign="left", padding_x=64, font_size=24, shorten=True, shorten_from="right", **kwargs)
        with self.canvas.after:
            self._ring_color = Color(*ACCENT_TEXT)
            self._ring = Line(width=1.6)
            self._fill_color = Color(*ACCENT)
            self._fill = Ellipse()
            self._tick_color = Color(*ON_ACCENT)
            self._tick = Line(width=2.2, cap="round", joint="round")
        self.bind(pos=self._redraw, size=self._redraw, checked=self._redraw)

    def _redraw(self, *_):
        radius, cx, cy = 14, self.x + 34, self.center_y
        self._ring.circle = (cx, cy, radius)
        self._fill.pos, self._fill.size = (cx - radius, cy - radius), (2 * radius, 2 * radius)
        self._tick.points = [cx - 6, cy, cx - 1.5, cy - 5, cx + 7, cy + 5]
        shown = 1 if self.checked else 0
        self._fill_color.a = self._tick_color.a = shown
        self._ring_color.a = 1 - shown


class GroceryScreen(GradientScreen):
    def __init__(self, **kwargs):
        super().__init__(BG_TOP, BG_BOTTOM, padding=[96, 18, 96, 16], spacing=12, **kwargs)
        self.items = []
        self.page = 0
        self._refresh_event = None
        self._last_toggle = 0.0
        self.quick_add = QuickAddPanel(on_dismiss=lambda *_: self._load())
        self.phone_panel = PhonePanel()

        header = BoxLayout(size_hint=(1, 0.13), spacing=12)
        titles = BoxLayout(orientation="vertical")
        titles.add_widget(fit_text(Label(text="Grocery list", font_size=30, bold=True, color=BODY_TEXT)))
        self.status = fit_text(Label(font_size=17, color=ACCENT_TEXT))
        titles.add_widget(self.status)
        header.add_widget(titles)
        add_button = CardButton(text="+  Add", font_size=22, bold=True, bg=ACCENT, color=ON_ACCENT,
                                size_hint=(None, 1), width=150)
        add_button.bind(on_release=debounced(lambda _: self.quick_add.open()))
        phone_button = CardButton(text="Phone", font_size=22, size_hint=(None, 1), width=140)
        phone_button.bind(on_release=debounced(lambda _: self.phone_panel.open()))
        header.add_widget(add_button)
        header.add_widget(phone_button)
        self.root_box.add_widget(header)

        body = FloatLayout(size_hint=(1, 0.74))
        grid = GridLayout(cols=COLUMNS, rows=ROWS, spacing=10, pos_hint={"x": 0, "y": 0})
        self.rows = []
        for cell in range(PER_PAGE):
            row = CheckRow()
            row.bind(on_release=debounced(lambda _, c=cell: self._toggle(c)))
            self.rows.append(row)
            grid.add_widget(row)
        body.add_widget(grid)
        self.empty = Label(text="The list is empty\n[size=20][color=9eadc2]Tap  + Add, or add from your phone[/color][/size]",
                           markup=True, halign="center", font_size=30, color=BODY_TEXT,
                           pos_hint={"center_x": 0.5, "center_y": 0.5})
        body.add_widget(self.empty)
        self.root_box.add_widget(body)

        footer = BoxLayout(size_hint=(1, 0.13), spacing=12)
        self.prev_button = CardButton(text="Prev", font_size=20, size_hint=(None, 1), width=120)
        self.prev_button.bind(on_release=debounced(lambda _: self._turn_page(-1)))
        self.page_label = Label(font_size=18, color=ACCENT_TEXT, size_hint=(None, 1), width=80)
        self.next_button = CardButton(text="Next", font_size=20, size_hint=(None, 1), width=120)
        self.next_button.bind(on_release=debounced(lambda _: self._turn_page(1)))
        self.clear_button = CardButton(font_size=20, size_hint=(None, 1), width=220)
        self.clear_button.bind(on_release=debounced(lambda _: self._clear_checked()))
        for widget in (self.prev_button, self.page_label, self.next_button, Widget(), self.clear_button):
            footer.add_widget(widget)
        self.root_box.add_widget(footer)

        self._render()

    def on_enter(self, *_):
        self.on_leave()
        self._load()
        self._refresh_event = Clock.schedule_interval(lambda _: self._load(), REFRESH_SECONDS)

    def on_leave(self, *_):
        if self._refresh_event:
            self._refresh_event.cancel()
            self._refresh_event = None

    def _load(self):
        api.call("GET", "/api/grocery?include_checked=true", self._loaded,
                 lambda _: self._set_status("Can't reach the kitchen hub"))

    def _loaded(self, items):
        if time.monotonic() - self._last_toggle < TOGGLE_COOLDOWN_SECONDS:
            return
        # Alphabetical only, so a checked item dims in place instead of jumping under the next tap.
        self.items = sorted(items, key=lambda item: item["name"].lower())
        self._render()

    def _item_for_cell(self, cell):
        # Fill the first column top to bottom, then the second, like reading a list.
        index = self.page * PER_PAGE + (cell % COLUMNS) * ROWS + cell // COLUMNS
        return self.items[index] if index < len(self.items) else None

    def _toggle(self, cell):
        item = self._item_for_cell(cell)
        if item is None:
            return
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

    @staticmethod
    def _show(widget, visible):
        widget.opacity, widget.disabled = (1, False) if visible else (0, True)

    def _render(self):
        pages = max(1, math.ceil(len(self.items) / PER_PAGE))
        self.page = max(0, min(self.page, pages - 1))

        for cell, row in enumerate(self.rows):
            item = self._item_for_cell(cell)
            self._show(row, item is not None)
            if item is None:
                row.text, row.checked = "", False
                continue
            text = escape_markup(item["name"])
            if _qty(item):
                text += f"   [size=19][color=9eadc2]{escape_markup(_qty(item))}[/color][/size]"
            row.text = f"[s]{text}[/s]" if item["checked"] else text
            row.checked = bool(item["checked"])
            row.opacity = 0.45 if item["checked"] else 1

        remaining = sum(1 for item in self.items if not item["checked"])
        checked = len(self.items) - remaining
        self.empty.opacity = 0 if self.items else 1
        self._set_status(f"{remaining} to get" if remaining else ("All done" if self.items else "Nothing to get"))

        multi_page = pages > 1
        self.page_label.text = f"{self.page + 1} / {pages}" if multi_page else ""
        self._show(self.prev_button, multi_page)
        self._show(self.next_button, multi_page)
        if multi_page:
            self.prev_button.disabled = self.page == 0
            self.next_button.disabled = self.page >= pages - 1
            self.prev_button.opacity = 0.3 if self.prev_button.disabled else 1
            self.next_button.opacity = 0.3 if self.next_button.disabled else 1
        self._show(self.clear_button, checked > 0)
        self.clear_button.text = f"Clear {checked} checked"
