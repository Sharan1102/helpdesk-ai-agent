import json
import anthropic
import os

FAQ_PATH = os.path.join(os.path.dirname(__file__), "faq.md")

SYSTEM_PROMPT = """You are a support agent for Roosterly, a Dutch shift-planning app.

Your job: classify each customer ticket and decide the action.

## Rules
1. ONLY answer using the FAQ below. If the FAQ does not cover it, hand off to a human.
2. These ALWAYS go to a human (handoff), even if the FAQ seems to cover them:
   - Refunds or disputed charges
   - Cancellations and contract changes
   - Personal data requests (GDPR / AVG)
   - Possible security incidents
   - Legal threats
   - Customers threatening to leave
3. Reply in the customer's language. Most customers write in Dutch.
4. Handoff notes are in English.
5. Close tickets that are spam or empty (no real content).
6. NEVER repeat payment details (card numbers, IBANs) in replies or notes.

## Categories
- bug: something is broken or not working
- billing: invoices, payments, plans, pricing
- feature_request: customer wants a new feature or change
- question: how-to, general questions
- other: spam, empty, or doesn't fit above

## Priority
- P1: Many users blocked, or security/legal risk
- P2: One customer blocked, or money/contract involved
- P3: Something wrong/unclear, but workaround exists
- P4: No urgency: how-to, ideas, cosmetic

## FAQ
{faq}

## Output format
Respond with ONLY a JSON object (no markdown, no explanation):
{{
  "language": "nl" or "en" or "de",
  "category": "bug" | "billing" | "feature_request" | "question" | "other",
  "priority": "P1" | "P2" | "P3" | "P4",
  "action": "reply" | "handoff" | "close",
  "reason": "one or two sentences: why this category, priority and action",
  "draft_reply": "reply in customer's language (only if action is reply, otherwise omit)",
  "handoff_note": "English note for support team (only if action is handoff, otherwise omit)",
  "confidence": 0.0 to 1.0
}}"""


def load_faq() -> str:
    with open(FAQ_PATH, "r", encoding="utf-8") as f:
        return f.read()


_faq_cache: str | None = None


def get_faq() -> str:
    global _faq_cache
    if _faq_cache is None:
        _faq_cache = load_faq()
    return _faq_cache


def classify_ticket(ticket: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    faq = get_faq()
    system = SYSTEM_PROMPT.format(faq=faq)

    user_message = (
        f"Ticket ID: {ticket['id']}\n"
        f"Channel: {ticket.get('channel', 'unknown')}\n"
        f"Customer plan: {ticket.get('customer_plan', 'unknown')}\n"
        f"Subject: {ticket.get('subject', '(no subject)')}\n"
        f"Body: {ticket.get('body', '(empty)')}"
    )

    response = client.messages.create(
        model="claude-haiku-4-20250414",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    decision = json.loads(raw)

    required = ["language", "category", "priority", "action", "reason"]
    for field in required:
        if field not in decision:
            raise ValueError(f"Missing field: {field}")

    if decision["action"] == "reply" and "draft_reply" not in decision:
        raise ValueError("Action is reply but draft_reply is missing")
    if decision["action"] == "handoff" and "handoff_note" not in decision:
        raise ValueError("Action is handoff but handoff_note is missing")

    return decision


def back_translate(dutch_text: str) -> str:
    """Translate a Dutch reply to English for verification."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-20250414",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"Translate this Dutch text to English. Output only the translation:\n\n{dutch_text}",
        }],
    )
    return response.content[0].text.strip()
