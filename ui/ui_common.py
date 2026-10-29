import time

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

CARD_COLOR = (1, 1, 1, 0.055)
ACCENT_TEXT = (0.62, 0.68, 0.76, 1)
BODY_TEXT = (0.88, 0.9, 0.93, 1)
TAP_DEBOUNCE_SECONDS = 0.6


def make_vertical_gradient(top_rgba, bottom_rgba):
    tex = Texture.create(size=(1, 2), colorfmt="rgba")
    buf = bytes([int(c * 255) for c in bottom_rgba] + [int(c * 255) for c in top_rgba])
    tex.blit_buffer(buf, colorfmt="rgba", bufferfmt="ubyte")
    tex.mag_filter = "linear"
    tex.min_filter = "linear"
    return tex


def debounced(fn, seconds=TAP_DEBOUNCE_SECONDS):
    # The touchscreen fires ghost double-touches; ignore repeats inside the window.
    last = [0.0]

    def wrapper(*args):
        now = time.monotonic()
        if now - last[0] < seconds:
            return
        last[0] = now
        fn(*args)
    return wrapper


def fit_text(label, halign="left"):
    label.halign = halign
    label.valign = "middle"
    label.bind(size=lambda inst, _: setattr(inst, "text_size", (inst.width - 2 * inst.padding_x, inst.height)))
    return label


class Card(BoxLayout):
    def __init__(self, radius=20, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*CARD_COLOR)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class CardButton(Button):
    def __init__(self, radius=16, halign="center", **kwargs):
        super().__init__(background_normal="", background_down="", background_disabled_normal="",
                         background_color=(0, 0, 0, 0), color=BODY_TEXT, markup=True,
                         padding_x=24, **kwargs)
        with self.canvas.before:
            self._bg = Color(*CARD_COLOR)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])
        self.bind(pos=self._update_rect, size=self._update_rect, state=self._update_state)
        fit_text(self, halign)

    def _update_rect(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _update_state(self, *_):
        self._bg.a = CARD_COLOR[3] * 3 if self.state == "down" else CARD_COLOR[3]


class GradientScreen(Screen):
    def __init__(self, bg_top, bg_bottom, padding=26, spacing=14, **kwargs):
        super().__init__(**kwargs)
        self.root_box = BoxLayout(orientation="vertical", padding=padding, spacing=spacing)
        with self.root_box.canvas.before:
            Color(1, 1, 1, 1)
            self._bg_rect = Rectangle(size=self.root_box.size, pos=self.root_box.pos,
                                      texture=make_vertical_gradient(bg_top, bg_bottom))
        self.root_box.bind(size=self._update_bg, pos=self._update_bg)
        self.add_widget(self.root_box)

    def _update_bg(self, instance, _):
        self._bg_rect.size = instance.size
        self._bg_rect.pos = instance.pos


def eyebrow(text, size_hint=(1, 0.08)):
    return fit_text(Label(text=" ".join(text.upper()), font_size=13, bold=True,
                          color=ACCENT_TEXT, size_hint=size_hint))
