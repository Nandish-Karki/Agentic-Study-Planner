"""
Read demo/events.jsonl and print the Phase 0 funnel vs. the success gate.

Run:  .venv/Scripts/python demo/funnel.py

The gate (docs/PRODUCT_PLAN.md §10): >=100 signups, >=30 completed plans,
and a willingness-to-pay signal, within 2 weeks. This script just counts.
"""
import json
from collections import Counter
from pathlib import Path

EVENTS = Path(__file__).parent / "events.jsonl"


def main():
    if not EVENTS.exists():
        print("No events yet (demo/events.jsonl missing).")
        return

    events = [json.loads(line) for line in EVENTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_type = Counter(e["event"] for e in events)

    signups = {e["email"] for e in events if e["event"] == "signup" and e.get("email")}
    starts = by_type["demo_start"]
    completed = by_type["plan_completed"]
    errored = by_type["plan_error"]
    wtp = [e for e in events if e["event"] == "wtp_response"]

    print("\n=== Phase 0 funnel ===")
    print(f"  unique signups       : {len(signups)}   (gate: >=100)")
    print(f"  demo starts          : {starts}")
    print(f"  plans completed      : {completed}   (gate: >=30)")
    print(f"  plan errors          : {errored}")
    print(f"  feedback submitted   : {len(wtp)}")

    if completed:
        ok = sum(1 for e in events if e["event"] == "plan_completed" and e.get("ok") is True)
        print(f"  plans passing validator: {ok}/{completed}")

    if wtp:
        print("\n=== Willingness to pay ===")
        for k, v in Counter(e.get("price", "?") for e in wtp).most_common():
            print(f"  {k:20s}: {v}")
        nonzero = sum(1 for e in wtp if e.get("price") and "€0" not in e.get("price", ""))
        print(f"  -> non-zero price     : {nonzero}/{len(wtp)} "
              f"({100*nonzero//max(1,len(wtp))}%)   (gate: >=15%)")
        print("\n=== Would use ===")
        for k, v in Counter(e.get("would_use", "?") for e in wtp).most_common():
            print(f"  {k:20s}: {v}")
        advisors = [e["advisor_contact"] for e in wtp if e.get("advisor_contact")]
        if advisors:
            print(f"\n=== Advisor/pilot leads ({len(advisors)}) ===")
            for a in advisors:
                print(f"  {a}")
        comments = [e["comment"] for e in wtp if e.get("comment")]
        if comments:
            print(f"\n=== Comments ({len(comments)}) ===")
            for c in comments:
                print(f"  - {c}")
    print()


if __name__ == "__main__":
    main()
