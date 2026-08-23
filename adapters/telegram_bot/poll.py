"""Telegram bot adapter for NEW customer chats (stdlib long-polling).

Normalizes every update to {message_id, conversation_id, text, timestamp} and
hands it to the SAME runtime entry point the simulator uses. There is no parallel
chatbot here - this file only moves messages.

    TELEGRAM_BOT_TOKEN=... python3 adapters/telegram_bot/poll.py
"""
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from app import store, runtime_client  # noqa: E402

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED = {u.strip() for u in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if u.strip()}
API = "https://api.telegram.org/bot%s/" % TOKEN


def tls_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def call(method, **params):
    url = API + method + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=40, context=tls_context()) as r:
        return json.load(r)


def send(chat_id, text):
    call("sendMessage", chat_id=chat_id, text=text)


def handle(update):
    msg = update.get("message") or update.get("edited_message")
    if not msg or not msg.get("text"):
        return
    uid = str(msg["from"]["id"])
    chat_id = msg["chat"]["id"]
    text = msg["text"].strip()

    if text.startswith("/reset"):
        if ALLOWED and uid not in ALLOWED:
            return send(chat_id, "Not permitted.")
        store.reset()
        return send(chat_id, "Demo state reset.")

    recipe = store.get_latest("approved_recipe")
    if not recipe:
        return send(chat_id, "No approved recipe yet - approve one in the Resipi app first.")

    cid = "telegram:%s" % chat_id
    state = store.load_conversation(cid) or {
        "conversation_id": cid, "recipe_id": recipe.get("recipe_id"),
        "recipe_version": recipe.get("recipe_version"), "state": "collecting",
        "detected_language": "en", "slots": {}, "missing_required_slots": [],
        "seen_message_ids": [], "last_action": None, "escalation": None,
    }
    sender = msg.get("from") or {}
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])).strip()
    state["customer"] = {"id": str(sender.get("id") or chat_id),
                         "name": name or sender.get("username") or str(chat_id),
                         "username": sender.get("username")}
    normalized = {"message_id": str(msg["message_id"]), "conversation_id": cid,
                  "text": text, "timestamp": msg.get("date")}

    out = runtime_client.recipe_step(recipe, state, normalized)
    # Persist BEFORE replying: a crash after send must not lose the state.
    store.save_conversation(cid, out["state"])
    store.log("turn", {"cid": cid, "in": normalized, "trace": out["trace"],
                       "actions": out["actions"], "runtime": out["runtime"]})
    for a in out["actions"]:
        if a["type"] == "send":
            send(chat_id, a["text"])


def main():
    if not TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN is not set (see .env.example)")
    me = call("getMe")
    print("polling as @%s  (runtime: %s)" % (me["result"]["username"], runtime_client.RUNTIME_HERMES
          if runtime_client.hermes_available() else runtime_client.RUNTIME_STUB))
    offset = 0
    while True:
        try:
            r = call("getUpdates", offset=offset, timeout=30)
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                handle(u)
        except Exception as e:
            print("poll error:", e)
            time.sleep(2)


if __name__ == "__main__":
    main()
