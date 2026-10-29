import json
import os
import threading
import urllib.request

from kivy.clock import Clock

BASE_URL = os.environ.get("KITCHEN_API", "http://127.0.0.1:8000")


def call(method, path, on_done, on_error=None):
    """Run an API request on a worker thread and hand the result back on the Kivy main thread."""
    def work():
        try:
            request = urllib.request.Request(
                BASE_URL + path, method=method, data=b"" if method == "POST" else None,
                headers={"Authorization": f"Bearer {os.environ.get('KITCHEN_TOKEN', '')}"})
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.load(response)
        except Exception as exc:
            if on_error:
                Clock.schedule_once(lambda _, e=exc: on_error(e))
            return
        Clock.schedule_once(lambda _: on_done(result))

    threading.Thread(target=work, daemon=True).start()
