# Authoring registry entries

The registry is only useful if an agent can trust it. Every rule below exists to keep it trustworthy.

## Files

| What | Path | Schema `$defs` |
|---|---|---|
| Company | `registry/companies/<sector>/<id>.yaml` | `company` |
| Federal or nonprofit regulator | `registry/regulators/<id>.yaml` | `regulator` |
| State agencies | `registry/states/<two-letter code>.yaml` | `state` |
| Law or regulation | `registry/rules/<id>.yaml` | `rule` |
| Issue vocabulary | `registry/issues.yaml` | – |
| Sector and regulator vocabulary | `registry/sectors.yaml` | – |

The file name must equal the `id`. Ids are lowercase kebab-case (`united-airlines`). Issue and sector ids are snake_case (`delayed_baggage`).

Run `uv run escalate validate <files>` after every edit. Commit only when it prints `OK`.

## Sourcing rules

1. **Every channel, fact and rule point has a `source` and a `last_verified` date.** The source is the page that shows the value. Prefer the company's or the government's own page.
2. **Never guess.** If you cannot find a phone number, URL, deadline or dollar amount on a source page, leave it out. A missing entry is safe. A wrong entry sends an agent to the wrong place.
3. **`last_verified` is the date you saw the value on the source page.** Do not copy dates from other files.
4. **Quote numbers exactly as the source states them**, with the unit and the condition ("within 24 hours of arrival", "up to $3,800 per passenger").
5. **Tips are not facts.** Advice such as "ask for the retention department" goes in `tips`. A tip from a company page is `kind: official`. A tip from a consumer site is `kind: community` and needs a `source`.
6. **Record what blocks agents.** Set `access: login` when the user must sign in, `captcha` when a bot check blocks the form, and `human_only` when the company accepts only the account holder by voice or in person. Add free-text notes to `known_blockers`.
7. **Rules change.** For a law or regulation, set `status` from a current source. Several recent federal rules were vacated, stayed or withdrawn. Explain in `status_note`.

## Formats

- Phone: `+1-800-555-0100`, or a short code such as `611`. Put extensions as `+1-800-555-0100 ext. 2`.
- Dates: `2026-10-12`.
- URLs: full `https://` URLs. Use the most specific page (the refund form, not the home page).
- Claims: one or two plain sentences. No marketing language.

## Company example

```yaml
id: example-air
name: Example Air
aliases: [exampleair, example airlines]
sector: airline
website: https://www.example.com
account_url: https://www.example.com/account
regulators: [us-dot]

channels:
  - id: customer-care-form
    type: web_form
    label: Customer care complaint form
    value: https://www.example.com/contact/complaint
    purposes: [flight_cancellation, flight_delay, poor_service]
    access: open
    source: https://www.example.com/contact
    last_verified: 2026-10-12
  - id: baggage-claim-form
    type: web_form
    label: Delayed bag expense claim
    value: https://www.example.com/baggage/claim
    purposes: [delayed_baggage, lost_baggage]
    access: login
    notes: Needs the file reference number from the airport report.
    source: https://www.example.com/baggage
    last_verified: 2026-10-12
  - id: reservations-phone
    type: phone
    label: Reservations and customer service
    value: +1-800-555-0100
    hours: 24/7
    source: https://www.example.com/contact
    last_verified: 2026-10-12

escalation:
  - {rung: frontline, channel: reservations-phone}
  - {rung: written_complaint, channel: customer-care-form}
  - {rung: regulator, regulator: us-dot}
  - {rung: payment_dispute}

playbooks:
  - issue: delayed_baggage
    summary: Report at the airport, then claim expenses online.
    evidence: [bag tag, file reference number, receipts]
    steps:
      - do: Report the bag at the baggage office before leaving the airport. Get the file reference number.
      - do: Submit receipts for essentials through the claim form.
        channel: baggage-claim-form
      - do: If the airline does not answer, file a complaint with the U.S. DOT.
        regulator: us-dot
    facts:
      - kind: deadline
        claim: Expense claims for a delayed bag must be submitted within 21 days after the bag is returned.
        issues: [delayed_baggage]
        source: https://www.example.com/legal/contract-of-carriage
        last_verified: 2026-10-12

facts:
  - kind: policy
    claim: Example Air refunds a cancelled flight to the original form of payment on request.
    issues: [flight_cancellation]
    source: https://www.example.com/refunds
    last_verified: 2026-10-12

tips:
  - kind: community
    text: Written complaints through the customer care form get a reference number; phone calls often do not.
    source: https://www.consumer-site.example/airline-complaints
    last_verified: 2026-10-12

known_blockers:
  - The baggage claim form needs sign-in with the loyalty account or the file reference number.
```

## What to cover for each company

In order of value:

1. The main customer service phone number and the chat or contact page.
2. The written complaint channel (form or email), and the executive or escalation channel if the company publishes one.
3. The cancellation path and the refund or dispute path.
4. Playbooks for the two to four most common issues in that sector, with the company's own deadlines and limits.
5. `known_blockers`, so an agent knows when to hand back to the person.
