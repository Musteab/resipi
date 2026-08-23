"""Seam between the app lane and the Hermes runtime (Colin's lane).

The app NEVER implements a second chatbot. It calls one entry point:

    recipe_step(recipe, state, message) -> {state, actions, trace, runtime}

If `hermes.runtime` is importable we call it and the UI badges the turn as
`hermes`. Until it lands, a deterministic local walker stands in so the
simulator screen is buildable, and every turn is badged `local-stub` in the UI
and in the trace. Nothing here may invent a business fact - it can only follow
slots, templates, transitions and policies that exist in the compiled recipe.
"""
import re

RUNTIME_HERMES = "hermes"
RUNTIME_STUB = "local-stub"


def hermes_available():
    try:
        from hermes.runtime import recipe_step  # noqa: F401
        return True
    except Exception:
        return False


# --- deterministic stand-in walker ----------------------------------------
# Dr. Vegapunk split his brain into six satellites so the work continued while the
# main body was busy thinking. This is Resipi's satellite: same orders, same limits,
# strictly less genius. When the real brain (hermes.runtime) is home, it stands down.
SIZE_RX = re.compile(r"\b(\d{3,4}\s*g|\d+\s*kg)\b", re.I)
QTY_RX = re.compile(r"\b(\d{1,2})\s*(?:x|pcs?|piece|biji|satu|unit)?\b", re.I)
NUMWORD = {"satu": 1, "dua": 2, "tiga": 3, "one": 1, "two": 2, "three": 3}
DATE_RX = re.compile(r"\b(sabtu|ahad|isnin|selasa|rabu|khamis|jumaat|monday|tuesday|wednesday|thursday|friday|saturday|sunday|besok|esok|tomorrow|today|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", re.I)
PRICE_RX = re.compile(r"\b(price|harga|berapa|how much|cost|charge)\b", re.I)
RUSH_RX = re.compile(r"\b(urgent|rush|asap|tomorrow|esok|besok|today|hari ini|last minute)\b", re.I)
HUMAN_RX = re.compile(r"\b(speak|talk|call)\b.{0,20}\b(human|person|owner|manager|orang)\b|\bhuman\b", re.I)
CONFIRM_RX = re.compile(r"\b(yes|yep|ya|ok|okay|correct|betul|sahkan|confirm|setuju)\b", re.I)
DELIVERY_RX = re.compile(r"\b(deliver|delivery|hantar|send)\b", re.I)
PICKUP_RX = re.compile(r"\b(pickup|pick up|self.?collect|ambil|collect)\b", re.I)
INJECTION_RX = re.compile(r"\b(ignore|disregard|forget)\b.{0,30}\b(rule|instruction|prompt|system|recipe)\b|\byou are now\b", re.I)


# One distinctive Malay marker is enough - histories are heavily code-switched,
# so requiring two words misreads short replies like "ya betul" as English.
MS_MARKERS = {"nak", "boleh", "berapa", "untuk", "tarikh", "hantar", "ambil", "sahkan",
              "harga", "saya", "betul", "dulu", "esok", "besok", "banyak", "tak", "je",
              "ni", "satu", "dua", "tiga", "sabtu", "ahad", "isnin", "selasa", "rabu",
              "khamis", "jumaat", "kak", "bang", "terima", "kasih"}


def _lang(text):
    words = set(re.findall(r"[a-z']+", text.lower()))
    return "ms" if words & MS_MARKERS else "en"


def _products(recipe):
    """Product vocabulary comes only from evidence excerpts - never invented."""
    vocab = set()
    for e in recipe.get("evidence", []):
        for m in re.finditer(r"\b([a-z]+)\s+cake\b", e.get("redacted_excerpt", ""), re.I):
            vocab.add(m.group(0).lower())
    return vocab


def _extract_slots(recipe, text, slots):
    found = {}
    for p in _products(recipe):
        if p in text.lower():
            found["product"] = p
    m = SIZE_RX.search(text)
    if m:
        found["size"] = m.group(1).replace(" ", "").lower()
    low = text.lower()
    for w, n in NUMWORD.items():
        if re.search(r"\b" + w + r"\b", low):
            found["quantity"] = n
    m = re.search(r"\b(\d{1,2})\s*(?:x|pcs?|pieces?|biji)\b", low)
    if m:
        found["quantity"] = int(m.group(1))
    m = DATE_RX.search(text)
    if m and "size" not in ("",):
        val = m.group(1)
        if not SIZE_RX.fullmatch(val or ""):
            found["fulfilment_date"] = val.lower()
    if DELIVERY_RX.search(text):
        found["fulfilment_method"] = "delivery"
    elif PICKUP_RX.search(text):
        found["fulfilment_method"] = "pickup"
    declared = {s["id"] for s in recipe.get("slots", [])}
    return {k: v for k, v in found.items() if k in declared and k not in slots}


def _template(recipe, tid, lang, slots):
    for t in recipe.get("templates", []):
        if t["id"] == tid:
            text = t["variants"].get(lang) or t["variants"].get("en") or next(iter(t["variants"].values()))
            for k, v in slots.items():
                text = text.replace("{{" + k + "}}", str(v))
            return re.sub(r"\{\{\w+\}\}", "?", text), t.get("evidence_ids", [])
    return "(template " + tid + " missing)", []


def _required(recipe, slots):
    need = []
    for s in recipe.get("slots", []):
        rf = s.get("required_for", [])
        if "propose_order" in rf:
            need.append(s["id"])
        elif "propose_order_delivery" in rf and slots.get("fulfilment_method") == "delivery":
            need.append(s["id"])
    return need


def _prompt(recipe, sid, lang):
    for s in recipe.get("slots", []):
        if s["id"] == sid:
            return s["prompts"].get(lang) or s["prompts"].get("en"), s.get("evidence_ids", [])
    return "Could you tell me more?", []


def _stub_step(recipe, state, message):
    text = message.get("text", "")
    mid = str(message.get("message_id"))
    trace = {"runtime": RUNTIME_STUB, "message_id": mid, "state_in": state.get("state")}

    if mid in state.get("seen_message_ids", []):
        trace["result"] = "duplicate_ignored"
        return {"state": state, "actions": [], "trace": trace}
    state.setdefault("seen_message_ids", []).append(mid)

    lang = _lang(text)
    state["detected_language"] = lang
    slots = state.setdefault("slots", {})
    actions = []

    if INJECTION_RX.search(text):
        trace["note"] = "instruction-like customer text treated as untrusted content"

    def escalate(reason):
        state["state"] = "escalated"
        state["escalation"] = {"reason": reason, "message_id": mid}
        body, ev = _template(recipe, "escalate_to_owner", lang, slots)
        trace.update({"transition": "escalate", "policy": reason, "evidence_ids": ev, "state_out": "escalated"})
        return {"state": state, "actions": [{"type": "escalate", "reason": reason},
                                            {"type": "send", "text": body}], "trace": trace}

    if HUMAN_RX.search(text):
        return escalate("customer_requests_human")
    if PRICE_RX.search(text):
        return escalate("missing_price_or_availability")
    if RUSH_RX.search(text) and state.get("state") != "awaiting_customer_confirmation":
        return escalate("no_rush_order_without_owner")

    new = _extract_slots(recipe, text, slots)
    # A slot the recipe explicitly asked for last turn is answered by this turn.
    # Only slots the recipe declares can be filled this way - nothing is invented.
    pending = state.get("pending_slot")
    if pending and pending not in slots and not new and not CONFIRM_RX.fullmatch(text.strip()):
        new[pending] = text.strip()
    slots.update(new)
    for k, v in new.items():
        actions.append({"type": "set_slot", "slot": k, "value": v})

    if state.get("state") == "awaiting_customer_confirmation" and CONFIRM_RX.search(text) and not new:
        state["state"] = "awaiting_deposit"
        body, ev = _template(recipe, "awaiting_deposit_notice", lang, slots)
        actions += [{"type": "transition_state", "to": "awaiting_deposit"},
                    {"type": "send", "text": body}, {"type": "emit_owner_summary"}]
        trace.update({"transition": "customer_confirms", "policy": "deposit_before_confirmation",
                      "evidence_ids": ev, "state_out": "awaiting_deposit"})
        return {"state": state, "actions": actions, "trace": trace}

    need = _required(recipe, slots)
    missing = [s for s in need if s not in slots]
    state["missing_required_slots"] = missing

    if missing:
        q, ev = _prompt(recipe, missing[0], lang)
        state["state"] = "collecting"
        state["last_action"] = "ask_for_slot"
        state["pending_slot"] = missing[0]
        actions.append({"type": "ask_for_slot", "slot": missing[0]})
        actions.append({"type": "send", "text": q})
        trace.update({"transition": None, "asked": missing[0], "evidence_ids": ev, "state_out": "collecting"})
        return {"state": state, "actions": actions, "trace": trace}

    state["state"] = "awaiting_customer_confirmation"
    state["pending_slot"] = None
    state["last_action"] = "render_template"
    body, ev = _template(recipe, "order_summary", lang, slots)
    actions += [{"type": "transition_state", "to": "awaiting_customer_confirmation"},
                {"type": "render_template", "template_id": "order_summary"},
                {"type": "send", "text": body}]
    trace.update({"transition": "propose_complete_order", "evidence_ids": ev,
                  "state_out": "awaiting_customer_confirmation"})
    return {"state": state, "actions": actions, "trace": trace}


def recipe_step(recipe, state, message):
    """Single runtime entry point used by BOTH the simulator and the Telegram bot."""
    try:
        from hermes.runtime import recipe_step as hermes_step
        out = hermes_step(recipe, state, message)
        out.setdefault("trace", {})["runtime"] = RUNTIME_HERMES
        out["runtime"] = RUNTIME_HERMES
        return out
    except ImportError:
        out = _stub_step(recipe, state, message)
        out["runtime"] = RUNTIME_STUB
        return out
