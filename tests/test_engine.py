import copy
import io
import json
import os
import unittest
from unittest.mock import patch

from adapters.telegram_export.normalize import normalize
from engine.compile import _hash, compile_recipe
from engine.extract import DEFAULT_BASE_URL, DEFAULT_MODEL, _stream_completion, extract_candidate
from engine.schema import validate_recipe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    with open(os.path.join(ROOT, "app", "devdata", name), encoding="utf-8") as handle:
        return json.load(handle)


def approved_pair():
    recipe = load("recipe_candidate.dev.json")
    recipe["status"] = "approved"
    core = {key: value for key, value in recipe.items() if not key.startswith("_")}
    approval = {
        "recipe_id": recipe["recipe_id"],
        "recipe_version": 1,
        "content_hash": _hash(core),
        "status": "approved",
    }
    recipe["recipe_version"] = 1
    return recipe, approval


class SchemaTests(unittest.TestCase):
    def test_dev_candidate_is_schema_valid(self):
        self.assertEqual([], validate_recipe(load("recipe_candidate.dev.json"), "needs_owner_review"))

    def test_shared_fixture_is_schema_valid_and_resolves_evidence(self):
        with open(os.path.join(ROOT, "fixtures", "qwen_recipe_candidate.json"), encoding="utf-8") as handle:
            candidate = json.load(handle)
        with open(os.path.join(ROOT, "fixtures", "telegram_history.anonymized.json"), encoding="utf-8") as handle:
            history = json.load(handle)
        messages, _ = normalize(history, owner_ids=["user1000"])
        message_ids = {message["message_id"] for message in messages}
        evidence_ids = {str(message_id) for evidence in candidate["evidence"] for message_id in evidence["source"]["message_ids"]}
        self.assertEqual([], validate_recipe(candidate, "needs_owner_review"))
        self.assertTrue(evidence_ids <= message_ids)

    def test_stream_completion_assembles_openai_events(self):
        events = [
            {"model": "qwen-stream", "choices": [{"delta": {"content": "{\"ok\":"}}]},
            {"model": "qwen-stream", "choices": [{"delta": {"content": "true}"}}]},
        ]
        payload = "".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"
        result, model = _stream_completion(io.BytesIO(payload.encode()), "fallback")
        self.assertEqual({"ok": True}, result)
        self.assertEqual("qwen-stream", model)

    def test_live_extract_validates_qwen_result_and_evidence(self):
        history = load("telegram_export.dev.json")
        messages, _ = normalize(history, owner_ids=["user1000"])
        candidate = load("recipe_candidate.dev.json")
        with patch.dict(os.environ, {"MODELSCOPE_API_KEY": "test"}, clear=True), patch(
            "engine.extract._request_qwen", return_value=(candidate, "qwen-test")
        ) as request:
            result = extract_candidate(messages)
        self.assertTrue(result["_provenance"]["is_live_model_output"])
        self.assertEqual("qwen-test", result["_provenance"]["model"])
        self.assertEqual((messages, "test", DEFAULT_BASE_URL, DEFAULT_MODEL), request.call_args.args)

    def test_live_extract_rejects_unknown_evidence_message(self):
        history = load("telegram_export.dev.json")
        messages, _ = normalize(history, owner_ids=["user1000"])
        candidate = load("recipe_candidate.dev.json")
        candidate["evidence"][0]["source"]["message_ids"] = ["missing"]
        with patch.dict(os.environ, {"MODELSCOPE_API_KEY": "test"}, clear=False), patch(
            "engine.extract._request_qwen", return_value=(candidate, "qwen-test")
        ):
            with self.assertRaisesRegex(ValueError, "do not exist"):
                extract_candidate(messages)


class CompilerTests(unittest.TestCase):
    def test_compiles_only_hash_locked_approval(self):
        recipe, approval = approved_pair()
        result = compile_recipe(recipe, approval)
        self.assertEqual("compiled", result["compile_report"]["status"])
        self.assertEqual("passed", result["test_report"]["status"])
        self.assertTrue(all(item["passed"] for item in result["test_report"]["scenarios"]))
        self.assertTrue(os.path.isfile(os.path.join(result["bundle_dir"], "bundle.json")))

    def test_rejects_recipe_changed_after_approval(self):
        recipe, approval = approved_pair()
        changed = copy.deepcopy(recipe)
        changed["templates"][0]["variants"]["en"] = "Changed after approval"
        result = compile_recipe(changed, approval)
        self.assertEqual("rejected", result["compile_report"]["status"])
        self.assertIn("approved content hash does not match recipe", result["compile_report"]["rejected"])


if __name__ == "__main__":
    unittest.main()
