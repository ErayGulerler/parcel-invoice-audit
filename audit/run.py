"""Run the July invoice audit from the repository root."""
import argparse
import csv
import json
import os
import shutil
import tempfile
from importlib.metadata import version
from numbers import Number
from pathlib import Path
from uuid import uuid4

from pyspark.sql import SparkSession
from snowflake.snowpark import Session, functions as F
from snowflake.snowpark.types import LongType, StringType, StructField, StructType

from audit.clean import COLUMNS, EVENT_SCHEMA, resolve
from audit.manifest import input_hashes
from audit.reconcile import carrier_summary, price
from audit.report import render
from audit.sample import RATE_FIELDS


def write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)


def run_spark(source, out):
    spark = (SparkSession.builder.appName("parcel-invoice-audit")
             .master("local[2]").config("spark.sql.shuffle.partitions", "4")
             .config("spark.ui.enabled", "false").getOrCreate())
    events = None
    try:
        events = (spark.read.schema(EVENT_SCHEMA).option("mode", "FAILFAST")
                  .json(str(source / "invoice_events.jsonl")).cache())
        received = events.count()
        accepted, rejected = resolve(events)
        for frame, filename in [(accepted, "accepted.csv"), (rejected, "quarantine.csv")]:
            write_csv(out / filename, frame.columns,
                      frame.sort("parcel_id", "billed_cents", "carrier", "zone", "weight_g")
                      .toLocalIterator())
        return received
    finally:
        if events is not None:
            events.unpersist()
        spark.stop()


def read_csv(session, path, fields, stage):
    types = [StringType() if key in ("parcel_id", "carrier", "zone") else LongType()
             for key in fields]
    schema = StructType([StructField(key.upper(), dtype) for key, dtype in zip(fields, types)])
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        if next(reader, None) != fields:
            raise ValueError(f"Unexpected CSV header in {path.name}")
        if stage is None:
            rows = []
            for row in reader:
                if len(row) != len(fields):
                    raise ValueError(f"Invalid column count in {path.name}")
                record = []
                for value, dtype in zip(row, types):
                    if value == "":
                        record.append(None)
                    elif isinstance(dtype, LongType):
                        record.append(int(value))
                    else:
                        record.append(value)
                rows.append(record)
            return session.create_dataframe(rows, schema)
    session.file.put(str(path.resolve()), stage, auto_compress=False)
    return session.read.schema(schema).option("SKIP_HEADER", 1).option(
        "FIELD_OPTIONALLY_ENCLOSED_BY", '"').csv(f"{stage}/{path.name}")


def export_frame(frame, path):
    # In the emulator, a nullable integer column can return values such as 29100.0.
    # All numeric output fields in this contract are whole units or grosz.
    fields = [field.lower() for field in frame.columns]

    def integer_fields(rows):
        for row in rows:
            values = []
            for field, value in zip(fields, row):
                if isinstance(value, Number):
                    if field in ("expected_cents", "variance_cents") and value != value:
                        value = None  # The emulator can return NaN for an unmatched rate.
                    elif value == int(value):
                        value = int(value)
                    else:
                        raise ValueError(f"Expected a whole number in {field}, received {value}")
                values.append(value)
            yield values

    write_csv(path, fields, integer_fields(frame.to_local_iterator()))


def run_snowpark(source, out, connection=None):
    if connection:
        session = Session.builder.config("connection_name", connection).create()
    else:
        session = Session.builder.config("local_testing", True).create()
    try:
        stage = None
        if connection:
            name = "PARCEL_AUDIT_" + uuid4().hex.upper()
            session.sql(f"CREATE TEMPORARY STAGE {name}").collect()
            stage = "@" + name
        invoices = read_csv(session, out / "accepted.csv", COLUMNS, stage)
        tariffs = read_csv(session, source / "tariffs.csv", RATE_FIELDS, stage)
        priced = price(invoices, tariffs)
        export_frame(priced.sort("parcel_id"), out / "audit.csv")
        disputes = priced.filter(F.col("status") == "OVERBILLED")
        export_frame(disputes.sort(F.col("variance_cents").desc(), F.col("parcel_id")),
                     out / "disputes.csv")
        export_frame(carrier_summary(priced), out / "carriers.csv")
    finally:
        session.close()


def run(source, target, connection=None):
    source, target = source.resolve(), target.resolve()
    if target.exists():
        raise FileExistsError(f"Choose a new output directory: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".parcel-audit-", dir=target.parent))
    try:
        with tempfile.TemporaryDirectory(dir=temp) as directory:
            snapshot = Path(directory)
            for name in ("invoice_events.jsonl", "tariffs.csv"):
                shutil.copyfile(source / name, snapshot / name)
            inputs = input_hashes(snapshot)
            received = run_spark(snapshot, temp)
            run_snowpark(snapshot, temp, connection)
        render(temp)
        manifest = {
            "raw_events": received, "input_sha256": inputs,
            "pyspark": version("pyspark"), "snowpark": version("snowflake-snowpark-python"),
            "snowpark_mode": "warehouse" if connection else "local emulator",
        }
        (temp / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        # Publish only after both engines and all file writes have succeeded.
        os.rename(temp, target)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    print(f"Review {target / 'carriers.csv'} and {target / 'disputes.csv'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=Path("data"), type=Path)
    parser.add_argument("--out", required=True, type=Path, help="New directory for this run")
    parser.add_argument("--connection", help="Snowflake named connection (default: local emulator)")
    args = parser.parse_args()
    run(args.data, args.out, args.connection)
