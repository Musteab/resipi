# Resipi Demo Guide

This demo starts with an anonymized Telegram history, turns it into an owner-approved Business Recipe, and then uses that recipe to handle a new customer conversation through the Telegram bot.

## Before the demo

You need:

- Python 3
- A Telegram bot token in `TELEGRAM_BOT_TOKEN`
- The Telegram username of the bot created with BotFather
- Two terminal windows

Run every command below from the repository root:

```bash
cd /Users/colinleong/Downloads/Resipi/repo
```

If the token is stored in `.env`, load it into each terminal that runs the bot:

```bash
set -a
source .env
set +a
```

The application does not load `.env` automatically. If the token was already exported by your shell or IDE, you can skip that command. Confirm that it is available without printing the secret:

```bash
[ -n "$TELEGRAM_BOT_TOKEN" ] && echo "Telegram token is set" || echo "Telegram token is missing"
```

Optionally restrict the destructive `/reset` bot command to your numeric Telegram user ID:

```bash
export TELEGRAM_ALLOWED_USER_IDS="123456789"
```

## Step 1: Reset the demo

Start from a clean state:

```bash
./demo/reset.sh
```

Expected output:

```text
reset by removing var/resipi.db
```

If the web server is already running, the output will instead say `reset via running server`.

## Step 2: Start the Resipi app

In terminal 1, run:

```bash
python3 app/server.py
```

Expected output includes:

```text
Resipi demo on http://127.0.0.1:8420  (runtime: hermes)
```

Keep this terminal running. Open <http://127.0.0.1:8420> in a browser.

## Step 3: Import the historical chats

On the **Import history** screen:

1. Click **Load anonymized export**.
2. Point out that service events are removed, speakers are normalized, and identifiers are redacted.
3. Scroll through the canonical owner and customer messages.
4. Click **Analyze with Qwen →**.
5. Wait for Resipi to open the **Review recipe** screen.

The extraction result is explicitly labelled. It shows a live Qwen result when a supported Qwen API key is configured; otherwise it uses the repository's saved candidate for the same demo input.

## Step 4: Review and approve the recipe

On the **Review recipe** screen:

1. Show the discovered workflow stages.
2. Open **Evidence from history** under a rule to show its source messages.
3. Point out the confidence score on each learned rule and field.
4. Show the unresolved questions. These remain questions instead of becoming unsupported automation.
5. Optionally click **Disable this rule** on one rule to demonstrate owner control.
6. Click **Approve version →**.
7. Show the immutable recipe version and content hash.
8. Click **Compile & test →**.
9. Show the compile status and passed scenarios.

Approval is required before the Telegram bot can answer customers.

## Step 5: Start the Telegram bot

In terminal 2, go to the repository root and load the token if necessary:

```bash
cd /Users/colinleong/Downloads/Resipi/repo
set -a
source .env
set +a
python3 adapters/telegram_bot/poll.py
```

If the token is already exported and there is no `.env` file, run only:

```bash
python3 adapters/telegram_bot/poll.py
```

Expected output:

```text
polling as @your_bot_username  (runtime: hermes)
```

Keep this terminal running. The bot and web app share the approved recipe and conversation state in `var/resipi.db`.

## Step 6: Demo a successful Telegram order

Open Telegram, find the bot by username, and press **Start**. Send these messages one at a time, waiting for each reply:

1. `Hi nak chocolate cake 1kg`
2. `satu`
3. `Sabtu ni, delivery`
4. `12 Jalan Example, Kuala Lumpur`
5. `yes correct`

What to point out:

- The bot replies in the customer's detected language.
- It asks only for fields still missing from the approved recipe.
- Delivery causes it to collect an address.
- It summarizes the complete order before confirmation.
- After confirmation, the order moves to `awaiting_deposit`; it does not claim that payment was received.
- State is persisted before each Telegram reply is sent.

## Step 7: Demo a safe escalation

The current Telegram chat is now in a terminal state, so use a different Telegram chat or reset and repeat Steps 3–5 before demonstrating another path.

From a fresh chat, send one of these messages:

```text
whats the price for 2kg
```

```text
can you do it tomorrow? urgent
```

```text
I want to speak to a human
```

The bot should hand the request to the owner instead of inventing a price, promising a rush order, or pretending to be a human.

## Reset between demos

From the browser, click **Reset demo**, or run:

```bash
./demo/reset.sh
```

An allowed Telegram user can also send:

```text
/reset
```

A reset removes imports, candidates, approvals, conversations, and events. After resetting, repeat the import, analysis, and approval steps before messaging the bot again.

## Troubleshooting

### `TELEGRAM_BOT_TOKEN is not set`

Load `.env` with `set -a; source .env; set +a`, or export `TELEGRAM_BOT_TOKEN` in the same terminal used to start the poller.

### `No approved recipe yet`

Complete Steps 3 and 4 in the web app. The bot intentionally refuses to run a workflow that the owner has not approved.

### The poller repeatedly reports an error

Check that the bot token is valid and that no other process is polling the same Telegram bot. Telegram allows only one active `getUpdates` poller per bot.

### `/reset` replies `Not permitted.`

Add your numeric Telegram user ID to `TELEGRAM_ALLOWED_USER_IDS`, then restart the bot so it reads the updated environment.

### The bot does not answer after a reset

Resetting also deletes the approved recipe. Import the history, analyze it, and approve a new version before trying again.
