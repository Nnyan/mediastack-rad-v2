# Opencode Model-by-Task Guide

Use this guide to route Opencode calls by task size and risk profile. Keep a
cheap model for routine edits, a medium model for normal fixes, and an expensive
model for architectural or data-sensitive changes.

You can now run the workflow through the `octask` command:

```bash
octask [quick|standard|critical] "your prompt"
```

- `quick` (or `fast`/`edit`) uses the cheap model
- `standard` (default) uses the balanced model
- `critical` (or `complex`/`release`) uses the premium model

If no tier is provided, `octask` defaults to `standard`.

- **Quick / repetitive tasks**: small refactors, typo/formatting cleanup, moving
  lines, small docs updates.
  - **Model**: cheapest code-edit model you trust (example: `haiku`-class model)
  - **Goal**: minimize cost per token
  - **Pattern**: `opencode run --model "$FAST_MODEL" ...`

- **Standard tasks**: feature work, API changes, moderate debugging, test
  iteration, and PR-sized edits.
  - **Model**: balanced capability/cost model (example: `sonnet`-class model)
  - **Goal**: strong default quality and speed
  - **Pattern**: `opencode run --model "$STANDARD_MODEL" ...`

- **Critical / complex tasks**: architecture, security-sensitive flows, merge
  conflict repair, multi-file refactors, and release-blocking bugs.
  - **Model**: highest quality model available in your budget
  - **Goal**: maximize correctness and context handling
  - **Pattern**: `opencode run --model "$PREMIUM_MODEL" ...`

Recommended default aliases (adapt model IDs to your actual account):

```bash
export FAST_MODEL="openrouter/anthropic/claude-3-5-haiku"
export STANDARD_MODEL="openrouter/anthropic/claude-sonnet-4"
export PREMIUM_MODEL="openrouter/anthropic/claude-opus-4"

alias oki='opencode run --model "$STANDARD_MODEL"'
alias okf='opencode run --model "$FAST_MODEL"'
alias okp='opencode run --model "$PREMIUM_MODEL"'

oki() { 
  # Usage:
  #   oki "brief task" "detailed prompt"
  local tier="$1"; shift
  case "$tier" in
    quick|fast|edit)
      opencode run --model "$FAST_MODEL" "$@" ;;
    critical|complex|release)
      opencode run --model "$PREMIUM_MODEL" "$@" ;;
    *)
      opencode run --model "$STANDARD_MODEL" "$@" ;;
  esac
}

# Optional wrapper for chat-style usage:
#   octask quick "Add a tiny type in README"
#   octask critical "Audit deploy flow before merge"
#   octask "Build a new migration flow"
```

Recommended selection policy:

1. If the prompt is short and low-risk, choose `oki quick`.
2. If it changes behavior (even one endpoint/service), choose `oki`.
3. If it changes authentication, persistence, deployment, or security logic,
   choose `oki critical`.
4. If the command failed three times in a row, switch to `oki critical` before the
   next attempt.
5. Keep a small log in your local notes so you can tune this threshold by cost.

This is intentionally lightweight: it standardizes model choice without blocking.
