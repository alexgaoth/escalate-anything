---
name: negotiate-bill
description: Lower a recurring bill (internet, cable, wireless, satellite, insurance premium, subscription) or fight a price increase after a promotion ends. Collects current offers, prepares a retention script and logs the result. Use when the person says a bill went up, is too high, or a promo is ending. Uses the Escalate Anything MCP tools.
---

# Negotiate a recurring bill

## 1. Facts first

1. Get the current bill and the previous one. Call `bill_record` for each bill if they are not recorded yet, then call `bill_check(company)`.
2. Call `get_playbook(company, "price_negotiation", state)`, and also `bill_increase` if the price went up. Note the retention channel, the facts, the tips and the blockers.
3. Find the person's leverage:
   - The company's current price for new customers for the same service. Use the company's own plans page.
   - Two competitor offers at the person's address. Ask for the address, or ask the person to check availability, because offers change by address.
   - The contract status: any early termination fee, and equipment the person owns versus rents.
   - Tenure and payment history.

## 2. Plan

Agree on these with the person before any contact:
- A target price and a walk-away point (switch provider, or downgrade).
- Changes they accept, such as a lower speed or no landline.
- Whether they will really cancel. Never bluff a cancellation they will not make.

## 3. Script

Write a short script:
1. "I am calling about my bill. It went from $X to $Y."
2. "I have an offer from [competitor] for $Z for the same speed. I would like to stay. What can you do?"
3. If the first offer is low: "That is still above $Z. Is there a loyalty or retention offer?"
4. Before accepting: "How long does this price last? What will the price be after that? Does it need a contract?"
5. "Please send the new price to my email, or confirm it in chat."

If the playbook names the retention or cancellation option in the phone menu, include it.

## 4. Contact

- Chat: say you are an AI assistant acting for the person. Get the offer in the transcript.
- Phone: the person makes the call with the script. Ask them to report the result back.

Then `case_open` (issue `price_negotiation`) and `case_log` each offer: amount, duration and the representative's name.

## 5. After

- Check the next bill. `case_log` the result.
- Call `bill_record` with `promo_end` set to the end date of the new price, so `bill_check` warns 45 days before it ends.
- If the company does not honor the promised price, switch to the `resolve` skill with issue `billing_error`.
