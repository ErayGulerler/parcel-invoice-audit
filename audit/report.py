"""Render the carrier totals and first ten disputes as an offline HTML report."""
import csv
from decimal import Decimal
from html import escape
from pathlib import Path


def money(cents):
    return f"{Decimal(cents) / 100:,.2f}"


def render(folder: Path):
    def rows(name):
        with (folder / name).open(newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file))

    carriers = rows("carriers.csv")
    disputes = rows("disputes.csv")
    quarantined = {r["parcel_id"] for r in rows("quarantine.csv")}
    total = sum(int(r["disputable_cents"]) for r in carriers)
    count = sum(int(r["parcels"]) for r in carriers)
    missing = sum(int(r["missing_rates"]) for r in carriers)
    under = sum(int(r["underbilled_cents"]) for r in carriers)
    bars = []
    for row in carriers:
        value = int(row["disputable_cents"])
        share = 100 * value / total if total else 0
        bars.append(f'<tr><th>{escape(row["carrier"])}</th><td>{int(row["overbilled"])}</td>'
                    f'<td><b>{money(value)}</b></td><td><div class="track"><i style="width:{share:.1f}%">'
                    f'</i></div>{share:.1f}%</td></tr>')
    queue = []
    for r in disputes[:10]:
        queue.append("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in [
            r["parcel_id"], r["carrier"], r["zone"], money(r["billed_cents"]),
            money(r["expected_cents"]), money(r["variance_cents"])]) + "</tr>")
    html = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Parcel invoice audit | Finance review</title>
<style>
*{{box-sizing:border-box}}body{{background:#f4f2eb;color:#182b2b;margin:0;font:16px/1.55 Arial,sans-serif}}
main{{max-width:920px;margin:auto;padding:44px 24px}}header{{border-top:5px solid #19665b}}
h1,h2{{font-family:Georgia,serif;font-weight:normal;line-height:1.15}}h1{{font-size:clamp(36px,6vw,64px);margin:18px 0 4px}}
h2{{font-size:28px;margin:32px 0 10px}}.meta{{font-size:13px;color:#4a5c55}}.lead{{font-size:22px;max-width:660px}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}td,th{{padding:9px 8px;border-bottom:1px solid #c8cec7;text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}thead{{background:#e7e9e0;font-size:13px}}.track{{display:inline-block;width:72px;background:#d6ded2;margin-right:8px}}
i{{background:#277769;height:8px;display:block}}.scroll{{overflow-x:auto}}a{{color:#155d51}}footer{{margin-top:26px;border-top:1px solid #929f95;padding-top:12px}}
@media print{{main{{padding:0}}a{{color:inherit}}}}
</style><main><header><p class="meta">Finance operations &nbsp; / &nbsp; Carrier billing</p>
<h1>Parcel invoice audit</h1></header>
<p class="lead"><strong>PLN {money(total)}</strong> in potential overcharges across {len(disputes):,} parcels.</p>
<p>{count:,} invoices passed revision checks. {missing} still need a contract rate.
{len(quarantined)} parcel IDs were held for data review. Undercharges total PLN {money(under)}.</p>
<h2>Where to start</h2><div class="scroll"><table><thead><tr><th>Carrier</th><th>Disputes</th>
<th>Exposure (PLN)</th><th>Share of exposure</th></tr></thead><tbody>{''.join(bars)}</tbody></table></div>
<h2>Largest invoice differences</h2><p>Showing {len(queue)} of {len(disputes)} disputes. All amounts are in PLN.</p>
<div class="scroll"><table><thead><tr><th>Parcel</th><th>Carrier</th><th>Zone</th>
<th>Billed</th><th>Contract</th><th>Difference</th></tr></thead><tbody>{''.join(queue)}</tbody></table></div>
<footer><a href="disputes.csv">Full dispute queue</a> &nbsp; / &nbsp; <a href="audit.csv">All priced and unrated invoices</a>
&nbsp; / &nbsp; <a href="quarantine.csv">Held revisions</a></footer></main></html>"""
    (folder / "review.html").write_text(html, encoding="utf-8")
