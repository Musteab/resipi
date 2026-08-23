"""Parse whatever chat export the owner actually has.

Real micro-business owners do not produce Telegram Desktop JSON. They tap
"Export chat" in WhatsApp and get a .txt, or they paste messages into a Word
doc, or they send a PDF. This module accepts all of those and emits the same
{date, from, text} records the JSON adapter produces, so engine/ never learns
there was more than one input format.

Stdlib only - .docx is a zip of XML, .pdf text is extracted best-effort.
"""
import io
import re
import zipfile

# WhatsApp Android:  12/08/2026, 09:13 - Aina: text
# WhatsApp iOS:      [12/08/2026, 09:13:00] Aina: text
# Telegram .txt:     [20.08.2026 09:13] Aina: text
# Telegram "name, [date]" style is handled by the multiline branch below.
LINE_PATTERNS = [
    re.compile(r"^\[?(?P<d>\d{1,4}[/.\-]\d{1,2}[/.\-]\d{2,4}),?\s+"
               r"(?P<t>\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp]\.?[Mm]\.?)?)\]?\s*[-–]?\s*"
               r"(?P<who>[^:]{1,60}?):\s(?P<msg>.*)$"),
]
# Telegram desktop text export puts the header on its own line:
#   Aina, [20/08/2026 09:13]
#   Hi kak, nak order...
HEADER_PATTERN = re.compile(
    r"^(?P<who>[^,\[]{1,60}),\s*\[(?P<d>\d{1,4}[/.\-]\d{1,2}[/.\-]\d{2,4})\s+"
    r"(?P<t>\d{1,2}:\d{2}(?::\d{2})?)\]\s*$")

# Lines WhatsApp inserts that are not conversation.
NOISE = re.compile(
    r"(messages and calls are end-to-end encrypted|"
    r"<media omitted>|image omitted|video omitted|sticker omitted|audio omitted|"
    r"this message was deleted|you deleted this message|"
    r"changed the subject|changed this group's icon|created group|"
    r"joined using this group's invite link|left$|added you)", re.I)


def _norm_date(d, t):
    """Best-effort ISO-ish timestamp. Ambiguous D/M vs M/D is resolved as D/M
    (Malaysian convention); exact dates are not used for any business rule."""
    d = d.replace(".", "/").replace("-", "/")
    parts = [p for p in d.split("/") if p]
    if len(parts) != 3:
        return None
    if len(parts[0]) == 4:
        y, m, day = parts
    else:
        day, m, y = parts
        if len(y) == 2:
            y = "20" + y
    t = t.strip().lower()
    ampm = "pm" if "pm" in t else ("am" if "am" in t else None)
    t = re.sub(r"[ap]\.?m\.?", "", t).strip()
    bits = (t.split(":") + ["00", "00"])[:3]
    try:
        hh = int(bits[0])
    except ValueError:
        return None
    if ampm == "pm" and hh < 12:
        hh += 12
    if ampm == "am" and hh == 12:
        hh = 0
    return "%s-%02d-%02dT%02d:%02d:%02d" % (y, int(m), int(day), hh, int(bits[1]), int(bits[2]))


def parse_text(raw):
    """Plain-text chat export -> [{date, from, text}]. Continuation lines are
    appended to the message above them, which is how multi-line messages export."""
    out = []
    for line in raw.replace(" ", " ").replace("‎", "").splitlines():
        line = line.rstrip()
        if not line.strip():
            continue

        header = HEADER_PATTERN.match(line.strip())
        if header:
            out.append({"date": _norm_date(header["d"], header["t"]),
                        "from": header["who"].strip(), "text": ""})
            continue

        matched = None
        for rx in LINE_PATTERNS:
            m = rx.match(line.strip())
            if m:
                matched = m
                break
        if matched:
            if NOISE.search(matched["msg"]):
                continue
            out.append({"date": _norm_date(matched["d"], matched["t"]),
                        "from": matched["who"].strip(), "text": matched["msg"].strip()})
        elif out and not NOISE.search(line):
            out[-1]["text"] = (out[-1]["text"] + "\n" + line.strip()).strip()

    return [m for m in out if m["text"] and not NOISE.search(m["text"])]


def docx_to_text(data):
    """.docx is a zip; the document body is word/document.xml."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    return re.sub(r"<[^>]+>", "", xml)


def pdf_to_text(data):
    """Best-effort PDF text: pull literals out of uncompressed content streams."""
    import zlib
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        blob = m.group(1)
        try:
            blob = zlib.decompress(blob)
        except Exception:
            pass
        for t in re.finditer(rb"\((?:\\.|[^\\()])*\)", blob):
            s = t.group(0)[1:-1]
            chunks.append(re.sub(rb"\\([()\\])", rb"\1", s).decode("utf-8", "replace"))
        if re.search(rb"T[Jj]", blob):
            chunks.append("\n")
    text = "".join(chunks)
    if len(text.strip()) < 40:
        raise ValueError("Could not read text from this PDF. It is most likely a scan or an "
                         "image. Export the chat as .txt from WhatsApp instead.")
    return text


def sniff_and_parse(filename, data):
    """(filename, bytes) -> ([{date,from,text}], detected_format)."""
    name = (filename or "").lower()
    if name.endswith(".docx") or data[:2] == b"PK":
        return parse_text(docx_to_text(data)), "docx"
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        return parse_text(pdf_to_text(data)), "pdf"
    return parse_text(data.decode("utf-8", "replace")), "txt"
