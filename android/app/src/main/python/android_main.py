"""Android entry point: runs the MCUBED gateway inside the app on 127.0.0.1.

Called from MainActivity through Chaquopy. The gateway runs in LITE mode
(standard library only) and reaches every model through OpenRouter. Without
an API key it starts in demo (mock) mode so the dashboard still works.
"""
import os
import secrets
import socket
import threading
import time
from os.path import dirname, join

_state: dict = {}


def start(data_dir: str, openrouter_key: str = "") -> str:
    """Start the gateway once per process and return the dashboard URL."""
    if _state:
        set_key(openrouter_key)
        return _state["url"]
    os.environ["GATEWAY_LITE"] = "1"
    if openrouter_key:
        os.environ["OPENROUTER_API_KEY"] = openrouter_key
    import gateway  # imported after GATEWAY_LITE is set

    os.makedirs(data_dir, exist_ok=True)
    gw = gateway.Gateway(join(dirname(__file__), "models.json"),
                         join(data_dir, "gateway_usage.db"), mock=not openrouter_key)

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    token = secrets.token_urlsafe(24)
    threading.Thread(target=gateway.serve_gui, args=(gw, "127.0.0.1", port, token),
                     name="mcubed-gui", daemon=True).start()

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("MCUBED gateway did not start")

    _state.update(gw=gw, url=f"http://127.0.0.1:{port}/?token={token}")
    return _state["url"]


def set_key(openrouter_key: str) -> bool:
    """Apply a new OpenRouter key without restarting. Empty key = demo mode."""
    if openrouter_key:
        os.environ["OPENROUTER_API_KEY"] = openrouter_key
    else:
        os.environ.pop("OPENROUTER_API_KEY", None)
    gw = _state.get("gw")
    if gw is not None:
        gw.mock = not openrouter_key
    return not openrouter_key
