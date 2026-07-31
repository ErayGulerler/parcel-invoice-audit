# Data contract

Sample billing period ending 31 July 2026.

Both files represent one billing period, July 2026. The contract card applies throughout the month. Every amount is in grosz (100 grosz = PLN 1). The sample has one base charge per parcel and excludes VAT, fuel surcharges and refunds. Comparing real invoices would require those charge types and effective-dated rates.

## Invoice events

Each JSON line describes a full replacement version of a parcel invoice. Field names are case-sensitive.

| Field | Type | Rule |
| --- | --- | --- |
| parcel_id | string | Nonblank and unique across all carriers for this billing period |
| revision | integer | Positive, increases when the carrier corrects a bill |
| carrier, zone | strings | Nonblank, case-sensitive contract keys |
| weight_g | integer | Positive weight in grams |
| billed_cents | integer | Nonnegative amount in grosz |

A missing parcel ID, invalid revision or unparseable typed record stops the batch. Exact repeated events collapse. For each parcel, Spark keeps the highest revision present in the extract. Multiple distinct rows at that revision go to quarantine together, even if one looks plausible. A highest revision with an invalid charge also goes to quarantine. This prevents an old, superseded price from reaching finance.

Quarantine contains one row per distinct held payload. Count distinct parcel IDs to find the number of invoices on hold. The output covers the input snapshot supplied to the run. To process a correction next month, include the original history or build a persisted current-state table.

## Carrier tariffs

One CSV row gives the price for a `carrier, zone` pair. The header is `carrier,zone,base_cents,extra_kg_cents`. Both amounts must be nonnegative integers. The pipeline fails on duplicate contract keys so a join cannot multiply invoice lines.

The base price covers the first started kilogram. Each additional started kilogram adds the extra rate. An invoice of exactly 2,000 g has one extra unit. An invoice of 2,001 g has two.

```text
extra units = floor((weight_g - 1) / 1000)
expected    = base_cents + extra units * extra_kg_cents
variance    = billed_cents - expected
```

| Audit status | Meaning | Finance action |
| --- | --- | --- |
| OVERBILLED | Positive variance | Check invoice evidence and dispute the difference if confirmed |
| UNDERBILLED | Negative variance | Track separately for reconciliation |
| MATCH | Zero variance | No price exception |
| NEEDS_RATE | No matching carrier and zone | Request the missing tariff. Expected amount and variance stay blank |

Carrier exposure sums only positive differences. Billed totals include accepted invoices with missing rates. The report uses PLN for presentation, while the CSV outputs preserve integer grosz.
