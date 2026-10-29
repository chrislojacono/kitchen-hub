import sys

from dotenv import load_dotenv

load_dotenv()

from kivy.config import Config

Config.set("graphics", "width", "1024")
Config.set("graphics", "height", "600")
Config.set("graphics", "resizable", "0")
if sys.platform.startswith("linux"):
    Config.set("graphics", "fullscreen", "auto")

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, RoundedRectangle
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, SlideTransition

from ui.clock_screen import ClockScreen
from ui.dinners_screen import DinnersScreen
from ui.grocery_screen import GroceryScreen
from ui.ui_common import debounced

SCREENS = [
    ("grocery", "Grocery list", GroceryScreen),
    ("dinners", "Dinners", DinnersScreen),
    ("clock", "Clock", ClockScreen),
]


class ScreenTitleBadge(Label):
    def __init__(self, **kwargs):
        super().__init__(font_size=15, bold=True, size_hint=(None, None), size=(180, 34),
                         color=(1, 1, 1, 0), **kwargs)
        with self.canvas.before:
            self._bg = Color(0.05, 0.05, 0.07, 0)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[17])
        self.bind(pos=self._update_rect, size=self._update_rect)
        self._hide_event = None

    def _update_rect(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def show(self, text):
        self.text = text
        self.color = (1, 1, 1, 0.95)
        self._bg.a = 0.7
        if self._hide_event:
            self._hide_event.cancel()
        self._hide_event = Clock.schedule_once(lambda _: self._hide(), 1.4)

    def _hide(self):
        self.color = (1, 1, 1, 0)
        self._bg.a = 0


class NavArrow(Button):
    def __init__(self, direction, **kwargs):
        super().__init__(text="‹" if direction == "left" else "›", font_size=36,
                         size_hint=(None, None), size=(64, 64), background_normal="",
                         background_color=(0, 0, 0, 0), **kwargs)
        with self.canvas.before:
            Color(0.05, 0.05, 0.07, 0.78)
            self._circle = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self._update_circle, size=self._update_circle)

    def _update_circle(self, *_):
        self._circle.pos = self.pos
        self._circle.size = self.size


class RootLayout(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sm = ScreenManager(transition=SlideTransition(duration=0.25))
        for name, _, screen in SCREENS:
            self.sm.add_widget(screen(name=name))
        self.add_widget(self.sm)
        # Kivy doesn't reliably fire on_enter for the first screen, so start it explicitly.
        Clock.schedule_once(lambda _: self.sm.current_screen.dispatch("on_enter"))

        for direction, step, pos_hint in (("left", -1, {"x": 0.01, "center_y": 0.5}),
                                          ("right", 1, {"right": 0.99, "center_y": 0.5})):
            arrow = NavArrow(direction, pos_hint=pos_hint)
            arrow.bind(on_release=debounced(lambda _, s=step: self._navigate(s)))
            self.add_widget(arrow)

        self.title_badge = ScreenTitleBadge(pos_hint={"center_x": 0.5, "y": 0.02})
        self.add_widget(self.title_badge)

    def _navigate(self, step):
        names = [name for name, _, _ in SCREENS]
        index = (names.index(self.sm.current) + step) % len(names)
        self.sm.transition.direction = "left" if step > 0 else "right"
        self.sm.current = names[index]
        self.title_badge.show(SCREENS[index][1])


class KitchenHubApp(App):
    title = "Kitchen Hub"

    def build(self):
        return RootLayout()


if __name__ == "__main__":
    KitchenHubApp().run()
