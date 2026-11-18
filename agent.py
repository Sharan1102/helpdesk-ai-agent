import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from classifier import classify_ticket
from helpdesk import AlreadyHandledError, HelpdeskClient, HelpdeskError

load_dotenv()

STATE_FILE = Path(__file__).parent / "state.json"
LOG_DIR = Path(__file__).parent / "logs"


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"handled": {}}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def strip_payment_details(text: str) -> str:
    text = re.sub(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b", "[IBAN REDACTED]", text)
    text = re.sub(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[CARD REDACTED]", text)
    return text


def log_ticket(ticket: dict, decision: dict, action_result: str):
    LOG_DIR.mkdir(exist_ok=True)
    log_line = {
        "ticket_id": ticket["id"],
        "subject": strip_payment_details(ticket.get("subject", "")),
        "language": decision["language"],
        "category": decision["category"],
        "priority": decision["priority"],
        "action": decision["action"],
        "reason": strip_payment_details(decision["reason"]),
        "confidence": decision.get("confidence"),
        "result": action_result,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    log_path = LOG_DIR / f"{ticket['id']}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_line, f, indent=2, ensure_ascii=False)
    print(f"  [{ticket['id']}] {decision['action']} | {decision['category']} | {decision['priority']} | {action_result}")


def post_decision(client: HelpdeskClient, ticket_id: str, decision: dict) -> str:
    payload = {
        "language": decision["language"],
        "category": decision["category"],
        "priority": decision["priority"],
        "reason": decision["reason"],
    }
    if decision.get("confidence") is not None:
        payload["confidence"] = decision["confidence"]

    action = decision["action"]
    if action == "reply":
        payload["draft_reply"] = decision["draft_reply"]
        client.reply(ticket_id, payload)
    elif action == "handoff":
        payload["handoff_note"] = decision["handoff_note"]
        client.handoff(ticket_id, payload)
    elif action == "close":
        client.close(ticket_id, payload)
    else:
        raise ValueError(f"Unknown action: {action}")

    return "ok"


def process_ticket(client: HelpdeskClient, ticket: dict, state: dict) -> bool:
    ticket_id = ticket["id"]

    if ticket_id in state["handled"]:
        print(f"  [{ticket_id}] Already handled (skipping)")
        return False

    print(f"  [{ticket_id}] Classifying: {ticket.get('subject', '(no subject)')}")
    decision = classify_ticket(ticket)

    try:
        result = post_decision(client, ticket_id, decision)
    except AlreadyHandledError:
        print(f"  [{ticket_id}] 409 already handled on server (skipping)")
        state["handled"][ticket_id] = "already_handled_409"
        save_state(state)
        return False

    state["handled"][ticket_id] = decision["action"]
    save_state(state)
    log_ticket(ticket, decision, result)
    return True


def run_agent(reset: bool = False):
    client = HelpdeskClient()

    if reset:
        print("Resetting practice tickets...")
        client.reset_practice()
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print("Reset complete.\n")

    state = load_state()
    status = client.get_status()
    print(f"Helpdesk status: {status}\n")

    print("Fetching open tickets...")
    tickets = client.get_tickets(status="open")
    print(f"Found {len(tickets)} open tickets.\n")

    if not tickets:
        print("No open tickets to process.")
        client.close_connection()
        return

    handled_count = 0
    skipped_count = 0
    error_count = 0

    for ticket in tickets:
        try:
            was_handled = process_ticket(client, ticket, state)
            if was_handled:
                handled_count += 1
            else:
                skipped_count += 1
        except HelpdeskError as e:
            print(f"  [{ticket['id']}] API error: {e}")
            error_count += 1
        except Exception as e:
            print(f"  [{ticket['id']}] Error: {e}")
            error_count += 1

    client.close_connection()
    print(f"\nDone. Handled: {handled_count}, Skipped: {skipped_count}, Errors: {error_count}")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    run_agent(reset=reset)
