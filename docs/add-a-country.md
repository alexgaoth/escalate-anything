# Add your country

Escalate Anything started in the US. The data model works for any country: companies, the regulators and
ombudsmen that take complaints, the consumer rules that apply, and the escalation ladder between them.
If you know how complaints work where you live, you can add your country, one small pull request at a time.

| Country | Status | Maintainers |
|---|---|---|
| 🇺🇸 United States | complete: 279 companies, 51 states and DC, 31 rules | @alexgaoth |
| 🇪🇺 European Union | in progress: EU261 (incl. the 2027 reform), enforcement bodies for all 30 countries, European Consumer Centres, 12 airlines | wanted |
| 🇬🇧 United Kingdom | in progress: 25 companies — telecoms, energy, airlines, banks; Ofcom, Ofgem, CAA, FCA and the ombudsmen; 15 rules incl. UK261, Section 75 and APP scam refunds | wanted |
| 🇩🇪 Germany, 🇫🇷 France, 🇪🇸 Spain | in progress: air dispute bodies (SRUV, BfJ, MTV, AESA); national companies wanted | wanted |
| Your country | [open an issue](https://github.com/alexgaoth/escalate-anything/issues/new?template=add-a-country.yml) | you |

## How a country is put together

1. **`registry/countries/<code>.yaml`**: the two-letter ISO code in lowercase (`gb` for the UK, `de` for Germany).
   Name, languages, currency, `status: in_progress`, `maintainers`, and `how_complaints_work`: a short paragraph on
   the usual path (company first, how long to wait, then which ombudsman or regulator, then small claims).
   An EU member state gets the EU-wide rules automatically through `registry/countries/eu.yaml`.
2. **Regulators and ombudsmen** in `registry/regulators/<code>-<name>.yaml` with `country: <code>` and a `level`:
   `national` for a government regulator, `ombudsman` for a statutory or approved dispute scheme,
   `supranational` for an EU-level body. List each id in `registry/sectors.yaml` under `regulators`.
3. **Rules** in `registry/rules/` with `jurisdiction: <code>` (or `eu`). Cite the law itself (legislation site,
   official journal) and the regulator's own guidance. Give the amounts and deadlines with the source.
4. **Companies** in `registry/companies/<sector>/<id>.yaml` with `countries: [<code>]`. Start with the companies people
   complain about most: airlines, phone and internet, energy, banks. Use the company's own contact and complaint pages.
5. **Phone numbers** in international format: `+44 345 222 1111` or `+44-345-222-1111`.

Every value needs a `source` (the page it came from) and `last_verified` (the date you read it), the same as the US data.
Values you could only see in a search snippet get `verified_via: search_snippet`, so agents double-check them.

## Check and send

```bash
uv run escalate validate                                  # schema and cross-reference checks
uv run escalate playbook <company> <issue> --country <code>   # read it the way an agent will
uv run pytest -q
```

Open one pull request per sector or per group of companies, so each one is easy to review. Write the text yourself
in plain English; an AI assistant may help you research, but you check every value against its source.

Agents use `country` when they call `get_playbook`, `get_rules`, `find_regulators` and `find_company`, so your
country's rules apply as soon as the data is merged.
