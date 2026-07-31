"""Select the authoritative invoice revision in Spark."""
from pyspark.sql import Window, functions as F

EVENT_SCHEMA = ("parcel_id string, revision long, carrier string, zone string, "
                "weight_g long, billed_cents long")
COLUMNS = ["parcel_id", "revision", "carrier", "zone", "weight_g", "billed_cents"]


def resolve(events):
    # A missing key or revision makes even the ordering ambiguous. Fail the batch.
    invalid_key = (F.col("parcel_id").isNull() | (F.trim("parcel_id") == "") |
                   F.col("revision").isNull() | (F.col("revision") < 1))
    if events.filter(invalid_key).limit(1).count():
        raise ValueError("Every invoice event needs a parcel ID and a positive revision.")

    by_parcel = Window.partitionBy("parcel_id")
    distinct = events.select(*COLUMNS).dropDuplicates()
    latest = (distinct.withColumn("last_revision", F.max("revision").over(by_parcel))
              .filter(F.col("revision") == F.col("last_revision")))
    invalid_charge = (F.col("weight_g").isNull() | (F.col("weight_g") < 1) |
                      F.col("billed_cents").isNull() | (F.col("billed_cents") < 0) |
                      F.col("carrier").isNull() | (F.trim("carrier") == "") |
                      F.col("zone").isNull() | (F.trim("zone") == ""))
    classified = latest.withColumn(
        "reason",
        F.when(F.count("*").over(by_parcel) > 1, "conflicting_revision")
         .when(invalid_charge, "invalid_charge"),
    )
    accepted = classified.filter(F.col("reason").isNull()).select(*COLUMNS)
    rejected = classified.filter(F.col("reason").isNotNull()).select(*COLUMNS, "reason")
    return accepted, rejected
