import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from classifier import classify_ticket, back_translate
from helpdesk import HelpdeskClient

load_dotenv()

EVAL_RESULTS_DIR = Path(__file__).parent / "eval_results"


def run_eval(save_tag: str = "eval"):
    client = HelpdeskClient()
    examples = client.get_examples()
    client.close_connection()

    print(f"Running eval on {len(examples)} labelled examples...\n")

    results = []
    scores = {"language": 0, "category": 0, "priority": 0, "action": 0}
    total = len(examples)

    for ex in examples:
        ticket = {
            "id": ex["id"],
            "subject": ex.get("subject", ""),
            "body": ex.get("body", ""),
            "channel": ex.get("channel", "email"),
            "customer_plan": ex.get("customer_plan", "unknown"),
        }
        label = ex["label"]

        print(f"  [{ex['id']}] {ex.get('subject', '(no subject)')}")

        try:
            prediction = classify_ticket(ticket)
        except Exception as e:
            print(f"    ERROR: {e}")
            results.append({"id": ex["id"], "error": str(e)})
            continue

        matches = {}
        for field in ["language", "category", "priority", "action"]:
            match = prediction.get(field) == label.get(field)
            matches[field] = match
            if match:
                scores[field] += 1

        english_check = None
        if prediction.get("action") == "reply" and prediction.get("draft_reply"):
            english_check = back_translate(prediction["draft_reply"])
            print(f"    [Verification] {english_check[:120]}")

        result = {
            "id": ex["id"],
            "subject": ex.get("subject", ""),
            "expected": label,
            "predicted": {
                "language": prediction.get("language"),
                "category": prediction.get("category"),
                "priority": prediction.get("priority"),
                "action": prediction.get("action"),
                "reason": prediction.get("reason"),
                "confidence": prediction.get("confidence"),
            },
            "matches": matches,
            "english_check": english_check,
        }
        results.append(result)

        status = " ".join(
            f"{f}:{'OK' if m else 'MISS'}" for f, m in matches.items()
        )
        print(f"    {status}")

    print("\n--- Eval Summary ---")
    for field in ["language", "category", "priority", "action"]:
        pct = scores[field] / total * 100 if total else 0
        print(f"  {field}: {scores[field]}/{total} ({pct:.0f}%)")

    overall = sum(scores.values()) / (total * 4) * 100 if total else 0
    print(f"  overall: {overall:.0f}%")

    EVAL_RESULTS_DIR.mkdir(exist_ok=True)
    output_path = EVAL_RESULTS_DIR / f"{save_tag}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"scores": scores, "total": total, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {output_path}")

    return scores, total, results


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "eval_before"
    run_eval(save_tag=tag)
