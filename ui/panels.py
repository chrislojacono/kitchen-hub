import qrcode
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
from kivy.utils import escape_markup

from ui import api
from ui.ui_common import (ACCENT, ACCENT_TEXT, BODY_TEXT, ON_ACCENT, PANEL_COLOR, CardButton, debounced,
                          fit_text)

SUGGESTIONS = 12


class Panel(ModalView):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(0.88, 0.86), background="", background_color=(0, 0, 0, 0),
                         overlay_color=(0, 0, 0, 0.6), **kwargs)
        with self.canvas.before:
            Color(*PANEL_COLOR)
            self._rect = RoundedRectangle(radius=[24])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *_):
        self._rect.pos, self._rect.size = self.pos, self.size


class QuickAddPanel(Panel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        box = BoxLayout(orientation="vertical", padding=26, spacing=14)
        header = BoxLayout(size_hint=(1, 0.16))
        titles = BoxLayout(orientation="vertical")
        titles.add_widget(fit_text(Label(text="Tap to add", font_size=28, bold=True, color=BODY_TEXT)))
        self.hint = fit_text(Label(text="Anything else? Add it from your phone.", font_size=17, color=ACCENT_TEXT))
        titles.add_widget(self.hint)
        header.add_widget(titles)
        done = CardButton(text="Done", font_size=22, bold=True, bg=ACCENT, color=ON_ACCENT,
                          size_hint=(None, 1), width=150)
        done.bind(on_release=debounced(lambda _: self.dismiss()))
        header.add_widget(done)
        box.add_widget(header)

        grid = GridLayout(cols=4, spacing=10, size_hint=(1, 0.84))
        self.buttons = []
        for index in range(SUGGESTIONS):
            button = CardButton(font_size=22, shorten=True)
            button.bind(on_release=debounced(lambda _, i=index: self._add(i)))
            self.buttons.append(button)
            grid.add_widget(button)
        box.add_widget(grid)
        self.add_widget(box)
        self.names = []

    def on_pre_open(self):
        for button in self.buttons:
            button.text, button.opacity, button.disabled = "", 0, True
        self.hint.text = "Anything else? Add it from your phone."
        api.call("GET", f"/api/grocery/frequent?limit={SUGGESTIONS}", self._fill,
                 lambda _: self._set_hint("Can't reach the kitchen hub"))

    def _set_hint(self, text):
        self.hint.text = text

    def _fill(self, names):
        self.names = names
        for index, button in enumerate(self.buttons):
            if index < len(names):
                button.text, button.opacity, button.disabled = escape_markup(names[index]), 1, False

    def _add(self, index):
        button, name = self.buttons[index], self.names[index]
        button.text, button.disabled = f"Added  {escape_markup(name)}", True
        button.opacity = 0.45

        def failed(_):
            button.text, button.disabled, button.opacity = escape_markup(name), False, 1
            self._set_hint(f"Couldn't add {name}, try again")

        api.call("POST", "/api/grocery", lambda _: None, failed, body=[{"name": name}])


class QrCode(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._modules = []
        self.bind(pos=self._draw, size=self._draw)

    def show(self, data):
        matrix = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
        matrix.add_data(data)
        matrix.make(fit=True)
        self._modules = matrix.get_matrix()
        self._draw()

    def clear(self):
        self._modules = []
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        if not self._modules:
            return
        count = len(self._modules)
        cell = int(min(self.width, self.height) / count)
        side = cell * count
        left, bottom = self.center_x - side / 2, self.center_y - side / 2
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(pos=(left, bottom), size=(side, side))
            Color(0, 0, 0, 1)
            for row, line in enumerate(self._modules):
                for col, dark in enumerate(line):
                    if dark:
                        Rectangle(pos=(left + col * cell, bottom + (count - 1 - row) * cell), size=(cell, cell))


class PhonePanel(Panel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        box = BoxLayout(padding=30, spacing=30)
        self.qr = QrCode(size_hint=(None, 1), width=380)
        box.add_widget(self.qr)

        text = BoxLayout(orientation="vertical", spacing=10)
        text.add_widget(fit_text(Label(text="Add from your phone", font_size=30, bold=True, color=BODY_TEXT,
                                       size_hint=(1, 0.2))))
        self.steps = fit_text(Label(font_size=21, color=BODY_TEXT, size_hint=(1, 0.45), markup=True))
        text.add_widget(self.steps)
        self.note = fit_text(Label(font_size=17, color=ACCENT_TEXT, size_hint=(1, 0.17)))
        text.add_widget(self.note)
        close = CardButton(text="Close", font_size=22, size_hint=(1, 0.18))
        close.bind(on_release=debounced(lambda _: self.dismiss()))
        text.add_widget(close)
        box.add_widget(text)
        self.add_widget(box)
        self._expire_event = None

    def on_pre_open(self):
        self.qr.clear()
        self.steps.text = "Making a code..."
        self.note.text = ""
        api.call("POST", "/api/pair", self._paired, lambda _: self._failed())

    def on_dismiss(self):
        if self._expire_event:
            self._expire_event.cancel()
            self._expire_event = None

    def _paired(self, result):
        self.qr.show(result["url"])
        self.steps.text = ("1.  Open your phone's camera\n"
                           "2.  Point it at the code\n"
                           "3.  Tap the link, then save the page\n      to your home screen")
        self.note.text = f"The code works once and expires in {result['expires_in'] // 60} minutes."
        self._expire_event = Clock.schedule_once(lambda _: self.dismiss(), result["expires_in"])

    def _failed(self):
        self.steps.text = "Couldn't make a code.\nCheck that the kitchen hub server is running."
