import os
import socket
import threading
import time
import webview
from app import app, assistant_settings_payload
from eve_agent import native_agent_status, run_native_agent


def find_free_port() -> int:
    requested = int(os.environ.get("REFORM_LIFE_PORT", "0") or 0)
    if requested:
        return requested
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def start_flask(port: int):
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def start_eve_agent(port: int) -> threading.Thread:
    """Start the optional local wake-word loop without blocking the UI."""

    def worker() -> None:
        try:
            with app.app_context():
                settings = assistant_settings_payload()
            if not settings.get("enabled"):
                return
            native = native_agent_status()
            if not native.get("ready"):
                # The browser/manual assistant remains available when the
                # optional native packages or model are not installed.
                return
            run_native_agent(
                server_url=f"http://127.0.0.1:{port}",
                wake_word=str(settings.get("wake_word") or "эва"),
                continuous_dialog=bool(settings.get("continuous_dialog", True)),
                device=settings.get("microphone_device"),
            )
        except Exception:
            # A microphone/model problem must never prevent the planner window
            # from opening. The status endpoint exposes the reason to the UI.
            return

    thread = threading.Thread(target=worker, name="eve-native-agent", daemon=True)
    thread.start()
    return thread


def wait_for_server(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Не удалось запустить локальный сервер RE:FORM LIFE")


if __name__ == "__main__":
    port = find_free_port()
    t = threading.Thread(target=start_flask, args=(port,), daemon=True)
    t.start()
    wait_for_server(port)
    window = webview.create_window(
        title="RE:FORM LIFE",
        url=f"http://127.0.0.1:{port}",
        width=1400,
        height=900,
        min_size=(1200, 700),
        resizable=True,
        background_color="#070b12"
    )

    # The offline speech model is intentionally loaded after the page appears.
    webview.events.loaded += lambda: start_eve_agent(port)

    # Запуск приложения (окно)
    webview.start()
