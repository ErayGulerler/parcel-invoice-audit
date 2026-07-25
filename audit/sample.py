"""Regenerate the small, deterministic July billing extract."""
import csv
import json
import random
from pathlib import Path

DATA = Path("data")
RATE_FIELDS = ["carrier", "zone", "base_cents", "extra_kg_cents"]


def generate(directory=DATA):
    directory.mkdir(parents=True, exist_ok=True)
    randomizer = random.Random(42)
    rates = {
        ("Baltic", "A"): (900, 120), ("Baltic", "B"): (1100, 150),
        ("Vistula", "A"): (950, 100), ("Vistula", "B"): (1250, 140),
        ("Amber", "A"): (850, 130), ("Amber", "B"): (1180, 155),
    }
    with (directory / "tariffs.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(RATE_FIELDS)
        for (carrier, zone), prices in rates.items():
            writer.writerow((carrier, zone, *prices))

    events = []
    for number in range(1, 1201):
        carrier, zone = randomizer.choice(list(rates))
        grams = randomizer.choice([500, 1000, 1001, 1750, 2400, 3500, 5100])
        base, extra = rates[carrier, zone]
        billed = base + (grams - 1) // 1000 * extra
        # One carrier sometimes bills the remote-area supplement on zone B.
        if carrier == "Baltic" and zone == "B" and number % 3 == 0:
            billed += 450
        elif number % 19 == 0:
            billed += 150
        elif number % 23 == 0:
            billed -= 80
        row = dict(parcel_id=f"PK{number:05}", revision=1, carrier=carrier,
                   zone=zone, weight_g=grams, billed_cents=billed)
        if number % 101 == 0:
            row["zone"] = "C"  # No signed rate for this zone.
        events.append(row)
        if number % 13 == 0:
            events.append(row.copy())  # A retried upload.
        if number % 17 == 0:
            events.append(dict(row, revision=2, billed_cents=billed - 100))
        if number % 211 == 0:
            events.append(dict(row, billed_cents=billed + 30))  # Same revision, two prices.
        if number % 251 == 0:
            events.append(dict(row, revision=3, weight_g=0))
    randomizer.shuffle(events)
    with (directory / "invoice_events.jsonl").open("w", encoding="utf-8") as file:
        for row in events:
            file.write(json.dumps(row, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    generate()
