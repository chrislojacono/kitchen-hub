from datetime import datetime

from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from ui.ui_common import GradientScreen

BG_TOP = (0.22, 0.10, 0.38, 1)
BG_BOTTOM = (0.02, 0.02, 0.04, 1)
ACCENT = (0.4, 0.9, 0.85, 1)


def _strftime(moment, fmt):
    # %-I / %-d are Linux-only; Windows spells them %#I / %#d.
    try:
        return moment.strftime(fmt)
    except ValueError:
        return moment.strftime(fmt.replace("%-", "%#"))


class ClockScreen(GradientScreen):
    def __init__(self, **kwargs):
        super().__init__(BG_TOP, BG_BOTTOM, **kwargs)
        self.root_box.add_widget(Widget(size_hint=(1, 0.18)))
        self.time_label = Label(font_size=160, bold=True, size_hint=(1, 0.45))
        self.meridiem_label = Label(font_size=34, bold=True, color=ACCENT, size_hint=(1, 0.1))
        self.date_label = Label(font_size=28, color=(0.75, 0.76, 0.85, 1), size_hint=(1, 0.12))
        for label in (self.time_label, self.meridiem_label, self.date_label):
            self.root_box.add_widget(label)
        self.root_box.add_widget(Widget(size_hint=(1, 0.15)))
        self._tick()
        Clock.schedule_interval(lambda _: self._tick(), 10)

    def _tick(self):
        now = datetime.now()
        self.time_label.text = _strftime(now, "%-I:%M")
        self.date_label.text = _strftime(now, "%A, %B %-d")
        self.meridiem_label.text = now.strftime("%p")
