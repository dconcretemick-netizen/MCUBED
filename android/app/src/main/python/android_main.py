"""Android entry point: runs the MCUBED gateway inside the app on 127.0.0.1.

Called from MainActivity through Chaquopy. The gateway runs in LITE mode
(standard library only). OpenRouter reaches every model; OpenAI and DeepSeek
keys are also used directly. With no keys it starts in demo (mock) mode.
"""
import json
import os
import secrets
import socket
import threading
import time
from os.path import dirname, join

KEY_NAMES = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GITHUB_TOKEN")
_state: dict = {}


def _apply_keys(keys_json: str) -> bool:
    """Export provider keys to the environment. Returns True if at least one key is set."""
    keys = json.loads(keys_json or "{}")
    for name in KEY_NAMES:
        value = (keys.get(name) or "").strip()
        if value:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)
    return any(os.getenv(n) for n in KEY_NAMES if n != "GITHUB_TOKEN")


def start(data_dir: str, keys_json: str = "{}") -> str:
    """Start the gateway once per process and return the dashboard URL."""
    if _state:
        set_keys(keys_json)
        return _state["url"]
    os.environ["GATEWAY_LITE"] = "1"
    has_key = _apply_keys(keys_json)
    import gateway  # imported after GATEWAY_LITE is set

    os.makedirs(data_dir, exist_ok=True)
    gw = gateway.Gateway(join(dirname(__file__), "models.json"),
                         join(data_dir, "gateway_usage.db"), mock=not has_key)

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


def set_keys(keys_json: str) -> bool:
    """Apply new keys without restarting. Returns True when running in demo mode."""
    has_key = _apply_keys(keys_json)
    gw = _state.get("gw")
    if gw is not None:
        gw.mock = not has_key
    return not has_key
