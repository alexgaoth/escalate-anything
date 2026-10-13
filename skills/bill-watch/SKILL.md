---
name: bill-watch
description: Watch the person's recurring bills for increases and ending promotions by reading bill emails, recording amounts and flagging anomalies. Use when the person asks to check their bills, set up bill monitoring, or find bills that went up. Uses the Escalate Anything MCP tools and an email connector (for example Gmail).
---

# Watch bills

## 1. Find bills

Use the email connector to search for recent bill notifications, for example:
`subject:(bill OR statement OR "your bill" OR "payment due") newer_than:100d`
Narrow it to known billers from `find_company` (internet, wireless, utilities, insurance and subscriptions).

For each bill email:
- Read the amount due, the billing period end date (or statement date), and the plan name.
- Read any promotion end date ("your promotional rate ends on …").
- Skip receipts for one-time purchases.

If the email has only a link to the bill portal and no amount, list it for the person. Do not sign in for them.

## 2. Record

Call `bill_record(company, period_end, amount, plan, promo_end)` for each bill. Use the company name as it appears. Escalate Anything maps it to its registry id. Recording the same bill twice updates it.

## 3. Check

Call `bill_check()`. For each finding:
- `increase`: show the previous median, the new amount and the percent change. Offer `negotiate-bill`, or `resolve` with `billing_error` if the increase breaks a promise.
- `promo_ending` / `promo_ended`: offer `negotiate-bill` before the date.

Report in a short table: company, last amount, change, finding and suggested action. Do not contact any company without the person's approval.

## 4. Repeat

When the person asks for a regular check, suggest a scheduled task that runs this skill monthly and reports findings only. Create it only after they agree.
