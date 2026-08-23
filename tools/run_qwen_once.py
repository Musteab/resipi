"""Run the real Qwen extraction once, save the raw response, then validate.

Separating capture from validation means one slow call yields both the artifact
and a diagnosis if validation fails. Does not modify engine/extract.py.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.telegram_export.normalize import normalize
from engine import extract as ex

doc = json.load(open("fixtures/telegram_history.anonymized.json", encoding="utf-8"))
msgs, _ = normalize(doc, owner_ids=["user1000"])
key = os.environ["MODELSCOPE_API_KEY"]

t = time.time()
raw, model = ex._request_qwen(msgs, key, ex.DEFAULT_BASE_URL,
                              os.environ.get("QWEN_MODEL", ex.DEFAULT_MODEL))
print("qwen responded in %.0fs (model %s)" % (time.time() - t, model))

with open("artifacts/qwen_raw_response.json", "w", encoding="utf-8") as f:
    json.dump(raw, f, indent=2, ensure_ascii=False)
print("raw saved -> artifacts/qwen_raw_response.json")

print("top-level keys:", list(raw) if isinstance(raw, dict) else "NOT A DICT: " + type(raw).__name__)
for k, v in (raw.items() if isinstance(raw, dict) else []):
    if isinstance(v, list) and v:
        bad = [i for i, item in enumerate(v) if not isinstance(item, dict)]
        if bad:
            print("  !! %s has non-dict entries at %s -> %r" % (k, bad[:3], v[bad[0]])[:200])

errs = ex.validate_recipe(raw, expected_status="needs_owner_review")
print("schema errors:", errs if errs else "none")
