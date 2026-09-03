# Parcel invoice audit

Sample billing period ending 31 July 2026.

A retailer has 1,371 carrier invoice events for 1,200 parcels. Some rows are upload retries. Others are corrections that arrived after the original bill. Which charges should its finance team challenge?

This Python project uses **Apache Spark** to settle the invoice history and **Snowpark** to price each accepted parcel against a contract. The supplied data is synthetic. Carrier names and PLN tariffs belong to this example.

**Start with the result.** Open [the finance report](examples/july/review.html) in a browser. The sample flags **PLN 361.50 across 121 invoices**. Baltic accounts for PLN 291.00, about 80.5% of the exposure. A reviewer can open the dispute queue, select a parcel and trace the amount back to its invoice and rate.

## Run the example

Use Python 3.12 and a Java 17 JDK. Set `JAVA_HOME` to the JDK directory and check `java -version`. Run these commands from the folder containing this README. A virtual environment keeps the two engine libraries together.

```sh
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on Linux or macOS, or `.\.venv\Scripts\Activate.ps1` in Windows PowerShell. On Windows, WSL with a Linux JDK also works as a setup option.

```sh
python -m pip install -r requirements.txt
python -m audit.run --out runs/july
python -m audit.verify runs/july
```

Open `runs/july/review.html`. The default run uses local Spark and Snowflake's Snowpark emulator. It needs no Snowflake credentials. Pick a fresh output folder for each rerun. You can also inspect the packaged sample or run `python -m audit.verify examples/july` with just Python.

Each output folder includes a `manifest.json` with the engine versions, execution mode and SHA-256 fingerprints of both input files. The verifier checks these fingerprints, so it will catch a rate card that changed after the audit ran.

## How the two engines fit

```text
Invoice event history (.jsonl)
       |
       v
Spark: collapse retries, select highest revision per parcel
       |                                    |
       | one accepted row per parcel        +--> quarantine.csv
       v
accepted.csv  +  contract tariffs (.csv)
       |
       v
Snowpark: validate rates, left join, price, compare and group
       |
       +--> audit.csv       One row for every accepted parcel
       +--> disputes.csv    Positive differences, largest first
       +--> carriers.csv    Exposure and coverage by carrier
       +--> review.html     Finance review with links to the evidence
```

| File | What to look for |
| --- | --- |
| [audit/clean.py](audit/clean.py) | Why an invalid correction blocks the older bill from slipping back into the report |
| [audit/reconcile.py](audit/reconcile.py) | The rate join, weight steps and positive exposure calculation |
| [audit/run.py](audit/run.py) | How a complete run gets published and how to switch to a Snowflake warehouse |
| [docs/july-run.md](docs/july-run.md) | Two parcel traces and design trade-offs for the July sample |
| [docs/warehouse.md](docs/warehouse.md) | Optional live execution using a named connection |
| [tests/test_audit.py](tests/test_audit.py) | Small cases for revisions, conflicting rates, exact kilogram boundaries and missing rates |

## Check or change the input

```sh
python -m unittest discover -s tests -v
```

The [CI workflow](.github/workflows/test.yml) runs the tests and checks the full sample on Linux. To rebuild the checked-in sample, run `python -m audit.sample`. To try your own extract, copy the two input files into a new folder, keep their headers and run:

```sh
python -m audit.run --data my-data --out runs/custom
python -m audit.verify runs/custom --data my-data --custom
```

The fields, assumptions and exception rules are in [the data contract](docs/data-contract.md). The verifier checks parcel coverage, queue ordering and agreement between the queue and carrier totals. In sample mode it also checks the fixed counts and amounts in [expected.json](examples/expected.json).
