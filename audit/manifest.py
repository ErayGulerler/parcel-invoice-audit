"""Identify the exact invoice extract and rate card behind a report."""
import hashlib


def input_hashes(directory):
    result = {}
    for name in ("invoice_events.jsonl", "tariffs.csv"):
        with (directory / name).open("rb") as file:
            result[name] = hashlib.file_digest(file, "sha256").hexdigest()
    return result
