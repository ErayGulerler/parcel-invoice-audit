# Optional Snowflake run

Sample billing period ending 31 July 2026.

The default example uses the Snowpark local testing framework. To execute pricing on a warehouse, use the same Python environment and configure a Snowflake Python connector named connection outside the repository.

1. Choose a development database, schema and warehouse. The connection's role needs warehouse, database and schema usage, plus permission to create a temporary stage in that schema. A live run uploads the two CSV inputs and uses warehouse compute.
2. Configure a connection named `parcel_dev` in your Snowflake `connections.toml` with account, user, role, database, schema, warehouse and the authentication method supported by your account. Keep credentials in your local profile.
3. From the repository root, run the commands below.

```sh
python -m audit.run --out runs/warehouse --connection parcel_dev
python -m audit.verify runs/warehouse
```

Spark still resolves the local invoice snapshot. The Snowpark session creates a uniquely named temporary stage, uploads `accepted.csv` and `tariffs.csv`, and reads both with explicit column types. Joins, price comparisons and summaries execute in Snowflake. The client writes the results into the chosen local folder and closes the session. The temporary stage is scoped to that session.

Check [carriers.csv](../examples/july/carriers.csv) against the output from the live run. The sample acceptance criteria are the same in both modes. Local testing validates the pricing logic. Stage privileges, authentication and warehouse execution require a live account.

## References

- [Snowflake local testing framework](https://docs.snowflake.com/en/developer-guide/snowpark/python/testing-locally)
- [Snowflake Python connector connections](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect)
- [Apache Spark window partitions](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.Window.partitionBy.html)
