"""Resipi demo server - one stdlib process, three screens, one runtime seam."""
import hashlib
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from adapters.telegram_export.normalize import normalize, detect_participants  # noqa: E402
from app import store, runtime_client  # noqa: E402

STATIC = os.path.join(ROOT, "app", "static")
DEVDATA = os.path.join(ROOT, "app", "devdata")
FIXTURES = os.path.join(ROOT, "fixtures")


def sha(obj):
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _pick(*paths):
    """Prefer Colin's shared fixture once it exists; fall back to the app-lane dev copy."""
    for p in paths:
        if os.path.exists(p):
            return p
    return None


# --- seams to engine/ (Colin's lane) --------------------------------------
def _cached_candidate(reason):
    p = _pick(os.path.join(FIXTURES, "qwen_recipe_candidate.json"),
              os.path.join(DEVDATA, "recipe_candidate.dev.json"))
    with open(p, encoding="utf-8") as f:
        cand = json.load(f)
    cand["_fallback_reason"] = reason
    return cand, "cached"


def call_extract(messages):
    """Qwen extraction. Falls back to a saved candidate, labelled with the REAL reason.

    The reason is surfaced in the UI verbatim: "not installed" and "no API key"
    and "the live call failed" are different claims and must not look alike.
    """
    try:
        from engine.extract import extract_candidate
    except ImportError as e:
        return _cached_candidate("engine.extract is not installed (%s)" % e)
    try:
        cand = extract_candidate(messages)
    except Exception as e:
        return _cached_candidate("%s: %s" % (type(e).__name__, e))
    cand.setdefault("_provenance", {})["is_live_model_output"] = True
    return cand, "qwen"


def call_compile(recipe, approval):
    """Devin-built compiler. Falls back to a labelled placeholder report."""
    try:
        from engine.compile import compile_recipe
    except ImportError as e:
        reason = "engine.compile is not installed (%s)" % e
    else:
        try:
            return compile_recipe(recipe, approval), "devin"
        except Exception as e:
            reason = "%s: %s" % (type(e).__name__, e)
    if True:
        scenarios = ([{"name": "transition:" + t["id"], "passed": None} for t in recipe.get("transitions", [])] +
                     [{"name": "policy:" + p["id"], "passed": None} for p in recipe.get("policies", [])])
        return {
            "compile_report": {"status": "not_compiled", "reason": reason,
                               "approved_hash": approval.get("content_hash"), "warnings": [], "rejected": []},
            "test_report": {"status": "pending", "scenarios": scenarios,
                            "note": "Scenario names are derived from the approved recipe. Pass/fail comes from the Devin-built compiler."},
        }, "pending"


# --- API ------------------------------------------------------------------
class API:
    @staticmethod
    def status(_):
        imp = store.get("import") or {}
        cand = store.get("candidate")
        appr = store.get("approval")
        comp = store.get("compile")
        return {
            "import": {"messages": len(imp.get("messages", [])), "stats": imp.get("stats"), "loaded": bool(imp)},
            "candidate": bool(cand),
            "candidate_source": (cand or {}).get("_source"),
            "approval": appr,
            "compile": (comp or {}).get("compile_report"),
            "compile_source": (comp or {}).get("_source"),
            "runtime": runtime_client.RUNTIME_HERMES if runtime_client.hermes_available() else runtime_client.RUNTIME_STUB,
            "conversations": len(store.list_conversations()),
        }

    @staticmethod
    def participants(body):
        doc = API._load_doc(body)
        return {"participants": detect_participants(doc)}

    @staticmethod
    def _load_doc(body):
        if body.get("content"):
            return body["content"]
        p = _pick(os.path.join(FIXTURES, "telegram_history.anonymized.json"),
                  os.path.join(DEVDATA, "telegram_export.dev.json"))
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def import_history(body):
        doc = API._load_doc(body)
        owner_ids = body.get("owner_ids") or [detect_participants(doc)[0]["from_id"]]
        msgs, stats = normalize(doc, owner_ids=owner_ids)
        rec = {"messages": msgs, "stats": stats, "owner_ids": owner_ids,
               "source": "upload" if body.get("content") else "fixture"}
        store.put("import", rec)
        store.log("import", {"count": len(msgs), "stats": stats})
        return {"count": len(msgs), "stats": stats, "owner_ids": owner_ids,
                "chats": stats["chats"], "messages": msgs}

    @staticmethod
    def extract(_):
        imp = store.get("import")
        if not imp:
            return {"error": "import history first"}
        cand, src = call_extract(imp["messages"])
        cand["_source"] = src
        cand["_candidate_hash"] = sha({k: v for k, v in cand.items() if not k.startswith("_")})
        store.put("candidate", cand)
        store.log("extract", {"source": src, "hash": cand["_candidate_hash"]})
        return cand

    @staticmethod
    def candidate(_):
        return store.get("candidate") or {"error": "no candidate"}

    @staticmethod
    def approve(body):
        cand = store.get("candidate")
        if not cand:
            return {"error": "no candidate to approve"}
        disabled = set(body.get("disabled_rules") or [])
        approved = json.loads(json.dumps(cand))
        edits = []
        for key in ("policies", "transitions"):
            keep = []
            for item in approved.get(key, []):
                if key[:-1] + ":" + item["id"] in disabled or item["id"] in disabled:
                    edits.append({"action": "disabled", "target": key[:-1] + ":" + item["id"]})
                else:
                    keep.append(item)
            approved[key] = keep
        approved["status"] = "approved"
        core = {k: v for k, v in approved.items() if not k.startswith("_")}
        prev = store.get("approval") or {}
        approval = {
            "recipe_id": approved.get("recipe_id"),
            "recipe_version": prev.get("recipe_version", 0) + 1,
            "approved_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
            "approved_by": "demo_owner",
            "content_hash": sha(core),
            "source_candidate_hash": cand.get("_candidate_hash"),
            "owner_edits": edits,
            "status": "approved",
        }
        approved["recipe_version"] = approval["recipe_version"]
        store.put("approved_recipe", approved)
        store.put("approval", approval)
        store.log("approve", approval)
        return approval

    @staticmethod
    def compile(_):
        rec, appr = store.get("approved_recipe"), store.get("approval")
        if not rec or not appr:
            return {"error": "approve a recipe first"}
        out, src = call_compile(rec, appr)
        out["_source"] = src
        store.put("compile", out)
        store.log("compile", {"source": src, "hash": appr["content_hash"]})
        return out

    @staticmethod
    def chat_send(body):
        rec = store.get("approved_recipe")
        if not rec:
            return {"error": "no approved recipe - approve one first"}
        cid = body.get("conversation_id") or "sim:demo"
        state = store.load_conversation(cid) or {
            "conversation_id": cid, "recipe_id": rec.get("recipe_id"),
            "recipe_version": rec.get("recipe_version"), "state": "collecting",
            "detected_language": "en", "slots": {}, "missing_required_slots": [],
            "seen_message_ids": [], "last_action": None, "escalation": None,
        }
        msg = {"message_id": str(body.get("message_id") or len(state["seen_message_ids"]) + 1),
               "text": body.get("text", "")}
        out = runtime_client.recipe_step(rec, state, msg)
        store.save_conversation(cid, out["state"])
        store.log("turn", {"cid": cid, "in": msg, "trace": out["trace"],
                           "actions": out["actions"], "runtime": out["runtime"]})
        return out

    @staticmethod
    def chat_state(body):
        cid = body.get("conversation_id") or "sim:demo"
        return store.load_conversation(cid) or {"empty": True}

    @staticmethod
    def transcript(body):
        cid = body.get("conversation_id") or "sim:demo"
        turns = [e for e in reversed(store.events(500)) if e["kind"] == "turn" and e["payload"]["cid"] == cid]
        return {"turns": turns}

    @staticmethod
    def result_card(_):
        """Computed from stored artifacts only. Never hand-written numbers."""
        imp = store.get("import") or {}
        cand = store.get("candidate") or {}
        appr = store.get("approval")
        comp = store.get("compile") or {}
        convs = store.list_conversations()
        rules = len(cand.get("policies", [])) + len(cand.get("transitions", []))
        confs = [p.get("confidence", 0) for p in cand.get("policies", [])]
        scen = comp.get("test_report", {}).get("scenarios", [])
        return {
            "input": {"conversations": imp.get("stats", {}).get("chats", 0),
                      "messages": len(imp.get("messages", []))},
            "discovered": {"stages": len(cand.get("states", [])),
                           "required_fields": len([s for s in cand.get("slots", []) if s.get("required_for")]),
                           "evidence_backed_rules": rules,
                           "unresolved_questions": len(cand.get("unresolved_questions", [])),
                           "mean_policy_confidence": round(sum(confs) / len(confs), 2) if confs else None},
            "owner_control": {"approved": bool(appr),
                              "edits": len((appr or {}).get("owner_edits", [])),
                              "version": (appr or {}).get("recipe_version"),
                              "hash": ((appr or {}).get("content_hash") or "")[7:19]},
            "validation": {"scenarios_total": len(scen),
                           "scenarios_passed": sum(1 for s in scen if s.get("passed") is True),
                           "conversations_handled": len(convs),
                           "escalations": sum(1 for c in convs if c.get("escalation"))},
        }

    @staticmethod
    def events(_):
        return {"events": store.events(100)}

    @staticmethod
    def reset(_):
        store.reset()
        store.log("reset", {})
        return {"ok": True}


ROUTES = {
    "/api/status": API.status, "/api/participants": API.participants,
    "/api/import": API.import_history, "/api/extract": API.extract,
    "/api/candidate": API.candidate, "/api/approve": API.approve,
    "/api/compile": API.compile, "/api/chat/send": API.chat_send,
    "/api/chat/state": API.chat_state, "/api/chat/transcript": API.transcript,
    "/api/result-card": API.result_card, "/api/events": API.events,
    "/api/reset": API.reset,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ROUTES:
            return self._handle(path, {})
        rel = "index.html" if path == "/" else path.lstrip("/")
        fp = os.path.normpath(os.path.join(STATIC, rel))
        if not fp.startswith(STATIC) or not os.path.isfile(fp):
            return self._send(404, {"error": "not found"})
        ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css",
                 "json": "application/json"}.get(fp.rsplit(".", 1)[-1], "text/plain")
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype + "; charset=utf-8")

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        self._handle(path, body)

    def _handle(self, path, body):
        fn = ROUTES.get(path)
        if not fn:
            return self._send(404, {"error": "no route " + path})
        try:
            self._send(200, fn(body))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send(500, {"error": type(e).__name__ + ": " + str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8420"))
    print("Resipi demo on http://127.0.0.1:%d  (runtime: %s)" % (
        port, "hermes" if runtime_client.hermes_available() else "local-stub"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
