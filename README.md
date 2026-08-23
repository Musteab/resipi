# Resipi — A Conversation-to-Workflow Compiler for Micro-Businesses

Resipi reverse-engineers a business process from historical conversations and compiles its
evidence-backed, owner-approved rules into a persistent Hermes agent.

**This is not a generic chatbot.** The owner never writes a bot prompt or configures a CRM
workflow. Qwen discovers an evidence-backed state machine from past chats, the owner approves
it, Devin's compiler makes it executable and tests it, and Hermes runs only that approved version.

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
