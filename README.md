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

Three screens: **Import history → Review recipe → Live conversation.**
`demo/reset.sh` returns the demo to zero.

Telegram bot for new customer chats (optional):

```bash
TELEGRAM_BOT_TOKEN=... python3 adapters/telegram_bot/poll.py
```

## Honesty about fallbacks

Every screen badges which path produced it. `runtime: local-stub` means the Hermes runtime is
not installed and a deterministic walker ran through the same entry point. `cached` on the
recipe means the candidate is a saved result for the displayed input, not a live model call.
Nothing labelled live is cached.

See `HANDOFF.md` for the three seams into the engine/Hermes lane.
