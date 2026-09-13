# Meesho Dashboard — API Memory & Rules

Ye file Kiro ke liye permanent memory hai. User Meesho ke DevTools se curl bhejta hai;
har API ka structure aur uska dashboard view yahan document hota hai. User ne bola:
**"jo bhi API bhejunga usko hamesha mind me rakhna, aur difference bhi dekhte rehna."**

## Core Rules (hamesha follow karo)

1. **Har naya curl yaad rakho** — jab user naya curl de, use `meesho_curl.txt` me ek
   `[label]` ke saath save karo AUR is file me uska entry add karo (URL, type, key fields, view).
2. **Difference dekhte raho** — dashboard har refresh pe data ka snapshot save karta hai
   (`meesho_snapshots/<label>.json`). Naye refresh pe purane se compare karke "kya naya aaya,
   kya hata, count kitna badla" dikhana hai.
3. **UI Hindi/Hinglish me** — user Hinglish me baat karta hai, labels bhi wahi style me.
4. **Session/cookie expire hone par** user se fresh curl maango — API fail (401/403) ho to yahi wajah hoti hai.
5. Amounts me `₹` symbol aata hai strings me — number nikaalne ke liye `_to_number()` use karo.

## Known APIs

### [returns] — Return Claims (RTO + Customer Return)
- **URL:** `POST https://supplier.meesho.com/api/fulfillment/returnRto/fetchReturnClaims`
- **Body:** `{"screenType":"returns","size":50,"filters":{"shipment_status":"intransit"},"supplier_details":{"identifier":"wafhp","id":4789817},...}`
- **Records:** `data[]` array
- **Key field `type`:**
  - `"RTO"` → Courier Return (order customer tak nahi pahuncha, wapas aa raha)
  - `"RET"` → Customer Return (customer ne return kiya, `return_shipping_fee` lagti hai, aksar ₹175)
- **Sub types (`sub_type`):** forward_RTO, EXCHANGE_RTO, FIRST_RET
- **Per record fields:** order_num, awb, carrier_name, shipment_status, created_date_iso,
  expected_delivery_date_iso, return_shipping_fee, tracking_url,
  return_reason_details.{return_reason, detailed_reason},
  product.{name, sku, variation, image_urls[], meesho_pid, category}
- **View:** `_render_returns()` — 2 sub-tabs (RTO / Customer Return), overview metrics
  (RTO count, RET count, customer return fee total, total returns), tables with product image + track link.
- **Supplier:** identifier=`wafhp`, id=`4789817`

### [prev_payments] — Previous Payments (payouts, jo mil chuke)
- **URL:** `POST https://supplier.meesho.com/api/payouts/payments/previous-payments`
- **Body:** `{"identifier":"wafhp","supplier_id":4789817,"limit":30}` (limit = kitne din chahiye)
- **Records:** `daywisePayments[]` (har din ka ek payment/transfer)
- **Per day fields:** date, date_iso, transferId, netAmount (jo mila),
  netOrderAmount (order value), platformRecovery (total deduction, negative),
  platformCompensation, netPlatformRecovery.{adsCost, programCosts, loanSettlementAmount},
  netPlatformCompensation.{referralAmount, programBenefits}, headerAmount ("₹1.30K" jaise)
- **`header`:** overall summary (netAmount, netOrderAmount, platformRecovery)
- **`payoutState`:** {state: "unblocked"/blocked, message} — payout block hai ya nahi
- **View:** `_render_prev_payments()` — metrics (total received, order amount, deductions,
  payment days) + payout state banner + day-wise table (net payment, ads cost, deductions,
  transfer id). Diff transferId/date ke basis pe.
- **Note:** ye "ho chuke" payments hain.

### [upcoming_payments] — Upcoming Payments (jo aane wale hain)
- **URL:** `POST https://supplier.meesho.com/api/payouts/payments/upcoming-payments`
- **Body:** `{"identifier":"wafhp","supplier_id":4789817,"limit":30}`
- **Structure prev_payments jaisa hi:** `daywisePayments[]` + `header` + `count` + `updatedAtTimestamp`
- Future dates dikhata hai (transferId nahi hota, kyunki abhi hua nahi).
  `netPlatformRecovery.loanSettlementStatus` = "To be calculated" bhi aata hai.
- **View:** dono payments `_render_payments(mode=...)` se render hote hain.
  Mode `_payment_mode(label, curl)` se decide — label/URL me "upcoming" ho to upcoming.
  Upcoming green theme "Total Upcoming", previous "Total Received".
- **Detector:** `_is_daywise_payments()` (dono ke paas `daywisePayments` key hoti hai).
- Dashboard order: Upcoming pehle, phir Previous.

## Curl parsing notes
- Parser `curl --url '...'` AUR plain `curl '...'` dono handle karta hai.
- `-b/--cookie`, `-H/--header`, `--data-raw/--data` supported.

## Pagination (IMPORTANT)
- Request body me `size` = ek page me max records (default 50).
- `run_curl()` me AUTO-PAGINATION hai: agar response me `total_pages > 1` aur `cursor` ho,
  to dashboard khud `cursor`/`page_pointer`/`filter_cursor` bhej ke saare pages laata hai
  aur `data[]` merge kar deta hai. Isliye 100/500 records ho to bhi sab aa jaate hain —
  `size` badhane ki zaroorat nahi.
- Response ke pagination fields: `cursor`, `filter_cursor`, `page_pointer`, `total_pages`, `total_records`.

## Pending / TODO (user ne bola aayenge)
- payments API (upcoming/outstanding) — abhi nahi mila
- orders/settlement API (profit/loss) — abhi nahi mila
- Jab aaye to yahan add karna + view banana.
