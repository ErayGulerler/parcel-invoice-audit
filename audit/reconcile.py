"""Price accepted invoices and roll up the audit using Snowpark DataFrames."""
from snowflake.snowpark import functions as F

col = F.col


def price(invoices, tariffs):
    # Check the contract grain before joining. A duplicate rate would double a bill.
    duplicate = tariffs.group_by("carrier", "zone").count().filter(col("COUNT") > 1)
    if duplicate.limit(1).count():
        raise ValueError("Tariff keys must be unique (carrier, zone).")
    invalid = (col("base_cents").is_null() | (col("base_cents") < 0) |
               col("extra_kg_cents").is_null() | (col("extra_kg_cents") < 0) |
               col("carrier").is_null() | col("zone").is_null() |
               col("carrier").regexp(r"^\s*$") | col("zone").regexp(r"^\s*$"))
    if tariffs.filter(invalid).limit(1).count():
        raise ValueError("Each tariff needs a carrier, zone and nonnegative prices.")
    joined = invoices.join(tariffs, ["carrier", "zone"], "left")
    # The first started kilogram is included in the base charge.
    grams_above_first = col("weight_g") - 1
    extra_units = (grams_above_first - (grams_above_first % 1000)) / 1000
    priced = (joined.with_column("expected_cents",
                                 (col("base_cents") + extra_units * col("extra_kg_cents")).cast("long"))
              .with_column("variance_cents", col("billed_cents") - col("expected_cents")))
    return priced.with_column(
        "status",
        F.when(col("expected_cents").is_null(), F.lit("NEEDS_RATE"))
         .when(col("variance_cents") > 0, F.lit("OVERBILLED"))
         .when(col("variance_cents") < 0, F.lit("UNDERBILLED"))
         .otherwise(F.lit("MATCH")),
    ).select("parcel_id", "revision", "carrier", "zone", "weight_g", "billed_cents",
             "expected_cents", "variance_cents", "status")


def carrier_summary(priced):
    def count_status(status):
        return F.sum(F.when(col("status") == status, 1).otherwise(0))

    totals = priced.group_by("carrier").agg(
        F.count("parcel_id").alias("parcels"),
        count_status("OVERBILLED").alias("overbilled"),
        count_status("NEEDS_RATE").alias("missing_rates"),
        F.sum(col("billed_cents")).alias("billed_cents"),
        F.sum(F.when(col("status") == "OVERBILLED", col("variance_cents"))
              .otherwise(0)).alias("disputable_cents"),
        F.sum(F.when(col("status") == "UNDERBILLED", col("variance_cents"))
              .otherwise(0)).alias("underbilled_cents"),
    )
    return (totals.with_column("underbilled_cents", -col("underbilled_cents"))
            .sort(col("disputable_cents").desc(), col("carrier")))
