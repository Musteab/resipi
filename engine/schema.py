ACTION_TYPES = {
    "set_slot", "ask_for_slot", "render_template", "transition_state",
    "emit_owner_summary", "escalate", "send",
}
POLICY_OPERATORS = {"equals", "not_equals", "in"}


def _ids(items):
    return {item.get("id") for item in items if isinstance(item, dict) and item.get("id")}


def _dict_items(recipe, key):
    value = recipe.get(key, [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def validate_recipe(recipe, expected_status=None):
    errors = []
    if not isinstance(recipe, dict):
        return ["recipe must be an object"]
    if recipe.get("schema_version") != "resipi.recipe.v1":
        errors.append("schema_version must be resipi.recipe.v1")
    if expected_status and recipe.get("status") != expected_status:
        errors.append("status must be %s" % expected_status)
    if not recipe.get("recipe_id"):
        errors.append("recipe_id is required")

    required_lists = ("intents", "slots", "states", "transitions", "policies", "templates", "evidence")
    for key in required_lists:
        value = recipe.get(key)
        if not isinstance(value, list):
            errors.append("%s must be a list" % key)
        elif any(not isinstance(item, dict) for item in value):
            errors.append("every %s item must be an object" % key)

    states = _ids(_dict_items(recipe, "states"))
    slots = _ids(_dict_items(recipe, "slots"))
    intents = _ids(_dict_items(recipe, "intents"))
    templates = _ids(_dict_items(recipe, "templates"))
    evidence = _ids(_dict_items(recipe, "evidence"))

    for key in required_lists:
        values = [item.get("id") for item in _dict_items(recipe, key)]
        if None in values or "" in values:
            errors.append("every %s item needs an id" % key)
        if len(values) != len(set(values)):
            errors.append("%s ids must be unique" % key)

    initial = [state for state in _dict_items(recipe, "states") if state.get("initial")]
    if len(initial) != 1:
        errors.append("exactly one initial state is required")

    for slot in _dict_items(recipe, "slots"):
        if not isinstance(slot.get("prompts"), dict) or not slot.get("prompts"):
            errors.append("slot:%s needs prompts" % slot.get("id"))
        if not isinstance(slot.get("required_for", []), list):
            errors.append("slot:%s required_for must be a list" % slot.get("id"))

    for transition in _dict_items(recipe, "transitions"):
        tid = transition.get("id")
        if transition.get("from") not in states:
            errors.append("transition:%s has unknown from state" % tid)
        if transition.get("to") not in states:
            errors.append("transition:%s has unknown to state" % tid)
        trigger = transition.get("trigger", {})
        if not isinstance(trigger, dict) or not trigger.get("intent"):
            errors.append("transition:%s needs a trigger intent" % tid)
        guards = transition.get("guards")
        if guards is not None and not isinstance(guards, dict):
            errors.append("transition:%s guards must be an object" % tid)
            guards = {}
        guarded = (guards or {}).get("all_slots_present", [])
        for slot_id in guarded if isinstance(guarded, list) else []:
            if slot_id not in slots:
                errors.append("transition:%s references unknown slot:%s" % (tid, slot_id))
        actions = transition.get("actions")
        for action in actions if isinstance(actions, list) else []:
            if not isinstance(action, dict):
                errors.append("transition:%s actions must be objects" % tid)
                continue
            action_type = action.get("type")
            if action_type not in ACTION_TYPES:
                errors.append("transition:%s has unsupported action:%s" % (tid, action_type))
            if action_type == "render_template" and action.get("template_id") not in templates:
                errors.append("transition:%s references unknown template:%s" % (tid, action.get("template_id")))

    for policy in _dict_items(recipe, "policies"):
        pid = policy.get("id")
        rule = policy.get("machine_rule", {})
        if not isinstance(rule, dict) or rule.get("operator") not in POLICY_OPERATORS:
            errors.append("policy:%s has unsupported machine rule" % pid)
        if policy.get("on_unknown") not in {"ask", "escalate", "ignore"}:
            errors.append("policy:%s has invalid on_unknown" % pid)

    for template in _dict_items(recipe, "templates"):
        variants = template.get("variants")
        if not isinstance(variants, dict) or not variants:
            errors.append("template:%s needs variants" % template.get("id"))

    for collection in ("intents", "slots", "transitions", "policies", "templates"):
        for item in _dict_items(recipe, collection):
            ids = item.get("evidence_ids")
            for evidence_id in ids if isinstance(ids, list) else []:
                if evidence_id not in evidence:
                    errors.append("%s:%s references unknown evidence:%s" % (collection[:-1], item.get("id"), evidence_id))

    for item in _dict_items(recipe, "evidence"):
        source = item.get("source")
        if not isinstance(source, dict) or not source.get("chat_id_hash") or not source.get("message_ids"):
            errors.append("evidence:%s needs source message ids" % item.get("id"))
        if not item.get("redacted_excerpt") or not item.get("supports"):
            errors.append("evidence:%s needs excerpt and supports" % item.get("id"))

    return errors
