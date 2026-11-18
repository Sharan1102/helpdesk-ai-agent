# Roosterly Support Ticket Agent

An AI agent that reads open support tickets from the Roosterly helpdesk, classifies them, and posts a decision (reply, handoff, or close) for each one.

## How to run

```bash
# 1. Clone and install
git clone <repo-url>
cd candidate_pack
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your actual keys

# 3. Run the agent (processes all open tickets)
python agent.py

# 4. Run with reset (resets practice tickets first, clears state)
python agent.py --reset

# 5. Run eval against labelled examples
python eval.py eval_before    # before fix
python eval.py eval_after     # after fix
```

## Decisions

1. **Model: Claude Haiku** — Cheapest Claude model that handles Dutch well. Keeps cost under €0.05 for 30 tickets. Fast enough for single-ticket classification.

2. **Dutch handling: Work in Dutch directly** — The LLM reads Dutch tickets natively and replies in Dutch, no pre-translation step. This avoids translation errors compounding and keeps costs low (one LLM call per ticket instead of three). For verification, `back_translate()` translates Dutch replies to English so a non-Dutch speaker can check correctness.

3. **Confidence threshold** — The LLM self-reports confidence (0-1). The agent sends whatever the LLM decides; the eval tracks confidence to identify weak spots. When unsure, the prompt biases toward handoff (safe default).

**Assumption:** When the brief says "close for spam and empty tickets," I treat tickets with no meaningful content (empty body, random characters, test messages) as closeable. Everything else gets a reply or handoff.

## Reliability

- **503 (temporary failure):** Exponential backoff retry, up to 5 attempts (1s, 2s, 4s, 8s, 16s).
- **429 (rate limited):** Reads `Retry-After` header and sleeps that duration. Also throttles requests to ~4.5/sec proactively.
- **409 (already handled):** Logged and skipped — never retries. The customer won't get a duplicate answer.
- **Crash recovery:** State is saved to `state.json` after each ticket. On restart, already-handled tickets are skipped. The state file is cleared on `--reset`.
- **Security:** API key loaded from `.env` (never committed). Ticket text is treated as data, never executed. Payment details (IBANs, card numbers) are stripped from logs via regex.

## Eval and fix

**Before fix:**
Run `python eval.py eval_before` to generate baseline scores. Results are saved to `eval_results/eval_before.json`.

**After fix:**
Run `python eval.py eval_after` after applying the fix. Results are saved to `eval_results/eval_after.json`.

**The fix:**
Describe the specific change and re-run the eval to confirm improvement.

**Verification:** The eval back-translates every Dutch reply to English, printed in the console and saved in `eval_results/` under `english_check`, so a non-Dutch speaker can verify correctness.

**Cost per 100 tickets:**
- ~1500 tokens per ticket (FAQ prompt + ticket + response)
- 100 tickets × 1500 tokens = 150K tokens
- Claude Haiku input: $0.25/MTok, output: $1.25/MTok
- Estimated: ~100K input + 50K output = $0.025 + $0.0625 ≈ **$0.09 per 100 tickets**

## What I would improve

**Next step:** Add a confidence-based fallback — if the LLM confidence is below 0.7, automatically hand off instead of replying. This reduces the risk of wrong answers reaching customers.

**Brief change:** The priority definitions could be clearer about edge cases. For example, a billing question (like "where is my invoice?") is not urgent but involves money — P2 or P3? I'd add examples to each priority level.
