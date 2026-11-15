"""Values shared with the rest of ryce-pc. Mirrors contracts/constants.json
(tests/test_contract.py fails if the two drift); agentd is deployed without
the contracts directory, so they are restated here rather than read."""

TAG = "agentwait"
SIGNAL = 9
RUNTIME = "agentd"
ROSTER_FILE = "roster.json"
LOCK_FILE = "lock.txt"
WAYBAR_DIR = "waybar"
AGENTS_FILE = "agents.json"
MAX_WS = 11
DISPATCH_TAG = 'hl.dsp.window.tag({ tag = "%s", window = "address:%s" })'
ALWAYS_SHOWN = 5        # slots 1..5 always show (empty = dim numeral); others only in use

# One vocabulary for the bar and the sidebar (contracts/constants.json words_es).
WORDS = {
    "state": {
        "waiting": "te espera",
        "busy": "trabajando",
        "shell": "comando en marcha",
        "idle": "en reposo",
        "unknown": "sin estado",
    },
    "waiting_for": {
        "permission prompt": "pide permiso",
        "input needed": "espera tu respuesta",
        "dialog open": "tiene un diálogo abierto",
        "sandbox request": "pide salir del sandbox",
        "worker request": "un subagente pide permiso",
    },
    "waiting_fallback": "te espera",
    "lock_one": "1 agente te espera",
    "lock_many": "%d agentes te esperan",
}
