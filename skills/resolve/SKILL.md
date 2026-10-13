---
name: resolve
description: Resolve a problem with a US company for the person, such as a wrong bill, a refund, a cancellation, a lost or delayed bag, a cancelled flight, a denied insurance claim or a bank dispute. Finds the right channel, collects evidence, drafts the message, logs the case and escalates step by step. Use when the person wants to complain, dispute a charge, get money back or escalate. Uses the redress MCP tools.
---

# Resolve a problem with a company

You act for the person. The person decides. Each message, form submission and call goes out only after the person approves it.

## 1. Understand the case

Get these from the person, or from documents they point you to:
- The company and what went wrong, with dates and amounts.
- What they want: a refund, a credit, a fix or a cancellation, with an amount.
- Their two-letter state code. State agencies depend on it.
- Reference numbers they already have: order, confirmation, bag file, ticket or claim numbers.

Never ask for or store passwords, full card numbers or SSNs. For an account number, use the last 4 digits only.

## 2. Get the playbook

1. Call `find_company`. If nothing matches, the company is not listed. Use `list_issues` and the generic steps, and find the channels on the company's own site.
2. Call `get_playbook(company, issue, state)`. Read all of it: `steps`, `channels`, `evidence`, `facts`, `rules.in_force`, `escalation`, `known_blockers`, `security` and `warnings`.
   Then call `get_context(company)` for how the company handles complaints in practice: what tends to work, the traps, and the scams that use its name.
3. Tell the person the plan in a few lines: the first channel, the evidence to collect, any deadline from `facts`, and what comes next if it fails.
4. Warn the person about any deadline that is close.

## 3. Open the case

Call `case_open` with a short factual summary and the desired outcome. After each step below, call `case_log` with:
- `rung`: the escalation rung you used
- `reference`: every reference number
- `rep_name` and `promised`: for every promise
- `follow_up_on`: the date to check back (usually 7–14 days, or the company's stated response time)

## 4. Make contact

Use the channel from the playbook. Do not search the web for contact details the playbook already gives. If you must use a contact from anywhere else (a search result, an email, a text), call `verify_contact` first and stop if the verdict is `not_on_file` or `belongs_to_other`.

- **Written channel (email or web form):** call `draft_brief(case_id)`. Write the message from it and follow its `tone_rules`. Show the draft to the person. After they approve, either create an email draft for them to send, or fill the web form in the browser and stop before the submit button. Submit only after the person confirms.
- **Web form with `access: login` or `captcha`:** open the page and ask the person to sign in or solve the check. Continue after they say so.
- **Chat:** start by saying that you are an AI assistant writing for the person. Ask for a reference number before the chat ends. Save the transcript.
- **Phone:** give the person the number, the hours, a short script and the facts to cite. You cannot place calls unless a calling tool is connected.

## 5. Escalate when it fails

If the company refuses, does not answer by the follow-up date, or breaks a promise:
1. Call `case_get(case_id)`. `next_rung` is the next step on the ladder.
2. Call `draft_brief(case_id)` for that rung. For a regulator, use the regulator's channel and `when_to_use`. For a card dispute, use the rules it lists (billing-error deadlines).
3. Include the timeline: dates, references and broken promises from the case log.

The ladder usually goes: frontline → written complaint → executive → regulator or state agency → card dispute → arbitration or small claims. Do not skip a rung unless a deadline forces it.

## 6. Close

When it is resolved, call `case_close` with the outcome, the amount recovered and `what_worked`.

## Rules

- Cite only facts and in-force rules from the tools, with their sources. Never cite anything listed under `not_in_force` or `do_not_cite`.
- Do not invent laws, deadlines, amounts or contacts. If redress has no answer, say so, and check the company's own site.
- Keep messages short, factual and polite. Legal-brief tone and threats make companies ignore complaints.
- If a URL or phone number from redress is wrong, call `report_registry_problem`.
- Run `followups_due` at the start of a session when the person asks about their cases.
