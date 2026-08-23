Colin owns engine/, hermes/, schemas and tests (single-writer rule, plan section 5).
The app lane consumes these seams only:

  engine.extract.extract_candidate(canonical_messages: list) -> dict   # Qwen candidate
  engine.compile.compile_recipe(approved_recipe: dict, approval: dict) -> dict  # -> {bundle_dir, compile_report, test_report}
  hermes.runtime.recipe_step(state: dict, message: dict) -> dict       # -> {state, actions, trace}

Until these exist the app falls back to app/devdata stubs and labels the fallback
in the UI (truthfulness rule, plan section 12).
