"""Check an audit run against its inputs and the checked-in sample results."""
import argparse
import csv
import json
from pathlib import Path

from audit.manifest import input_hashes


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify(run, data, expected):
    manifest = json.loads((run / "manifest.json").read_text())
    check(input_hashes(data) == manifest["input_sha256"], "Input files differ from the run manifest.")
    with (data / "invoice_events.jsonl").open(encoding="utf-8") as file:
        events = [json.loads(line) for line in file]
    source_ids = {row["parcel_id"] for row in events}
    check(manifest["raw_events"] == len(events), "Manifest raw event count differs from the input.")
    accepted = read_rows(run / "accepted.csv")
    rejected = read_rows(run / "quarantine.csv")
    audits = read_rows(run / "audit.csv")
    queue = read_rows(run / "disputes.csv")
    carriers = read_rows(run / "carriers.csv")
    good = {r["parcel_id"] for r in accepted}
    bad = {r["parcel_id"] for r in rejected}
    check(len(accepted) == len(good) and not good & bad and good | bad == source_ids,
          "The handoff must account for every parcel exactly once across dispositions.")
    check(len(audits) == len(good) and {r["parcel_id"] for r in audits} == good,
          "Audit grain differs from the accepted invoice grain.")
    disputed = sorted((r for r in audits if r["status"] == "OVERBILLED"),
                      key=lambda r: (-int(r["variance_cents"]), r["parcel_id"]))
    check(queue == disputed, "Queue differs from overbilled parcels in priority order.")
    check(sum(int(r["disputable_cents"]) for r in carriers) ==
          sum(int(r["variance_cents"]) for r in queue), "Carrier exposure fails to reconcile.")
    check(sum(int(r["parcels"]) for r in carriers) == len(audits), "Carrier count mismatch.")
    for carrier in carriers:
        invoices = [r for r in audits if r["carrier"] == carrier["carrier"]]
        over = [int(r["variance_cents"]) for r in invoices if r["status"] == "OVERBILLED"]
        under = [int(r["variance_cents"]) for r in invoices if r["status"] == "UNDERBILLED"]
        counts = {
            "parcels": len(invoices), "overbilled": len(over), "disputable_cents": sum(over),
            "underbilled_cents": -sum(under), "billed_cents": sum(int(r["billed_cents"]) for r in invoices),
            "missing_rates": sum(r["status"] == "NEEDS_RATE" for r in invoices),
        }
        check(all(int(carrier[key]) == value for key, value in counts.items()),
              f"Carrier totals differ from invoice detail for {carrier['carrier']}.")
    metrics = {
        "raw_events": len(events), "unique_parcels": len(source_ids), "accepted": len(good),
        "quarantined_parcels": len(bad), "quarantine_rows": len(rejected),
        "missing_rates": sum(r["status"] == "NEEDS_RATE" for r in audits),
        "disputes": len(queue), "disputable_cents": sum(int(r["variance_cents"]) for r in queue),
        "underbilled_cents": -sum(int(r["variance_cents"]) for r in audits if r["status"] == "UNDERBILLED"),
    }
    if expected:
        check(metrics == json.loads(expected.read_text()), f"Sample totals differ: {metrics}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--custom", action="store_true", help="Skip the fixed sample totals")
    args = parser.parse_args()
    verify(args.run, args.data, None if args.custom else Path("examples/expected.json"))
