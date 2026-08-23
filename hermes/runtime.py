import re

SIZE_RX = re.compile(r"\b(\d{3,4}\s*g|\d+(?:\.\d+)?\s*kg|\d+\s*(?:inch|in))\b", re.I)
DATE_RX = re.compile(r"\b(sabtu|ahad|isnin|selasa|rabu|khamis|jumaat|monday|tuesday|wednesday|thursday|friday|saturday|sunday|besok|esok|tomorrow|today|hari ini|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", re.I)
PRICE_RX = re.compile(r"\b(price|harga|berapa|how much|cost|charge)\b", re.I)
RUSH_RX = re.compile(r"\b(urgent|rush|asap|tomorrow|esok|besok|today|hari ini|last minute)\b", re.I)
HUMAN_RX = re.compile(r"\b(speak|talk|call)\b.{0,20}\b(human|person|owner|manager|orang)\b|\bhuman\b", re.I)
CONFIRM_RX = re.compile(r"\b(yes|yep|ya|ok|okay|correct|betul|sahkan|confirm|setuju)\b", re.I)
DELIVERY_RX = re.compile(r"\b(deliver|delivery|hantar|send)\b", re.I)
PICKUP_RX = re.compile(r"\b(pickup|pick up|self.?collect|ambil|collect)\b", re.I)
INJECTION_RX = re.compile(r"\b(ignore|disregard|forget)\b.{0,30}\b(rule|instruction|prompt|system|recipe)\b|\byou are now\b", re.I)
NUMWORDS = {"satu": 1, "dua": 2, "tiga": 3, "one": 1, "two": 2, "three": 3}
MS_MARKERS = {"nak", "boleh", "berapa", "untuk", "tarikh", "hantar", "ambil", "sahkan", "harga", "saya", "betul", "dulu", "esok", "besok", "banyak", "tak", "je", "ni", "satu", "dua", "tiga", "sabtu", "ahad", "isnin", "selasa", "rabu", "khamis", "jumaat", "kak", "bang", "terima", "kasih"}


def _language(text):
    return "ms" if set(re.findall(r"[a-z']+", text.lower())) & MS_MARKERS else "en"


def _item(recipe, collection, item_id):
    return next((item for item in recipe.get(collection, []) if item.get("id") == item_id), None)


def _products(recipe):
    products = set()
    product_slot = _item(recipe, "slots", "product") or {}
    for key in ("values", "options", "enum"):
        products.update(str(value).lower() for value in product_slot.get(key, []))
    for evidence in recipe.get("evidence", []):
        excerpt = evidence.get("redacted_excerpt", "")
        products.update(match.group(0).lower() for match in re.finditer(r"\b[a-z]+\s+cake(?:s)?\b|\b[a-z]+\s+cupcakes?\b", excerpt, re.I))
    return products


ROLE_HINTS = {
    "product":           ("product", "item", "cake", "type", "order_item", "menu"),
    "size":              ("size", "weight", "saiz"),
    "quantity":          ("quantity", "qty", "amount", "count", "berapa"),
    "fulfilment_date":   ("date", "when", "day", "tarikh", "deadline", "needed"),
    "fulfilment_method": ("method", "fulfil", "fulfill", "pickup", "delivery", "collect"),
    "delivery_address":  ("address", "alamat", "location"),
}


def _roles(recipe):
    """Map our extraction roles onto whatever the recipe actually calls its slots.

    Qwen names slots freely - `cake_type` in one run, `product` in another - so
    nothing here may hardcode a slot id. A role only binds to a slot the recipe
    actually declares; unbound roles are simply never filled.
    """
    roles = {}
    for slot in recipe.get("slots", []):
        sid = str(slot.get("id", ""))
        haystack = " ".join([sid, str(slot.get("type", "")),
                             " ".join(str(v) for v in (slot.get("prompts") or {}).values())]).lower()
        for role, hints in ROLE_HINTS.items():
            if role in roles:
                continue
            if any(h in sid.lower() for h in hints) or any(h in haystack for h in hints):
                roles[role] = sid
                break
    return roles


def _extract_slots(recipe, text, existing):
    roles = _roles(recipe)
    found = {}
    low = text.lower()

    def put(role, value):
        sid = roles.get(role)
        if sid:
            found[sid] = value

    for product in _products(recipe):
        if product in low:
            put("product", product)
    size = SIZE_RX.search(text)
    if size:
        put("size", re.sub(r"\s+", "", size.group(1).lower()))
    for word, number in NUMWORDS.items():
        if re.search(r"\b" + word + r"\b", low):
            put("quantity", number)
    quantity = re.search(r"\b(\d{1,2})\s*(?:x|pcs?|pieces?|biji|unit)\b", low)
    if quantity:
        put("quantity", int(quantity.group(1)))
    date = DATE_RX.search(text)
    if date:
        put("fulfilment_date", date.group(1).lower())
    if DELIVERY_RX.search(text):
        put("fulfilment_method", "delivery")
    elif PICKUP_RX.search(text):
        put("fulfilment_method", "pickup")
    declared = {slot.get("id") for slot in recipe.get("slots", [])}
    return {key: value for key, value in found.items() if key in declared and key not in existing}


def _pending_value(slot_id, text):
    clean = text.strip()
    if slot_id == "quantity":
        if clean.lower() in NUMWORDS:
            return NUMWORDS[clean.lower()]
        if re.fullmatch(r"\d{1,2}", clean):
            return int(clean)
        return None
    if slot_id == "fulfilment_method":
        if DELIVERY_RX.search(clean):
            return "delivery"
        if PICKUP_RX.search(clean):
            return "pickup"
        return None
    if slot_id == "size":
        match = SIZE_RX.fullmatch(clean)
        return re.sub(r"\s+", "", match.group(1).lower()) if match else None
    return clean or None


def _template(recipe, template_id, language, slots):
    template = _item(recipe, "templates", template_id)
    if not template:
        return None, []
    variants = template.get("variants", {})
    text = variants.get(language) or variants.get("en") or next(iter(variants.values()), "")
    for key, value in slots.items():
        text = text.replace("{{" + key + "}}", str(value))
    return re.sub(r"\{\{\w+\}\}", "?", text), template.get("evidence_ids", [])


def _required(recipe, slots):
    required = []
    for slot in recipe.get("slots", []):
        purposes = slot.get("required_for", [])
        if "propose_order" in purposes:
            required.append(slot["id"])
        elif "propose_order_delivery" in purposes and slots.get("fulfilment_method") == "delivery":
            required.append(slot["id"])
    return required


def _prompt(recipe, slot_id, language):
    slot = _item(recipe, "slots", slot_id)
    if not slot:
        return None, []
    prompts = slot.get("prompts", {})
    return prompts.get(language) or prompts.get("en") or next(iter(prompts.values()), None), slot.get("evidence_ids", [])


def _policy_for_field(recipe, field):
    return next((policy for policy in recipe.get("policies", [])
                 if policy.get("machine_rule", {}).get("field") == field), None)


def _transition_for(recipe, state_id, intent):
    return next((transition for transition in recipe.get("transitions", [])
                 if transition.get("from") == state_id
                 and transition.get("trigger", {}).get("intent") == intent), None)


def _transition_template(transition):
    return next((action.get("template_id") for action in transition.get("actions", [])
                 if action.get("type") == "render_template" and action.get("template_id")), None)


def _escalation_template(recipe):
    exact = _item(recipe, "templates", "escalate_to_owner")
    if exact:
        return exact["id"]
    return next((template.get("id") for template in recipe.get("templates", [])
                 if "owner" in (template.get("purpose", "") + " " + template.get("id", "")).lower()), None)


def recipe_step(recipe, state, message):
    if recipe.get("schema_version") != "resipi.recipe.v1" or recipe.get("status") != "approved":
        raise ValueError("Hermes accepts only approved resipi.recipe.v1 recipes")
    text = str(message.get("text", ""))
    message_id = str(message.get("message_id", ""))
    trace = {"runtime": "hermes", "message_id": message_id, "state_in": state.get("state")}
    seen = state.setdefault("seen_message_ids", [])
    if message_id in seen:
        trace["result"] = "duplicate_ignored"
        return {"state": state, "actions": [], "trace": trace}
    seen.append(message_id)

    language = _language(text)
    state["detected_language"] = language
    slots = state.setdefault("slots", {})
    actions = []
    if INJECTION_RX.search(text):
        trace["note"] = "instruction-like customer text treated as untrusted content"

    def escalate(reason, evidence_ids=None):
        state["state"] = "escalated"
        state["escalation"] = {"reason": reason, "message_id": message_id}
        body, template_evidence = _template(recipe, _escalation_template(recipe), language, slots)
        evidence = list(dict.fromkeys((evidence_ids or []) + template_evidence))
        result_actions = [{"type": "escalate", "reason": reason}]
        if body:
            result_actions.append({"type": "send", "text": body})
        trace.update({"transition": "escalate", "policy": reason, "evidence_ids": evidence, "state_out": "escalated"})
        return {"state": state, "actions": result_actions, "trace": trace}

    if HUMAN_RX.search(text):
        return escalate("customer_requests_human")
    unknown_price = _transition_for(recipe, state.get("state"), "ask_price")
    if PRICE_RX.search(text) and unknown_price:
        return escalate("missing_price_or_availability", unknown_price.get("evidence_ids", []))
    rush_policy = _policy_for_field(recipe, "is_rush")
    if RUSH_RX.search(text) and state.get("state") != "awaiting_customer_confirmation" and rush_policy:
        return escalate(rush_policy["id"], rush_policy.get("evidence_ids", []))
    if state.get("state") in {"awaiting_deposit", "escalated"}:
        trace.update({"result": "terminal_state", "state_out": state.get("state")})
        return {"state": state, "actions": [], "trace": trace}

    new_slots = _extract_slots(recipe, text, slots)
    pending = state.get("pending_slot")
    if pending and pending not in slots and pending not in new_slots:
        value = _pending_value(pending, text)
        if value is not None and not (new_slots and pending == "quantity"):
            new_slots[pending] = value
    slots.update(new_slots)
    actions.extend({"type": "set_slot", "slot": key, "value": value} for key, value in new_slots.items())

    if state.get("state") == "awaiting_customer_confirmation" and CONFIRM_RX.search(text) and not new_slots:
        transition = _transition_for(recipe, state.get("state"), "confirm")
        if not transition:
            return escalate("unsupported_request")
        state["state"] = transition["to"]
        state["pending_slot"] = None
        body, evidence = _template(recipe, _transition_template(transition), language, slots)
        actions.append({"type": "transition_state", "to": transition["to"]})
        if body:
            actions.append({"type": "send", "text": body})
        if any(action.get("type") == "emit_owner_summary" for action in transition.get("actions", [])):
            actions.append({"type": "emit_owner_summary"})
        deposit_policy = _policy_for_field(recipe, "deposit_status")
        trace.update({"transition": transition["id"], "policy": deposit_policy.get("id") if deposit_policy else None, "evidence_ids": list(dict.fromkeys(transition.get("evidence_ids", []) + evidence)), "state_out": transition["to"]})
        return {"state": state, "actions": actions, "trace": trace}

    missing = [slot_id for slot_id in _required(recipe, slots) if slot_id not in slots]
    state["missing_required_slots"] = missing
    if missing:
        question, evidence = _prompt(recipe, missing[0], language)
        if not question:
            return escalate("unsupported_request")
        state["state"] = "collecting"
        state["last_action"] = "ask_for_slot"
        state["pending_slot"] = missing[0]
        actions.extend([{"type": "ask_for_slot", "slot": missing[0]}, {"type": "send", "text": question}])
        trace.update({"transition": None, "asked": missing[0], "evidence_ids": evidence, "state_out": "collecting"})
        return {"state": state, "actions": actions, "trace": trace}

    transition = _transition_for(recipe, state.get("state"), "place_order")
    template_id = _transition_template(transition or {})
    if not transition or not template_id:
        return escalate("unsupported_request")
    state["state"] = transition["to"]
    state["pending_slot"] = None
    state["last_action"] = "render_template"
    body, evidence = _template(recipe, template_id, language, slots)
    if not body:
        return escalate("unsupported_request")
    actions.extend([{"type": "transition_state", "to": transition["to"]}, {"type": "render_template", "template_id": template_id}, {"type": "send", "text": body}])
    trace.update({"transition": transition["id"], "evidence_ids": list(dict.fromkeys(transition.get("evidence_ids", []) + evidence)), "state_out": transition["to"]})
    return {"state": state, "actions": actions, "trace": trace}
