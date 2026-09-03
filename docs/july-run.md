# The July sample run

Sample billing period ending 31 July 2026.

## Decide what finance should do first

Start with Baltic. Its 72 flagged invoices account for PLN 291.00 of the PLN 361.50 in potential overcharges. Open [disputes.csv](../examples/july/disputes.csv), filter to Baltic and check the repeated zone B differences against the signed tariff. The data generator deliberately includes a recurring 4.50 PLN supplement there. Its presence in a real invoice would call for checking the contract and any surcharge addendum before contacting the carrier.

| Sample result | Amount or count |
| --- | ---: |
| Raw events / distinct parcel IDs | 1,371 / 1,200 |
| Accepted parcel histories | 1,191 |
| Quarantined parcels / distinct held payloads | 9 / 14 |
| Accepted parcels without a contract rate | 11 |
| Positive discrepancies | 121 |
| Potential overcharges | PLN 361.50 |
| Undercharges, reported separately | PLN 101.60 |

The missing rates belong to a separate follow-up. Their financial exposure is unknown. The 9 held parcels need a corrected invoice version. The measured amount is a review opportunity on synthetic data. Actual refunds would require a claims process and proof of settlement.

## Trace one correction

Search for `PK00017` in [the event file](../data/invoice_events.jsonl). Revision 1 bills 1,530 grosz. Revision 2 bills 1,430. Spark accepts revision 2 regardless of where it appears in the file.

Vistula's zone B tariff is 1,250 grosz plus 140 for each extra started kilogram. At 2,400 g this parcel uses three started kilograms. The expected charge is 1,250 + 2 × 140 = 1,530. Snowpark records a variance of -100 grosz, or a PLN 1.00 undercharge. You can find the parcel in the full audit. Only positive differences enter the dispute queue.

## Trace one held invoice

Search for `PK00211` in [quarantine.csv](../examples/july/quarantine.csv). Two different revision 1 records bill 1,400 and 1,430 grosz. Picking the last line in the file would make the answer depend on upload order. Spark keeps both as evidence and leaves the parcel out of priced totals.

## Design decisions

- **Why two engines?** Spark handles the event history before finance sees it. Snowpark keeps contract pricing in the warehouse path, where a finance team could govern access to tariffs. A single engine would be enough for the small sample. The handoff makes each stage independently inspectable.
- **Why a full snapshot?** It is easy to replay and handles late corrections. A production pipeline would likely persist the highest revision by parcel and update affected keys. It would also need a policy for corrections arriving after finance closes a period.
- **What would break at larger volume?** This version runs Spark on two local workers and writes one CSV per output through the driver. The emulator loads accepted rows in memory. For millions of parcels, write partitioned Parquet to shared storage, read it from a Snowflake stage and keep the audit detail inside Snowflake. Export only the review queue.
- **How is the output verified?** The tests include a one-gram weight boundary, conflicting revisions and duplicate tariff keys. The full-run verifier checks that every input parcel is either accepted or quarantined, each accepted parcel has one audit row, and the ranked queue adds up to the carrier exposure.
