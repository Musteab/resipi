# App lane → engine lane handoff (Muste → Colin)

The app is done against the section-4 contract and runs today on fallbacks.
It calls your lane through exactly three seams. Drop these in and the UI
switches from amber "fallback" badges to green automatically — no app edits.

| Seam | Signature | Until it exists |
|---|---|---|
| `engine/extract.py` | `extract_candidate(canonical_messages: list) -> dict` (resipi.recipe.v1 candidate) | loads `fixtures/qwen_recipe_candidate.json`, else `app/devdata/recipe_candidate.dev.json`; UI labels it **cached** |
| `engine/compile.py` | `compile_recipe(recipe: dict, approval: dict) -> {"compile_report":…, "test_report":{"scenarios":[{"name","passed"}]}}` | placeholder report listing scenario names derived from the approved recipe; UI labels it **not compiled** |
| `hermes/runtime.py` | `recipe_step(recipe, state, message) -> {"state","actions","trace"}` | deterministic walker in `app/runtime_client.py`; every turn badged **local-stub** |

## What the app guarantees you
- `store.get("import")["messages"]` — canonical messages, section 4.1 shape, already redacted.
- `store.get("approved_recipe")` / `store.get("approval")` — approval envelope, section 4.3, content-hashed. Owner-disabled rules are already stripped from the approved copy.
- Conversation state, section 4.5 shape, persisted per `conversation_id` before any reply is sent.

## Action vocabulary the UI renders
`set_slot`, `ask_for_slot`, `render_template`, `transition_state`, `emit_owner_summary`, `escalate`, plus `{"type":"send","text":…}` for the customer-facing line. Anything else is ignored by the UI.

## Trace fields the demo shows
`transition`, `policy`, `evidence_ids`, `state_in`, `state_out`, `runtime`, optional `note`.

## Fixtures
`app/devdata/` is my throwaway. When your `fixtures/telegram_history.anonymized.json` and
`fixtures/qwen_recipe_candidate.json` land, the app prefers them automatically.
Evidence IDs in the candidate must reference message IDs that exist in the history —
the review screen resolves them and will show blanks otherwise.
