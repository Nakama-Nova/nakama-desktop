# Billing B5 (GST correctness): what the desktop does now, and what the backend must still do

## Done on the desktop (no backend change)
- **GSTIN check** at the till (`services/gst.py`): 15 characters, valid state code, check letter. A mistyped GSTIN stops the bill; a good one shows the buyer's state.
- **Buyer GSTIN** is saved on the customer (`gstin` already exists on the backend customer). The customer update only sends it when given, so it never wipes the one on file.
- **GST summary** on Reports (this month, last month, this financial year, or chosen dates) from the existing `GET /reports/gst-summary`, with a CSV for the accountant.
- HSN code was already on the product form (`hsn_code` exists on the backend item).

## Needs the backend (not decided or built; the desktop cannot do these alone)
1. **IGST and place of supply.** The server always splits CGST/SGST. A buyer whose GSTIN state differs from the shop's state must get IGST. Needs the shop's state (from the shop GSTIN in the letters profile, once registered) and the buyer's state (first two digits of the buyer GSTIN, or a `state` on the customer for a buyer without GSTIN). The summary already has an `igst_total`; it is always 0 today.
2. **GST on the discounted value.** The server takes a bill discount off the total (items + GST) and leaves GST on the full price. For a registered shop the GST must be worked on the price after discount. Change `build_sale` to spread the discount over the lines before working out GST.
3. **Export invoices.** You said you will export. An export is zero-rated (shipped under a bond/LUT, or with IGST paid and refunded): it needs an invoice type "export" (no GST or IGST), the buyer's country and shipping bill/port details, and the currency. Decide with your accountant which route you will use before building.
4. **HSN code and buyer GSTIN on the invoice PDF**, and the words "Tax Invoice" with the shop GSTIN once the shop is registered (`letters` already holds `gstin`, "printed only once the shop is registered").
5. **Credit notes** (B4) must reduce GST in the summary: already in the B3/B4 contract.

## Order
1 and 2 first (they change the amounts), then 4, then 3 when you know your export route.
