# How Resipi works

## What a "rule" actually is

A rule is a thing the shop always does, that nobody ever wrote down.

The demo bakery has three, and Resipi found all of them by reading two old chats:

| Rule | What it means | Where it came from |
|---|---|---|
| `deposit_before_confirmation` | An order stays unconfirmed until the owner sees a deposit | Owner said *"deposit dulu ya... then baru saya mark confirmed"* in one chat, and *"awaiting deposit — once deposit received I will mark it confirmed"* in another |
| `address_required_for_delivery` | Only ask for an address if it's delivery | Owner asked for an address in the delivery chat, and said *"pickup so no address needed"* in the other |
| `no_rush_order_without_owner` | Never promise a next-day order | Customer asked for tomorrow, owner said *"I cannot promise rush order"* |

Nobody configured these. They were *observed*, twice each, and only then treated as rules.

## The four things Resipi looks for

1. **What you always ask** — the questions that appear in every order chat. In the bakery: item, size, quantity, date, pickup-or-delivery. These become the fields the agent collects.
2. **What order you ask them in** — the shape of the conversation. Collect → propose → customer confirms → awaiting deposit.
3. **What you never do** — the refusals. "I cannot promise rush order", "let me get back to you on price". These become the boundaries where the agent stops and calls you.
4. **How you say it** — your actual phrasing, in your actual language mix, so replies sound like you and not like a call centre.

## Why every rule shows its evidence

Because a model guessing your business rules is worthless if you can't check it.

Click any rule and you see the exact messages it came from, with dates and message numbers. If Resipi got it wrong, you see *why* it got it wrong, and you switch that rule off before it ever runs. Approval is one button, and it locks that exact version — the agent cannot change its own rules afterwards.

## What happens when it isn't sure

It refuses. This is the important part.

In the demo it found three things it could not prove and left all three switched off:

- **Minimum lead time** — one chat accepted an order two days out, another refused next-day. No consistent rule, so no rule.
- **Prices** — no price list appears anywhere in the history, so the agent will never quote one.
- **Deposit amount** — the owner never stated a figure, so the agent can't either.

A guess here would be worse than useless — it would be a promise to a customer that the shop has to honour. So instead of guessing, the agent escalates and the question lands in your orders screen.

## The pipeline

```
Your old chats  →  Qwen reads them   →  You approve      →  Compiler checks   →  Agent runs it
(WhatsApp .txt,     and proposes         or switch rules     every rule against    on new customer
 Telegram, docx)    rules + evidence     off. Locked and     a fake order          chats
                                         version-stamped
```

Each stage can only narrow what the next one is allowed to do:

- **Qwen** proposes. It cannot execute anything.
- **You** approve. Anything you switch off is stripped out before compiling.
- **The compiler** refuses anything unsafe — a rule pointing at a step that doesn't exist, an unknown operator, a reply template using a field that was never collected. It fails closed, and it cannot add business facts.
- **The agent** can only do six things: fill in a field, ask for a missing field, send one of your approved replies, move to the next step, summarise for you, or escalate. There is no seventh option, so there is no path to inventing a price or confirming a payment.

## Why this isn't a chatbot

A chatbot starts from what you tell it. You write the prompt, you build the flow, you keep it updated.

Resipi starts from what you already did. The owner writes nothing. And because every rule is tied to real messages, the owner can audit it — which is the part that makes it safe enough to leave running.

The demo shows this directly: a rule that nobody configured, discovered from evidence, then applied to an order the system has never seen before.
