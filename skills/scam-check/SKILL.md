---
name: scam-check
description: Check whether a message, call, email, text, web page or phone number claiming to be from a company, bank, utility, carrier or government agency is genuine, before anyone replies, calls, clicks or pays. Use when the person received something suspicious, found a support number online, is asked to pay or share a code, or lost money and wants to know what to do next. Uses the redress MCP tools.
---

# Check for a scam

Scammers copy real companies: fake support numbers in search ads, texts about unpaid tolls or packages, calls about shutoffs or refunds, and "recovery" offers after a loss. The fastest protection is to verify the contact and use only official channels.

## 1. Check what the person received

- For a message, email, text or call script, call `scam_check(text, company)` with the full text and the company it claims to be.
- For a single phone number, email address or link, call `verify_contact(value, company)`.

Explain the result in plain words:
- `on_file`: the contact is in the registry, with a source.
- `official_domain`: the domain is the company's, but this exact address is not on file. Read the address letter by letter.
- `belongs_to_other`: the contact belongs to a different organization. Treat it as fake.
- `lookalike`: the domain uses a company's name, but it is not one of that company's domains. Treat it as fake. `lookalike` lists the official domains.
- `not_on_file`: unknown. Do not use it until it is confirmed on the company's official site.

List every red flag that `scam_check` found, with its reason.

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
