"""Telegram Desktop JSON export -> canonical Resipi messages.

Contract: plan section 4.1. Every history adapter must emit exactly this shape,
so the optional live-history adapter can be swapped in without touching engine/.
"""
import hashlib
import re

SOURCE = "telegram_export"

# --- redaction -------------------------------------------------------------
# Applied BEFORE anything leaves for Qwen and before anything is shown in the UI.
REDACTIONS = [
    ("email",    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("phone",    re.compile(r"(?:\+?6?0)1\d[-\s]?\d{3,4}[-\s]?\d{4}\b|\+\d{8,15}\b")),
    ("card",     re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("bank_ref", re.compile(r"\b(?:acc(?:ount)?|akaun|maybank|cimb|tng|touch\s*'?n\s*go|duitnow|ref)\W{0,3}[\w-]*\d{4,}\b", re.I)),
    ("link",     re.compile(r"https?://\S+|t\.me/\S+|wa\.me/\S+")),
    ("address",  re.compile(r"\b(?:no\.?\s*\d+[\w/-]*,?\s*)?(?:jalan|jln|lorong|lrg|taman|persiaran)\s+[\w\s./-]{2,40}(?:,?\s*\d{5})?", re.I)),
    ("postcode", re.compile(r"\b\d{5}\b(?=\s*(?:kuala|selangor|penang|johor|shah|petaling|\w+\s*,)?)", re.I)),
]


def redact(text):
    """Return (redacted_text, {kind: count}). Placeholders keep the sentence readable."""
    hits = {}
    for kind, rx in REDACTIONS:
        def sub(m):
            hits[kind] = hits.get(kind, 0) + 1
            return "[" + kind.upper() + "_REDACTED]"
        text = rx.sub(sub, text)
    return text, hits


# --- text flattening -------------------------------------------------------
def flatten_text(raw):
    """Telegram text is str | list[str | {type,text}]."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for p in raw:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                parts.append(p.get("text", ""))
        return "".join(parts)
    return ""


def _hash(value):
    return "sha256:" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:32]


def _language_hint(text):
    ms = {"nak", "boleh", "berapa", "untuk", "tarikh", "hantar", "ambil", "sahkan",
          "harga", "dulu", "ya", "tak", "sabtu", "ahad", "isnin", "deposit", "bayar", "saya"}
    low = re.findall(r"[a-z']+", text.lower())
    if not low:
        return "und"
    hits = sum(1 for w in low if w in ms)
    if hits == 0:
        return "en"
    if hits >= max(2, len(low) // 3):
        return "ms"
    return "ms-en"


def _iter_chats(doc):
    """Accept a single-chat export or a whole-account export."""
    if isinstance(doc, dict) and "messages" in doc:
        return [doc]
    if isinstance(doc, dict) and isinstance(doc.get("chats"), dict):
        return doc["chats"].get("list", [])
    if isinstance(doc, list):
        return doc
    return []


def normalize(doc, owner_ids=None, owner_names=None, max_messages=2000):
    """Telegram export document -> (canonical_messages, stats).

    owner_ids / owner_names identify the business account; everyone else becomes
    `customer`. Reactions, service events and empty messages are dropped.
    """
    owner_ids = set(owner_ids or [])
    owner_names = {n.lower() for n in (owner_names or [])}
    out = []
    stats = {"chats": 0, "raw_messages": 0, "dropped_service": 0, "dropped_empty": 0,
             "redactions": {}, "speakers": {}}

    for chat in _iter_chats(doc):
        stats["chats"] += 1
        chat_hash = _hash(chat.get("id", chat.get("name", "unknown")))
        for m in chat.get("messages", []):
            stats["raw_messages"] += 1
            if m.get("type") != "message":
                stats["dropped_service"] += 1
                continue
            text = flatten_text(m.get("text", "")).strip()
            if not text:
                stats["dropped_empty"] += 1
                continue

            sender_id = str(m.get("from_id", ""))
            sender_nm = str(m.get("from", "") or "").lower()
            is_owner = sender_id in owner_ids or sender_nm in owner_names
            speaker = "owner" if is_owner else "customer"

            clean, hits = redact(text)
            for k, v in hits.items():
                stats["redactions"][k] = stats["redactions"].get(k, 0) + v
            stats["speakers"][speaker] = stats["speakers"].get(speaker, 0) + 1

            out.append({
                "chat_id_hash": chat_hash,
                "message_id": str(m.get("id")),
                "timestamp": m.get("date"),
                "speaker": speaker,
                "text": clean,
                "language_hint": _language_hint(clean),
                "attachments": [],
                "source": SOURCE,
            })
            if len(out) >= max_messages:
                break

    out.sort(key=lambda x: (x["chat_id_hash"], x["timestamp"] or "", int(x["message_id"] or 0)))
    return out, stats


def detect_participants(doc):
    """List candidate senders so the owner can pick their own account at import."""
    seen = {}
    for chat in _iter_chats(doc):
        for m in chat.get("messages", []):
            if m.get("type") != "message":
                continue
            key = str(m.get("from_id", ""))
            if not key:
                continue
            entry = seen.setdefault(key, {"from_id": key, "name": m.get("from"), "count": 0})
            entry["count"] += 1
    return sorted(seen.values(), key=lambda e: -e["count"])
