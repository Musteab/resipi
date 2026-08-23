"""Resipi demo server - one stdlib process, three screens, one runtime seam."""
import hashlib
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from adapters.telegram_export.normalize import normalize, detect_participants  # noqa: E402
from adapters.chat_text.parse import sniff_and_parse  # noqa: E402
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
    def status(_, ns):
        imp = store.get("import", ns=ns) or {}
        cand = store.get("candidate", ns=ns)
        appr = store.get("approval", ns=ns)
        comp = store.get("compile", ns=ns)
        return {
            "import": {"messages": len(imp.get("messages", [])), "stats": imp.get("stats"), "loaded": bool(imp)},
            "candidate": bool(cand),
            "candidate_source": (cand or {}).get("_source"),
            "approval": appr,
            "compile": (comp or {}).get("compile_report"),
            "compile_source": (comp or {}).get("_source"),
            "runtime": runtime_client.RUNTIME_HERMES if runtime_client.hermes_available() else runtime_client.RUNTIME_STUB,
            "conversations": len(store.list_conversations(ns=ns)),
        }

    @staticmethod
    def participants(body, ns):
        doc = API._load_doc(body)
        return {"participants": detect_participants(doc)}

    @staticmethod
    def _records_to_doc(records, source_name):
        """Plain-text chat records -> the same document shape the JSON adapter
        emits, so there is one normalizer and one canonical output."""
        ids = {}
        msgs = []
        for i, r in enumerate(records):
            who = r["from"]
            ids.setdefault(who, "user_%d" % (len(ids) + 1))
            msgs.append({"id": 10000 + i, "type": "message", "date": r["date"],
                         "from": who, "from_id": ids[who], "text": r["text"]})
        return {"chats": {"list": [{"name": source_name, "type": "personal_chat",
                                    "id": abs(hash(source_name)) % 10**6, "messages": msgs}]}}

    @staticmethod
    def _load_doc(body):
        # Uploaded file: could be .json, .txt, .docx or .pdf
        if body.get("raw_b64"):
            import base64
            data = base64.b64decode(body["raw_b64"])
            name = body.get("filename") or ""
            if name.lower().endswith(".json") or data.lstrip()[:1] in (b"{", b"["):
                return json.loads(data.decode("utf-8", "replace"))
            records, fmt = sniff_and_parse(name, data)
            if not records:
                raise ValueError(
                    "No messages found in that file. Export the chat from WhatsApp "
                    "(Chat > Export chat > Without media) or Telegram, and upload the .txt.")
            body["_detected_format"] = fmt
            return API._records_to_doc(records, name or "Uploaded chat")
        if body.get("content"):
            return body["content"]
        p = _pick(os.path.join(FIXTURES, "telegram_history.anonymized.json"),
                  os.path.join(DEVDATA, "telegram_export.dev.json"))
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def import_history(body, ns):
        doc = API._load_doc(body)
        people = detect_participants(doc)
        owner_ids = body.get("owner_ids") or [people[0]["from_id"]]
        owner_name = next((p.get("name") for p in people if p["from_id"] in owner_ids), None)
        msgs, stats = normalize(doc, owner_ids=owner_ids)
        uploaded = bool(body.get("raw_b64") or body.get("content"))
        rec = {"messages": msgs, "stats": stats, "owner_ids": owner_ids,
               "source": "upload" if uploaded else "fixture",
               "format": body.get("_detected_format", "json" if uploaded else "fixture")}
        store.put("import", rec, ns=ns)
        store.log("import", {"count": len(msgs), "stats": stats}, ns=ns)
        return {"count": len(msgs), "stats": stats, "owner_ids": owner_ids,
                "chats": stats["chats"], "messages": msgs,
                "format": rec["format"], "owner_name": owner_name}

    @staticmethod
    def extract(_, ns):
        imp = store.get("import", ns=ns)
        if not imp:
            return {"error": "import history first"}
        cand, src = call_extract(imp["messages"])
        cand["_source"] = src
        cand["_candidate_hash"] = sha({k: v for k, v in cand.items() if not k.startswith("_")})
        store.put("candidate", cand, ns=ns)
        store.log("extract", {"source": src, "hash": cand["_candidate_hash"]}, ns=ns)
        return cand

    @staticmethod
    def candidate(_, ns):
        return store.get("candidate", ns=ns) or {"error": "no candidate"}

    @staticmethod
    def approve(body, ns):
        cand = store.get("candidate", ns=ns)
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
        prev = store.get("approval", ns=ns) or {}
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
        store.put("approved_recipe", approved, ns=ns)
        store.put("approval", approval, ns=ns)
        store.log("approve", approval, ns=ns)
        return approval

    @staticmethod
    def compile(_, ns):
        API._ensure_ready(ns)
        rec, appr = store.get("approved_recipe", ns=ns), store.get("approval", ns=ns)
        if not rec or not appr:
            return {"error": "approve a recipe first"}
        out, src = call_compile(rec, appr)
        out["_source"] = src
        store.put("compile", out, ns=ns)
        store.log("compile", {"source": src, "hash": appr["content_hash"]}, ns=ns)
        return out

    @staticmethod
    def _ensure_ready(ns):
        """Serverless instances start empty. Rebuild the demo chain on demand.

        This never fakes a result - it runs the same import/extract/approve the
        user would click. It exists so a judge landing mid-flow on a cold
        instance gets a working demo instead of "no approved recipe".
        """
        if store.get("approved_recipe", ns=ns):
            return False
        if not store.get("import", ns=ns):
            API.import_history({}, ns)
        if not store.get("candidate", ns=ns):
            API.extract({}, ns)
        API.approve({}, ns)
        return True

    @staticmethod
    def chat_send(body, ns):
        seeded = API._ensure_ready(ns)
        rec = store.get("approved_recipe", ns=ns)
        if not rec:
            return {"error": "no approved recipe - approve one first"}
        cid = body.get("conversation_id") or "sim:demo"
        state = store.load_conversation(cid, ns=ns) or {
            "conversation_id": cid, "recipe_id": rec.get("recipe_id"),
            "recipe_version": rec.get("recipe_version"), "state": "collecting",
            "detected_language": "en", "slots": {}, "missing_required_slots": [],
            "seen_message_ids": [], "last_action": None, "escalation": None,
        }
        msg = {"message_id": str(body.get("message_id") or len(state["seen_message_ids"]) + 1),
               "text": body.get("text", "")}
        out = runtime_client.recipe_step(rec, state, msg)
        store.save_conversation(cid, out["state"], ns=ns)
        store.log("turn", {"cid": cid, "in": msg, "trace": out["trace"],
                           "actions": out["actions"], "runtime": out["runtime"]}, ns=ns)
        return out

    @staticmethod
    def chat_state(body, ns):
        cid = body.get("conversation_id") or "sim:demo"
        return store.load_conversation(cid, ns=ns) or {"empty": True}

    @staticmethod
    def transcript(body, ns):
        cid = body.get("conversation_id") or "sim:demo"
        turns = [e for e in reversed(store.events(500, ns=ns)) if e["kind"] == "turn" and e["payload"]["cid"] == cid]
        return {"turns": turns}

    @staticmethod
    def orders(_, ns):
        """The owner's inbox. Every conversation that produced an order or an alert.

        `owner_status` is deliberately separate from the recipe state machine:
        the agent can never mark an order paid or confirmed. Only the owner can,
        and only from this screen.
        """
        out = []
        for c in store.list_conversations(ns=ns):
            slots = c.get("slots") or {}
            if not slots and not c.get("escalation"):
                continue
            cid = c["conversation_id"]
            channel = "Telegram" if cid.startswith("telegram:") else "Demo chat"
            owner_status = (store.get("owner_status", {}, ns=ns) or {}).get(cid)
            needs = bool(c.get("escalation")) or (c.get("state") == "awaiting_deposit" and not owner_status)
            out.append({
                "conversation_id": cid,
                "channel": channel,
                "customer": "Demo customer" if not cid.startswith("telegram:") else cid.split(":")[-1],
                "agent_state": c.get("state"),
                "owner_status": owner_status or ("Waiting for deposit" if c.get("state") == "awaiting_deposit" else None),
                "slots": slots,
                "escalation": c.get("escalation"),
                "language": c.get("detected_language"),
                "needs_you": needs,
            })
        out.sort(key=lambda o: (not o["needs_you"],))
        return {"orders": out,
                "waiting": sum(1 for o in out if o["needs_you"]),
                "total": len(out)}

    @staticmethod
    def order_action(body, ns):
        """Owner-only actions. The agent has no path to any of these."""
        cid, action = body.get("conversation_id"), body.get("action")
        statuses = store.get("owner_status", {}, ns=ns) or {}
        label = {"deposit_received": "Deposit received - confirmed",
                 "cancelled": "Cancelled by owner",
                 "handled": "Handled by owner"}.get(action)
        if not label or not cid:
            return {"error": "unknown action"}
        statuses[cid] = label
        store.put("owner_status", statuses, ns=ns)
        store.log("owner_action", {"cid": cid, "action": action}, ns=ns)
        return {"ok": True, "conversation_id": cid, "owner_status": label}

    @staticmethod
    def result_card(_, ns):
        """Computed from stored artifacts only. Never hand-written numbers."""
        imp = store.get("import", ns=ns) or {}
        cand = store.get("candidate", ns=ns) or {}
        appr = store.get("approval", ns=ns)
        comp = store.get("compile", ns=ns) or {}
        convs = store.list_conversations(ns=ns)
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
    def events(_, ns):
        return {"events": store.events(100, ns=ns)}

    @staticmethod
    def reset(_, ns):
        store.reset(ns)
        store.log("reset", {}, ns=ns)
        return {"ok": True}


ROUTES = {
    "/api/status": API.status, "/api/participants": API.participants,
    "/api/import": API.import_history, "/api/extract": API.extract,
    "/api/candidate": API.candidate, "/api/approve": API.approve,
    "/api/compile": API.compile, "/api/chat/send": API.chat_send,
    "/api/chat/state": API.chat_state, "/api/chat/transcript": API.transcript,
    "/api/result-card": API.result_card,
    "/api/orders": API.orders, "/api/orders/action": API.order_action, "/api/events": API.events,
    "/api/reset": API.reset,
}


class Handler(BaseHTTPRequestHandler):
    """Local transport. All routing/session/static logic lives in app.core."""

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _serve(self):
        from app.core import dispatch
        n = int(self.headers.get("Content-Length") or 0)
        body_in = self.rfile.read(n) if n else b""
        status, headers, body = dispatch(
            self.command, urlparse(self.path).path, body_in, self.headers.get("Cookie", ""))
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v.replace("; Secure", "") if k == "Set-Cookie" else v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _serve
    do_POST = _serve


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8420"))
    # 0.0.0.0 so this runs behind a PaaS/tunnel as well as locally.
    host = os.environ.get("HOST", "0.0.0.0")
    print("Resipi demo on http://%s:%d  (runtime: %s)" % (
        host, port, "hermes" if runtime_client.hermes_available() else "local-stub"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()
