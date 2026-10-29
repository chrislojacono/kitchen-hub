from datetime import date, timedelta

from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from ui import api
from ui.panels import Panel
from ui.ui_common import (ACCENT, ACCENT_TEXT, BODY_TEXT, CARD_COLOR, ON_ACCENT, CardButton, GradientScreen,
                          debounced, fit_text)

BG_TOP = (0.22, 0.14, 0.07, 1)
BG_BOTTOM = (0.04, 0.03, 0.02, 1)
COOK_COLORS = [(0.12, 0.36, 0.26, 1), (0.16, 0.27, 0.45, 1), (0.42, 0.26, 0.13, 1)]
TAKEOUT_COLOR = (0.42, 0.18, 0.23, 1)
TAKEOUT_TEXT = (1, 0.62, 0.70, 1)
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
REFRESH_SECONDS = 60
CONFIRM_SECONDS = 3


def week_start(offset=0):
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset)


def cook_color(cooks, cook):
    return COOK_COLORS[cooks.index(cook) % len(COOK_COLORS)] if cook in cooks else COOK_COLORS[0]


class Chip(Label):
    def __init__(self, **kwargs):
        super().__init__(font_size=15, bold=True, size_hint=(1, None), height=30, color=BODY_TEXT, **kwargs)
        with self.canvas.before:
            self._color = Color(0, 0, 0, 0)
            self._rect = RoundedRectangle(radius=[15])
        self.bind(pos=self._update, size=self._update)

    def _update(self, *_):
        self._rect.pos, self._rect.size = self.pos, self.size

    def set(self, text, rgba=(0, 0, 0, 0)):
        self.text = text
        self._color.rgba = rgba if text else (0, 0, 0, 0)


class DayCard(ButtonBehavior, BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=[8, 14, 8, 12], spacing=6, **kwargs)
        with self.canvas.before:
            self._bg = Color(*CARD_COLOR)
            self._rect = RoundedRectangle(radius=[16])
            self._outline_color = Color(*ACCENT[:3], 0)
            self._outline = Line(width=1.6)
        self.bind(pos=self._update, size=self._update, state=self._pressed)
        self.day_label = Label(font_size=19, bold=True, size_hint=(1, None), height=24, color=BODY_TEXT)
        self.date_label = Label(font_size=14, size_hint=(1, None), height=20, color=ACCENT_TEXT)
        self.title = Label(font_size=18, color=BODY_TEXT, halign="center", valign="top", max_lines=7)
        self.title.bind(size=lambda inst, _: setattr(inst, "text_size", (inst.width, inst.height)))
        self.chip = Chip()
        self.notes = Label(font_size=14, color=ACCENT_TEXT, halign="center", valign="bottom", max_lines=4)
        self.notes.bind(size=lambda inst, _: setattr(inst, "text_size", (inst.width, inst.height)))
        self.extra = Label(font_size=13, size_hint=(1, None), height=18, color=ACCENT_TEXT)
        for widget in (self.day_label, self.date_label, Widget(size_hint=(1, None), height=4), self.title,
                       self.notes, self.chip, self.extra):
            self.add_widget(widget)

    def _update(self, *_):
        self._rect.pos, self._rect.size = self.pos, self.size
        self._outline.rounded_rectangle = (self.x, self.y, self.width, self.height, 16)

    def _pressed(self, *_):
        self._bg.a = CARD_COLOR[3] * 3 if self.state == "down" else CARD_COLOR[3]

    def show(self, day, meal, cooks):
        today = day == date.today()
        self.day_label.text = "Today" if today else DAY_NAMES[day.weekday()]
        self.date_label.text = f"{day:%b} {day.day}"
        self._outline_color.a = 1 if today else 0
        if meal is None:
            self.title.text, self.title.color = "+", ACCENT_TEXT
            self.chip.set("")
            self.notes.text = ""
            self.extra.text = ""
            return
        self.title.text = meal["title"]
        self.title.color = TAKEOUT_TEXT if meal["takeout"] else BODY_TEXT
        self.notes.text = meal.get("notes") or ""
        if meal["cook"] and not meal["takeout"]:
            self.chip.set(meal["cook"], cook_color(cooks, meal["cook"]))
        else:
            self.chip.set("Take-Out!" if meal["takeout"] and meal["title"] != "Take-Out!" else "",
                          TAKEOUT_COLOR)
        lines = (meal.get("recipe") or {}).get("lines") or []
        self.extra.text = f"{len(lines)} ingredients" if lines else ""


class ConfirmButton(CardButton):
    """A destructive button that asks for a second tap before acting."""

    def __init__(self, text, confirm_text, on_confirm, **kwargs):
        super().__init__(text=text, **kwargs)
        self.base_text, self.confirm_text, self.on_confirm = text, confirm_text, on_confirm
        self._armed = None
        self.bind(on_release=debounced(lambda _: self._tap()))

    def reset(self, text=None, confirm_text=None):
        if self._armed:
            self._armed.cancel()
            self._armed = None
        self.base_text = text or self.base_text
        self.confirm_text = confirm_text or self.confirm_text
        self.text = self.base_text

    def _tap(self):
        if self._armed:
            self.reset()
            self.on_confirm()
            return
        self.text = self.confirm_text
        self._armed = Clock.schedule_once(lambda _: self.reset(), CONFIRM_SECONDS)


class DinnerPanel(Panel):
    def __init__(self, on_change, **kwargs):
        super().__init__(**kwargs)
        self.on_change = on_change
        self.day, self.meal, self.cooks, self.week = None, None, [], []

        box = BoxLayout(orientation="vertical", padding=26, spacing=14)
        header = BoxLayout(size_hint=(1, None), height=96)
        titles = BoxLayout(orientation="vertical")
        self.day_label = fit_text(Label(font_size=17, color=ACCENT_TEXT))
        self.title_label = fit_text(Label(font_size=28, bold=True, color=BODY_TEXT, shorten=True))
        self.notes_label = fit_text(Label(font_size=17, color=ACCENT_TEXT, shorten=True))
        titles.add_widget(self.day_label)
        titles.add_widget(self.title_label)
        titles.add_widget(self.notes_label)
        header.add_widget(titles)
        close = CardButton(text="Done", font_size=22, bold=True, bg=ACCENT, color=ON_ACCENT, size_hint=(None, 1),
                           width=140)
        close.bind(on_release=debounced(lambda _: self.dismiss()))
        header.add_widget(close)
        box.add_widget(header)

        self.cook_row = BoxLayout(size_hint=(1, None), height=64, spacing=10)
        self.cook_row.add_widget(fit_text(Label(text="Cooking", font_size=18, color=ACCENT_TEXT, size_hint=(None, 1),
                                                width=110)))
        self.cook_buttons = []
        for index in range(4):
            button = CardButton(font_size=20)
            button.bind(on_release=debounced(lambda _, i=index: self._set_cook(i)))
            self.cook_buttons.append(button)
            self.cook_row.add_widget(button)
        box.add_widget(self.cook_row)

        actions = BoxLayout(size_hint=(1, None), height=64, spacing=10)
        self.takeout_button = ConfirmButton("Take-Out!", "Tap again to replace", self._toggle_takeout, font_size=20)
        self.ingredients_button = CardButton(text="Add ingredients to list", font_size=20, size_hint=(1.6, 1))
        self.ingredients_button.bind(on_release=debounced(lambda _: self._add_ingredients()))
        self.delete_button = ConfirmButton("Delete", "Tap again to delete", self._delete, font_size=20,
                                           color=(1, 0.54, 0.5, 1))
        for widget in (self.takeout_button, self.ingredients_button, self.delete_button):
            actions.add_widget(widget)
        box.add_widget(actions)

        self.move_label = fit_text(Label(text="Move to", font_size=18, color=ACCENT_TEXT, size_hint=(1, None),
                                         height=26))
        box.add_widget(self.move_label)
        self.move_row = GridLayout(cols=7, spacing=8, size_hint=(1, None), height=64)
        self.move_buttons = []
        for index in range(7):
            button = CardButton(font_size=18)
            button.bind(on_release=debounced(lambda _, i=index: self._move(i)))
            self.move_buttons.append(button)
            self.move_row.add_widget(button)
        box.add_widget(self.move_row)
        self.status = fit_text(Label(font_size=18, color=ACCENT_TEXT, size_hint=(1, None), height=30))
        box.add_widget(self.status)
        box.add_widget(Widget())
        self.add_widget(box)

    @staticmethod
    def _show(widget, visible):
        widget.opacity, widget.disabled = (1, False) if visible else (0, True)

    def open_for(self, day, meal, cooks, week):
        self.day, self.meal, self.cooks, self.week = day, meal, cooks, week
        self.status.text = ""
        self._render()
        self.open()

    def _render(self):
        meal = self.meal
        self.day_label.text = f"{self.day:%A}, {self.day:%B} {self.day.day}"
        self.title_label.text = meal["title"] if meal else "Nothing planned yet"
        notes = (meal or {}).get("notes") or ""
        self.notes_label.text = f"From: {notes}" if notes and meal["takeout"] else notes
        show_cooks = meal is not None and not meal["takeout"]
        self._show(self.cook_row, show_cooks)
        options = self.cooks[:3] + [None]
        for index, button in enumerate(self.cook_buttons):
            if index >= len(options) or not show_cooks:
                self._show(button, False)
                continue
            cook = options[index]
            selected = meal["cook"] == cook
            button.text = cook or "Nobody"
            button._bg.rgba = cook_color(self.cooks, cook) if selected and cook else (
                (1, 1, 1, 0.16) if selected else CARD_COLOR)
            button._bg_alpha = button._bg.a
            self._show(button, True)

        if meal is None:
            self.takeout_button.reset("Take-Out!", "Tap again to confirm")
        elif meal["takeout"]:
            self.takeout_button.reset("Not take-out", "Tap again to clear")
        else:
            self.takeout_button.reset("Take-Out!", "Tap again to replace")
        lines = ((meal or {}).get("recipe") or {}).get("lines") or []
        self._show(self.ingredients_button, bool(lines))
        self._show(self.delete_button, meal is not None)
        self.delete_button.reset()
        self._show(self.move_label, meal is not None)
        self._show(self.move_row, meal is not None)
        for index, button in enumerate(self.move_buttons):
            target = self.week[index]
            button.text = "Today" if target == date.today() else DAY_NAMES[target.weekday()]
            button.disabled = meal is None or target == self.day
            button.opacity = 0.3 if target == self.day else 1
        if meal is None:
            self.status.text = "Plan dinners from your phone, or make it a take-out night."

    def _saved(self, meal):
        self.meal = meal
        self._render()
        self.on_change()

    def _put(self, changes):
        body = {key: self.meal.get(key) for key in ("title", "recipe", "cook", "takeout", "notes")} if self.meal else {}
        body.update(changes)
        api.call("PUT", f"/api/meals/{self.day.isoformat()}", self._saved, lambda e: self._failed(e), body=body)

    def _failed(self, _):
        self.status.text = "Couldn't save, try again"

    def _set_cook(self, index):
        options = self.cooks[:3] + [None]
        if self.meal and index < len(options):
            self._put({"cook": options[index]})

    def _toggle_takeout(self):
        if self.meal and self.meal["takeout"]:
            if self.meal["title"] == "Take-Out!":
                self._delete()
            else:
                self._put({"takeout": False})
            return
        self._put({"title": "Take-Out!", "takeout": True, "cook": None, "recipe": None})

    def _add_ingredients(self):
        def add(ingredients):
            names = [{"name": item["name"]} for item in ingredients if item["suggested"]]
            if not names:
                self.status.text = "Nothing new to buy: it's all in the pantry"
                return
            api.call("POST", "/api/grocery",
                     lambda _: setattr(self.status, "text", f"Added {len(names)} items to the grocery list"),
                     lambda e: self._failed(e), body=names)

        self.status.text = "Adding..."
        api.call("GET", f"/api/meals/{self.day.isoformat()}/ingredients", add, lambda e: self._failed(e))

    def _move(self, index):
        target = self.week[index]

        def moved(_):
            self.on_change()
            self.dismiss()

        api.call("POST", f"/api/meals/{self.day.isoformat()}/move?to={target.isoformat()}", moved,
                 lambda e: self._failed(e))

    def _delete(self):
        def deleted(_):
            self.on_change()
            self.dismiss()

        api.call("DELETE", f"/api/meals/{self.day.isoformat()}", deleted, lambda e: self._failed(e))


class DinnersScreen(GradientScreen):
    def __init__(self, **kwargs):
        super().__init__(BG_TOP, BG_BOTTOM, padding=[96, 18, 96, 18], spacing=14, **kwargs)
        self.offset, self.meals, self.cooks = 0, {}, []
        self._refresh_event = None
        self.panel = DinnerPanel(on_change=self._load)

        header = BoxLayout(size_hint=(1, 0.13), spacing=12)
        titles = BoxLayout(orientation="vertical")
        titles.add_widget(fit_text(Label(text="Dinners", font_size=30, bold=True, color=BODY_TEXT)))
        self.week_label = fit_text(Label(font_size=17, color=ACCENT_TEXT))
        titles.add_widget(self.week_label)
        header.add_widget(titles)
        for text, step in (("Prev week", -1), ("Next week", 1)):
            button = CardButton(text=text, font_size=19, size_hint=(None, 1), width=140)
            button.bind(on_release=debounced(lambda _, s=step: self._turn_week(s)))
            header.add_widget(button)
        self.root_box.add_widget(header)

        grid = GridLayout(cols=7, spacing=8, size_hint=(1, 0.87))
        self.cards = []
        for index in range(7):
            card = DayCard()
            card.bind(on_release=debounced(lambda _, i=index: self._open_day(i)))
            self.cards.append(card)
            grid.add_widget(card)
        self.root_box.add_widget(grid)
        self._render()

    def on_enter(self, *_):
        self.on_leave()
        api.call("GET", "/api/cooks", self._cooks_loaded)
        self._load()
        self._refresh_event = Clock.schedule_interval(lambda _: self._load(), REFRESH_SECONDS)

    def on_leave(self, *_):
        if self._refresh_event:
            self._refresh_event.cancel()
            self._refresh_event = None

    def _cooks_loaded(self, cooks):
        self.cooks = cooks
        self._render()

    def _week(self):
        start = week_start(self.offset)
        return [start + timedelta(days=index) for index in range(7)]

    def _load(self):
        start = week_start(self.offset).isoformat()
        api.call("GET", f"/api/meals?start={start}&days=7", self._loaded,
                 lambda _: setattr(self.week_label, "text", "Can't reach the kitchen hub"))

    def _loaded(self, meals):
        self.meals = {meal["date"]: meal for meal in meals if meal["slot"] == "dinner"}
        self._render()

    def _turn_week(self, step):
        self.offset += step
        self.meals = {}
        self._render()
        self._load()

    def _render(self):
        week = self._week()
        names = {-1: "Last week", 0: "This week", 1: "Next week"}
        self.week_label.text = names.get(self.offset, f"{week[0]:%b} {week[0].day} - {week[-1]:%b} {week[-1].day}")
        for day, card in zip(week, self.cards):
            card.show(day, self.meals.get(day.isoformat()), self.cooks)

    def _open_day(self, index):
        week = self._week()
        self.panel.open_for(week[index], self.meals.get(week[index].isoformat()), self.cooks, week)
