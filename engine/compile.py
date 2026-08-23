import hashlib
import json
import os

from engine.schema import validate_recipe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _approved_payload(recipe):
    return {key: value for key, value in recipe.items() if not key.startswith("_") and key != "recipe_version"}


def _approval_errors(recipe, approval):
    errors = []
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        errors.append("approval envelope is not approved")
        return errors
    if recipe.get("status") != "approved":
        errors.append("recipe is not owner-approved")
    if approval.get("recipe_id") != recipe.get("recipe_id"):
        errors.append("approval recipe_id does not match recipe")
    if approval.get("recipe_version") != recipe.get("recipe_version"):
        errors.append("approval recipe_version does not match recipe")
    actual_hash = _hash(_approved_payload(recipe))
    if approval.get("content_hash") != actual_hash:
        errors.append("approved content hash does not match recipe")
    return errors


def _scenarios(recipe, errors):
    global_error = any(not error.startswith(("transition:", "policy:")) for error in errors)
    scenarios = []
    for kind in ("transition", "policy"):
        for item in recipe.get(kind + "s", []):
            prefix = kind + ":" + str(item.get("id"))
            failures = [error for error in errors if error.startswith(prefix)]
            scenarios.append({
                "name": prefix,
                "passed": not global_error and not failures,
                "details": failures or ([] if not global_error else ["recipe-level validation failed"]),
            })
    return scenarios


def compile_recipe(recipe, approval):
    errors = validate_recipe(recipe, expected_status="approved") + _approval_errors(recipe, approval)
    errors = list(dict.fromkeys(errors))
    scenarios = _scenarios(recipe, errors)
    warnings = [question.get("question") for question in recipe.get("unresolved_questions", []) if question.get("question")]
    result = {
        "bundle_dir": None,
        "compile_report": {
            "status": "rejected" if errors else "compiled",
            "approved_hash": approval.get("content_hash") if isinstance(approval, dict) else None,
            "recipe_id": recipe.get("recipe_id") if isinstance(recipe, dict) else None,
            "recipe_version": recipe.get("recipe_version") if isinstance(recipe, dict) else None,
            "warnings": warnings,
            "rejected": errors,
        },
        "test_report": {
            "status": "failed" if errors or any(not item["passed"] for item in scenarios) else "passed",
            "scenarios": scenarios,
        },
    }
    if errors:
        return result

    short_hash = approval["content_hash"].split(":", 1)[-1][:12]
    bundle_dir = os.path.join(ROOT, "var", "bundles", "%s-v%s-%s" % (
        recipe["recipe_id"], recipe["recipe_version"], short_hash))
    os.makedirs(bundle_dir, exist_ok=True)
    bundle = {
        "schema_version": "resipi.bundle.v1",
        "approved_hash": approval["content_hash"],
        "recipe_id": recipe["recipe_id"],
        "recipe_version": recipe["recipe_version"],
        "recipe": recipe,
    }
    with open(os.path.join(bundle_dir, "bundle.json"), "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    result["bundle_dir"] = bundle_dir
    result["compile_report"]["bundle_hash"] = _hash(bundle)
    return result
