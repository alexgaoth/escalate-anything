---
name: scam-check
description: Check a suspicious message, email, text or call that claims to be from a company, bank, utility, carrier or government agency for common scam red flags, and say what to do next. Use when the person received something suspicious, is asked to pay or share a code, or lost money and wants to know what to do next. Uses the redress MCP tools.
---

# Check for a scam

Scammers copy real companies: texts about unpaid tolls or packages, calls about shutoffs or refunds, and "recovery" offers after a loss. The fastest protection is to ignore the message's own links and numbers and go to the company directly.

## 1. Check what the person received

Call `scam_check(text, company)` with the full text and the company it claims to be. List every red flag it found, with its reason, in plain words.

## 2. Read what the company says about itself

Call `get_context(company)`. Tell the person:
- what the company says it never asks for (`security.never_asks`)
- the scams known to use its name (`security.known_scams`)
- where to report impersonation (`security.report_phishing`)

## 3. Act safely

- Never reply, call back or click inside the suspicious message. Use a channel from `get_playbook` or the company's official website.
- Never share one-time codes, passwords, PINs or full card numbers. Never install remote-access apps. Never pay by gift card, crypto, wire or "to yourself" by Zelle.
- A real problem (an unpaid bill, a refund, a delivery) is still there when the person signs in through the official app or website.

## 4. If money or data is already gone

Act in this order. Speed matters.
1. Call the bank's or card issuer's fraud line, from the back of the card or from `get_playbook(bank, "fraud")`. Ask to stop or reverse the payment and to secure the account.
2. Change passwords for any account that was shared. Turn on two-factor authentication.
3. Report at ReportFraud.ftc.gov. For identity theft, use IdentityTheft.gov. Use the company's `security.report_phishing` channel.
4. Use the `resolve` skill with issue `fraud` (or `unauthorized_charge` or `identity_theft`) to log a case and follow up in writing.
5. Warn the person about recovery scams: nobody legitimate charges a fee to get their money back.

## Rules

- Pattern checks catch common scams, not all of them. A `low` risk result is not proof that a message is real.
- Do not tell the person a message is "definitely safe".
- Never contact a suspected scammer on the person's behalf.
