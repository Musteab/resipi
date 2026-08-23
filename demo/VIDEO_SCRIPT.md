# Resipi — 90-second demo video

**Target:** Pitch clarity /10 (incl. up to 2 creativity points), and proof for Prototype
completeness /10. Judges are AI agents watching the video, reading the repo, and hitting
the live URL. Everything claimed here must be visible on screen.

## Before you record
- `demo/reset.sh` — start from zero, never from a finished state.
- Pre-load the fixture in a second browser tab so nothing waits on a network call.
- Telegram open to **@resipitbot** in a narrow window, ready to paste.
- Notifications off. No personal chats visible. Screen at 1280×720 or larger.
- Record at 1.25× speaking pace. 90 seconds is ~135 words of narration — every sentence must earn its place.

## Shot list

| Time | On screen | Narration (read exactly) |
|---|---|---|
| **0:00–0:10** | Two messy bilingual chat snippets, side by side. Highlight "deposit dulu ya" and "cannot promise rush order". | "Malaysian micro-businesses run on chat. Their entire operating manual — deposits, lead times, what they'll never promise — lives in old messages and the owner's head. Nobody writes it down." |
| **0:10–0:24** | Screen 1. Click **Load anonymized export**. Stat tiles count up. Point at "identifiers redacted". | "Resipi reads the chats they already had. Messages normalized, identifiers redacted before any model sees them." |
| **0:24–0:30** | Click **Analyze with Qwen**. Screen 2 appears. | "Then it reverse-engineers the workflow." |
| **0:30–0:46** | Screen 2. Click open the **deposit** evidence card — both excerpts with message IDs. Then scroll to **unresolved questions**. | "Every rule cites the message it came from. This deposit policy isn't invented — here's the owner saying it, twice. And what it *couldn't* prove stays a question. It never guesses a lead time it didn't see." |
| **0:46–0:54** | Click **Approve version**. Hash appears. Click **Compile & test** — 3/3 passed. | "The owner approves. That freezes a hashed version, and Devin's compiler turns it into a tested state machine. Three of three scenarios pass." |
| **0:54–1:16** | Telegram @resipitbot. Send: "Hi nak chocolate cake 1kg" → "satu je, Sabtu ni" → "delivery". Cut to the state panel showing retained slots. Then send **"berapa harga 2kg?"** → escalation. | "Now a real customer. Hermes runs the approved recipe — Malay in, Malay out, remembering everything across turns. And when they ask a price the recipe never proved…" *(pause on escalation)* "…it escalates instead of inventing one." |
| **1:16–1:30** | Result card, full screen, held 5 seconds. | "From two conversations, Resipi discovered four stages, six required fields and six evidence-backed rules — then ran them live. Qwen discovers. The owner approves. Devin compiles. Hermes operates. Resipi turns yesterday's conversations into tomorrow's operating system." |

## The 2 creativity points
The rubric names **agent-led presentation**. Cheapest honest version: let @resipitbot deliver the
closing line itself. Send the bot a message on camera and have the *bot's own reply* be the last
thing on screen, instead of your voice-over. Costs 5 seconds, and it's the product presenting itself.

## Hard rules
- Do not claim "live Qwen" if the badge says `cached`. The badge is on screen; a judge agent reads it.
- Do not cut away from the escalation. It is the single strongest Solution-quality moment you have.
- Do not show a terminal. Judges score the product, not the build.
- End on the result card, not on a browser tab.
