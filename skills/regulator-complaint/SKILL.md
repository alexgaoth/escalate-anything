---
name: regulator-complaint
description: File a complaint with a government regulator or state agency after a company failed to fix a problem: DOT for airlines, FCC for telecom, CFPB for banks, cards, credit reports and loans, state utility commissions, state insurance departments and state attorneys general. Use when the person wants to escalate beyond the company. Uses the redress MCP tools.
---

# File a regulator complaint

A regulator complaint works best when it is short, specific and backed by a record. Many regulators forward the complaint to the company and require a reply, so a clear complaint often gets a senior team to act.

## 1. Choose the agency

1. If a case exists, call `case_get(case_id)`. Otherwise use the `resolve` skill first. Most agencies expect that you contacted the company first.
2. Call `find_regulators(sector, state)`. Read `when_to_use`, the process `facts` (response times, what they do with complaints) and the `channels`.
3. Pick one agency. If more than one fits, use this order:
   - The agency that regulates the company directly: DOT for airlines, the state utility commission for utilities, the state insurance department for insurers, the FCC for telecom, and the CFPB for financial products.
   - The state attorney general, for consumer protection in general.
   - The FTC and the BBB collect complaints but usually do not resolve individual ones. Tell the person this.

## 2. Prepare

Call `draft_brief(case_id, rung="regulator")`, or `rung="state_agency"`. Prepare:
- A one-paragraph summary: who, what, when, and how much.
- A dated timeline from the case log, with reference numbers and broken promises.
- The resolution wanted, specific and with an amount.
- Attachments: the evidence from the playbook (bills, receipts, emails, photos).
- Facts and in-force rules with sources, only if they apply directly.

## 3. File

- Open the agency's complaint form from the channel URL. Most forms ask for the person's name, address and account details. The person enters or confirms personal data.
- Fill in the narrative fields from the prepared text. Stop before submit, show the person the form, and submit only after they confirm.
- Record the complaint number with `case_log(kind="sent", rung="regulator", reference=...)` and set `follow_up_on` to the company's required response time from the facts. Use 30 days if there is none.

## 4. After

- When the company replies, log it. If the reply does not resolve the case, most agencies let the person respond to it. Draft that response from the same timeline.
- If it is still unresolved, `case_get` shows the next rung (card dispute, arbitration or small claims).
