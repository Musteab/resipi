# Resipi — A Conversation-to-Workflow Compiler for Micro-Businesses

Resipi reverse-engineers a business process from historical conversations and compiles its
evidence-backed, owner-approved rules into a persistent Hermes agent.

**This is not a generic chatbot.** The owner never writes a bot prompt or configures a CRM
workflow. Qwen discovers an evidence-backed state machine from past chats, the owner approves
it, Devin's compiler makes it executable and tests it, and Hermes runs only that approved version.

## Problem statement

Micro-businesses are not a niche in Malaysia — they *are* the economy. Microenterprises make
up 69.7% of the country's 1.1 million MSMEs (SME Corp Malaysia / DOSM, Economic Census 2023),
and MSMEs overall contribute 39.1% of GDP. A large share of these are home bakers, tailors,
and home-based F&B sellers who have no storefront, no POS system, and no CRM — their entire
sales process is a phone. Meta's 2024 Kantar-commissioned Business Messaging Usage Research
found that ~80% of Malaysians message a business at least once a week and 7 in 10 prefer
messaging over calling or emailing, so this isn't a workaround, it's the primary sales
channel. Every order for these sellers starts as a WhatsApp/Telegram DM, manually triaged by
one person. This doesn't scale — the owner ends up re-answering the same pricing and
availability questions all day, every day, with no one to hand it off to.

Generic chatbot builders don't help this segment because they require the owner to sit down
and author a flow from scratch — a skill and a time investment most solo sellers don't have.
Plugging in a raw LLM is actively dangerous: it will happily invent prices, delivery dates,
or fake payment confirmations it was never told, and a single hallucinated promise can cost a
one-person business its reputation. Meanwhile, the business's real rules already exist —
buried in months of past chats — nobody has extracted them. Our target user is this solo
Malaysian micro-seller: technically unsophisticated, time-poor, message-first, and currently
choosing between "answer everything myself forever" and "risk an AI that lies to my
customers." The core problem: how do you turn a business's own conversation history into an
automation the owner can trust, without asking them to write a single rule, and without
letting a model invent facts?

## Solution

Resipi is a conversation-to-workflow compiler purpose-built for this seller: instead of
asking them to design a bot, it reverse-engineers the bot from work they've already done —
their own chat history. It imports a business's real Telegram history, uses Qwen to learn an
evidence-backed workflow (every rule cites the exact message it came from), and shows the
owner each rule next to its source chat so they can disable anything before approving an
immutable, hashed version. Only approved recipes ever run. At runtime, a deterministic state
machine — not the LLM — decides what happens next (which field to ask for, when to escalate a
rush order or price question to the human owner); the Hermes Agent (Qwen-backed) is only ever
used to phrase that already-decided action naturally in the customer's own language (including
Malaysian English/Bahasa code-switching, as seen in the demo), so it can never invent a
business fact. All customer conversations happen through a Telegram bot — the channel these
sellers already live in — with a read-only admin dashboard letting the seller watch every
conversation and step in the moment the system escalates to them.

This directly targets the two failure modes of every alternative available to a Malaysian
micro-seller today: manual DM triage (doesn't scale, burns out the owner) and generic/raw-LLM
chatbots (require setup expertise they don't have, and can hallucinate facts that damage
trust with customers). Resipi needs neither — it needs only what the owner already has: past
chats.

### Why this vs. existing options (novelty & impact)

- **vs. manual DM handling:** removes the single biggest time sink for solo sellers without
  removing them from the loop — they approve every rule and can still step in on escalation.
- **vs. generic chatbot builders (e.g. WhatsApp Business quick replies, Manychat):** zero
  flow-building. The workflow is *learned*, not authored, so there's no blank-canvas problem
  for a non-technical seller.
- **vs. raw LLM / "just prompt ChatGPT" bots:** facts are separated from phrasing. A
  deterministic, hashed, owner-approved recipe decides *what* happens; the LLM only decides
  *how to say it*. This is the difference between "an AI that might invent a price" and "an
  AI that can never invent a price" — the core trust gap blocking AI adoption among small
  sellers.
- **Distribution path:** because it rides on Telegram/WhatsApp-style messaging that ~80% of
  Malaysians already use weekly to talk to businesses, there's no new app for either the
  seller or their customers to install.

### Next steps: adoption, scaling, sustainability

- **Adoption:** onboard via existing micro-seller communities (e.g. home-baker/F&B WhatsApp
  and Facebook groups, pasar malam/night-market vendor associations) where a single successful
  seller's recipe becomes the referral; add a WhatsApp Business API adapter alongside the
  Telegram adapter, since WhatsApp is the dominant channel for this segment; pursue SME Corp
  Malaysia digitalisation grant programmes (e.g. PENJANA/PSGS-style matching grants) that
  already fund POS/CRM adoption for micro-businesses, as a channel to reach and subsidize
  first users.
- **Scaling:** the compiler/runtime split (deterministic recipe engine + swappable LLM phrasing
  layer) is business-agnostic — the same architecture generalizes past F&B/tailoring to any
  DM-first service business (tuition, home services, small retail) by re-running Learn on that
  business's own history, with no core engine changes.
- **Sustainability:** a usage-based or flat monthly SaaS fee per approved recipe is viable once
  a seller has seen the time saved; margins are healthy because the expensive step (Learn) runs
  once per recipe version, not per customer message, and the per-message cost (Hermes phrasing
  only) is small and bounded by the deterministic runtime.
- **Trust & safety runway:** because every rule is evidence-linked and versioned/hashed, future
  work can add owner-facing analytics (which rules fire most, where customers still get
  escalated) to keep closing the gap between "what the recipe covers" and "what customers ask."

## Run

```bash
python3 app/server.py     # http://127.0.0.1:8420 — no dependencies, stdlib only
```

Three screens: **Import history → Review recipe → Admin dashboard.**
There is no in-app chat simulator — every customer conversation happens over the
Telegram bot adapter, and the Admin dashboard is a read-only view onto those
conversations for the seller. `demo/reset.sh` returns the demo to zero.

## Hermes Agent Docker

Resipi keeps **Learn** mocked from the saved candidate. Customer-facing replies, sent to real customers over the **Telegram bot**, use the OpenAI-compatible API from `nousresearch/hermes-agent:latest`; the approved recipe runtime still controls state, required fields, and escalation.

Run the Hermes setup wizard once if `$HOME/.hermes` is not configured:

```bash
mkdir -p "$HOME/.hermes"
docker run -it --rm \
  -v "$HOME/.hermes:/opt/data" \
  nousresearch/hermes-agent:latest setup
```

Choose a Qwen provider and model during setup. To change it later:

```bash
docker compose -f compose.hermes.yaml run --rm hermes model
```

Hermes requires an API server key. Confirm setup created one without printing it:

```bash
set -a
source "$HOME/.hermes/.env"
set +a
[ -n "$API_SERVER_KEY" ] && echo "Hermes API key is set" || echo "Run Hermes setup again"
```

If an existing container named `hermes` is using port 8642, stop it first. Its persisted `$HOME/.hermes` data is unchanged:

```bash
docker stop hermes
docker compose -f compose.hermes.yaml up -d
```

The Compose service publishes Hermes only on host loopback at `http://127.0.0.1:8642`. Verify model discovery:

```bash
curl http://127.0.0.1:8642/v1/models \
  -H "Authorization: Bearer $API_SERVER_KEY"
```

Start Resipi from the same shell so it can authenticate to Hermes:

```bash
export HERMES_BASE_URL=http://127.0.0.1:8642/v1
export HERMES_API_KEY="$API_SERVER_KEY"
python3 app/server.py
```

Open `http://127.0.0.1:8420`. The runtime badge should show `hermes-qwen`. Import the fixture, analyze the mocked learning result, approve and compile it, then message the Telegram bot as a customer and watch the turn show up in the **Admin dashboard**. If the badge says `local-stub`, inspect the container with:

```bash
docker compose -f compose.hermes.yaml ps
docker compose -f compose.hermes.yaml logs --tail=100 hermes
```

Stop the integration with `docker compose -f compose.hermes.yaml down`. If you stopped a previous `hermes` container, restore it with `docker start hermes` after the Compose service is down.

Hermes Agent's API profile can expose terminal, file, web, memory, and other tools. Customer messages are untrusted, so keep port 8642 loopback-only and use `hermes tools` to disable tools that the `api_server` platform does not need. For production, use a dedicated Hermes profile rather than your personal agent profile.

Telegram bot for customer chats — this is the **only** way a conversation reaches the
approved recipe runtime; there is no chat simulator in the app itself:

```bash
TELEGRAM_BOT_TOKEN=... python3 adapters/telegram_bot/poll.py
```

Every turn the bot handles is persisted and shows up immediately in the app's
**Admin dashboard** screen, so the seller can watch conversations without ever
being able to type a reply on the customer's behalf.

## Honesty about fallbacks

Every screen badges which path produced it. `runtime: local-stub` means the local recipe runtime
or Hermes Agent API is unavailable. `runtime: hermes-qwen` means the approved runtime chose the
action and Hermes Agent generated the reply. `cached` on the recipe means the candidate is a saved
result for the displayed input, not a live model call.
Nothing labelled live is cached.

See `HANDOFF.md` for the three seams into the engine/Hermes lane.
