(() => {
  "use strict";

  // ==== core: no DOM. tests/test_site.py runs this part in node. ==============
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (ch) => ESC[ch]);

  // ---- Markdown: ## and ### headings, "- " bullets, paragraphs, **bold**, [text](http(s) url) ----
  // Every block is HTML-escaped before any markup is added. Other link schemes render as plain text.
  function mdInline(escaped) {
    return escaped.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*/g, (m, text, url, bold) => {
      if (bold !== undefined) return `<strong>${mdInline(bold)}</strong>`;
      const inner = mdInline(text);
      return /^https?:\/\//i.test(url) ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${inner}</a>` : inner;
    });
  }

  // `top` is the heading level for "##" (default 2); "###" is one level lower.
  function renderMarkdown(src, top) {
    const base = top || 2;
    const out = [];
    let para = [];
    let list = null;
    let comment = false;
    const flushPara = () => { if (para.length) out.push(`<p>${mdInline(esc(para.join(" ")))}</p>`); para = []; };
    const flushList = () => { if (list) out.push(`<ul>${list.map((li) => `<li>${mdInline(esc(li))}</li>`).join("")}</ul>`); list = null; };
    for (const raw of String(src == null ? "" : src).replace(/\r\n?/g, "\n").split("\n")) {
      const t = raw.trim();
      if (comment) { if (t.includes("-->")) comment = false; continue; }
      if (t.startsWith("<!--")) { flushPara(); comment = !t.includes("-->"); continue; }
      if (!t) { flushPara(); flushList(); continue; }
      let m = /^(#{2,3})\s+(.+)$/.exec(t);
      if (m) {
        flushPara(); flushList();
        const level = Math.min(6, base + m[1].length - 2);
        out.push(`<h${level}>${mdInline(esc(m[2].replace(/\s+#+$/, "")))}</h${level}>`);
        continue;
      }
      m = /^-\s+(.*)$/.exec(t);
      if (m) { flushPara(); (list = list || []).push(m[1]); continue; }
      if (list) { list[list.length - 1] += " " + t; continue; } // a wrapped bullet line
      para.push(t);
    }
    flushPara(); flushList();
    return out.join("\n");
  }

  // The body of a registry Markdown file, without its YAML front matter (as context._split_front_matter).
  function stripFrontMatter(text) {
    const s = String(text == null ? "" : text).replace(/\r\n?/g, "\n");
    if (!s.startsWith("---\n")) return s;
    const end = s.indexOf("\n---\n", 4);
    return end < 0 ? s : s.slice(end + 5);
  }

  const core = { esc, renderMarkdown, stripFrontMatter };
  if (typeof module === "object" && module && module.exports) { module.exports = core; return; }

  // ==== the page ================================================================
  const D = JSON.parse(document.getElementById("data").textContent);
  const main = document.getElementById("main");
  const byId = (list) => Object.fromEntries(list.map((x) => [x.id, x]));
  const ISSUE = byId(D.issues);
  const SECTOR = byId(D.sectors);
  const COMPANY = byId(D.companies);
  const STATE = byId(D.states);

  // ---- vocabulary ----------------------------------------------------------
  const SHORT = {
    airline: "Airlines", wireless: "Wireless", internet_tv: "Internet and TV", utility: "Utilities",
    bank: "Banks and cards", credit_union: "Credit unions", payments: "Payment apps", credit_bureau: "Credit bureaus",
    student_loan: "Student loans", insurance_property: "Auto and home insurance", insurance_health: "Health insurance",
    subscription: "Subscriptions", retail: "Retail", lodging: "Hotels and rentals", travel_agency: "Travel agencies",
    car_rental: "Car rental", gig_delivery: "Rideshare and delivery", shipping: "Shipping", ground_transport: "Rail and bus",
    fitness: "Gyms",
  };
  const TYPE = {
    phone: "Phone", sms: "Text", chat: "Chat", web_form: "Form", portal: "Online", email: "Email",
    app: "App", mail: "Mail", in_person: "In person", social: "Social", fax: "Fax",
  };
  const GROUP = {
    phone: "Phone", sms: "Text message", chat: "Chat", web_form: "Online forms", portal: "Online tools and accounts",
    email: "Email", app: "Apps", mail: "Mail", in_person: "In person", social: "Social media", fax: "Fax",
  };
  const ORDER = ["phone", "sms", "chat", "web_form", "portal", "email", "app", "mail", "in_person", "social", "fax"];
  const ACCESS = {
    open: ["No sign-in", "ok", "Anyone can use it."],
    login: ["Sign-in required", "", "The account holder must sign in first."],
    captcha: ["CAPTCHA", "warn", "A CAPTCHA or bot check blocks automated agents."],
    human_only: ["Account holder only", "warn", "The company accepts only the account holder, in person or by voice."],
  };
  const RUNG = {
    frontline: "Customer service", supervisor: "Supervisor", retention: "Retention team",
    written_complaint: "Written complaint", executive: "Executive office", regulator: "Regulator",
    state_agency: "State agency", payment_dispute: "Card or bank dispute", arbitration: "Arbitration",
    small_claims: "Small claims court", public: "Public complaint",
  };
  const AGENCY = {
    attorney_general: "Attorney general", utility_commission: "Utility commission",
    insurance_department: "Insurance department", financial_regulator: "Financial regulator",
    consumer_affairs: "Consumer affairs office",
  };
  const FACT = {
    deadline: "Deadline", policy: "Policy", compensation: "Compensation", process: "Process",
    limit: "Limit", contact: "Contact", fee: "Fee",
  };
  const STATUS = {
    in_effect: "In effect", partially_in_effect: "Partly in effect", stayed: "Stayed", vacated: "Vacated",
    repealed: "Repealed", proposed: "Proposed", withdrawn: "Withdrawn", superseded: "Superseded",
  };

  // ---- helpers -------------------------------------------------------------
  const isUrl = (u) => typeof u === "string" && /^https?:\/\//i.test(u);
  const norm = (s) => String(s || "").toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim();
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const humanize = (id) => String(id).replace(/[_-]+/g, " ").replace(/^./, (ch) => ch.toUpperCase());
  const issueName = (id) => (ISSUE[id] ? ISSUE[id].name : humanize(id));
  const sectorShort = (id) => SHORT[id] || (SECTOR[id] ? SECTOR[id].name : humanize(id));
  const sectorName = (id) => (SECTOR[id] ? SECTOR[id].name : humanize(id));
  const plural = (n, one, many) => `${fmt(n)} ${n === 1 ? one : many || one + "s"}`;
  const canCopy = !!(navigator.clipboard && window.isSecureContext);
  const today = Date.parse(D.generated);

  const host = (u) => {
    try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return u; }
  };
  const shortUrl = (u) => {
    try {
      const x = new URL(u);
      let s = x.hostname.replace(/^www\./, "") + (x.pathname === "/" ? "" : x.pathname) + x.search;
      if (s.length > 58) s = s.slice(0, 42) + "…" + s.slice(-14);
      return s;
    } catch (e) { return u; }
  };
  const telHref = (v) => {
    const [num, ext] = String(v).split(/\s*ext\.?\s*/i);
    return "tel:" + num.replace(/[^\d+*#]/g, "").replace(/#/g, "%23") + (ext ? "," + ext.replace(/\D/g, "") : "");
  };
  const isStale = (date) => {
    const t = Date.parse(date);
    return !isNaN(t) && !isNaN(today) && (today - t) / 86400000 > 365;
  };
  const extLink = (href, text, cls) =>
    isUrl(href) ? `<a href="${esc(href)}"${cls ? ` class="${cls}"` : ""}>${esc(text)}</a>` : esc(text);

  // ---- shared renderers ----------------------------------------------------
  function badge(kind, text, title) {
    return `<span class="badge${kind ? " " + kind : ""}"${title ? ` title="${esc(title)}"` : ""}>${esc(text)}</span>`;
  }
  function accessBadge(ch) {
    const a = ACCESS[ch.access];
    return a ? badge(a[1], a[0], a[2]) : "";
  }

  function srcHtml(x) {
    if (!x || !x.source) return "";
    const lv = x.last_verified ? ` · verified ${esc(x.last_verified)}` : "";
    const stale = x.stale || isStale(x.last_verified) ? " " + badge("warn", "check source", "Not verified in the last year") : "";
    const label = `Source: ${host(x.source)}${x.last_verified ? ", verified " + x.last_verified : ""}`;
    return `<p class="src"><a href="${esc(x.source)}" title="${esc(x.source)}" aria-label="${esc(label)}">source</a>${lv}${stale}</p>`;
  }

  function valueHtml(ch) {
    const v = String(ch.value);
    let href = null;
    let copy = false;
    switch (ch.type) {
      case "phone": href = telHref(v); copy = true; break;
      case "sms": href = "sms:" + v.replace(/[^\d+]/g, ""); copy = true; break;
      case "email": href = "mailto:" + v; copy = true; break;
      case "fax": case "mail": case "in_person": copy = true; break;
      default: if (isUrl(v)) href = v;
    }
    let out = href
      ? `<a href="${esc(href)}">${esc(isUrl(href) ? shortUrl(v) : v)}</a>`
      : `<span class="plain">${esc(v)}</span>`;
    if (copy && canCopy) out += ` <button type="button" class="copy" data-copy="${esc(v)}" aria-label="Copy ${esc(v)}">Copy</button>`;
    return out;
  }

  function channelHtml(ch) {
    const big = ch.type === "phone" || ch.type === "sms";
    const purposes = (ch.purposes || []).map(issueName).join(", ");
    return `<li class="ch" id="ch-${esc(ch.id)}">
      <div class="ch-head"><span class="ch-label">${esc(ch.label)}</span>${accessBadge(ch)}</div>
      <div class="ch-value${big ? " big" : ""}">${valueHtml(ch)}</div>
      ${ch.hours ? `<p class="ch-hours">Hours: ${esc(ch.hours)}</p>` : ""}
      ${ch.notes ? `<p class="ch-notes">${esc(ch.notes)}</p>` : ""}
      ${purposes ? `<p class="ch-for">Use for: ${esc(purposes)}</p>` : ""}
      ${srcHtml(ch)}
    </li>`;
  }

  function channelGroups(channels) {
    const groups = {};
    (channels || []).forEach((ch) => (groups[ch.type] = groups[ch.type] || []).push(ch));
    const types = ORDER.filter((t) => groups[t]).concat(Object.keys(groups).filter((t) => !ORDER.includes(t)));
    return types.map((t) => `<section class="ch-group">
        <h3>${esc(GROUP[t] || humanize(t))}</h3>
        <ul class="ch-list">${groups[t].map(channelHtml).join("")}</ul>
      </section>`).join("");
  }

  // One line for a channel inside a step or a ladder rung.
  function channelLine(ch) {
    if (!ch) return "";
    const url = isUrl(ch.value);
    const main = url
      ? `<a href="${esc(ch.value)}">${esc(ch.label)}</a>`
      : `<span>${esc(ch.label)}</span> <span class="val">${valueHtml(ch)}</span>`;
    return `<div class="step-ch"><span class="type">${esc(TYPE[ch.type] || humanize(ch.type))}</span>${main}${accessBadge(ch)}</div>`;
  }

  function regulatorLine(r) {
    if (!r) return "";
    const chans = r.channels || [];
    const form = chans.find((c) => (c.type === "web_form" || c.type === "portal") && isUrl(c.value)) || chans.find((c) => isUrl(c.value));
    const phone = chans.find((c) => c.type === "phone");
    const name = form ? `<a href="${esc(form.value)}">${esc(r.name)}</a>` : `<span>${esc(r.name)}</span>`;
    const tel = phone ? ` <span class="val"><a href="${esc(telHref(phone.value))}">${esc(phone.value)}</a></span>` : "";
    return `<div class="step-ch"><span class="type">Regulator</span>${name}${tel}</div>`;
  }

  function factHtml(f) {
    const kind = f.kind ? `<span class="kind">${esc(FACT[f.kind] || humanize(f.kind))}</span>` : "";
    return `<li class="fact">${kind}<p class="claim">${esc(f.claim)}</p>${srcHtml(f)}</li>`;
  }

  function tipHtml(t) {
    const who = t.kind === "community" ? "Community tip" : "Company tip";
    return `<li class="fact"><span class="kind">${who}</span><p class="claim">${esc(t.text)}</p>${srcHtml(t)}</li>`;
  }

  function ruleHtml(r) {
    const cite = r.citation ? `<div class="cite">${esc(r.citation)}</div>` : "";
    if (r.do_not_cite) {
      return `<li class="rule off"><span class="rule-title">${esc(r.title)}</span> ${badge("bad", STATUS[r.status] || r.status)}${cite}
        ${r.status_note ? `<p class="rsum">${esc(r.status_note)}</p>` : ""}
        <p class="src">Not in force. Do not cite it as current law. <a href="${esc(r.source)}">source</a></p></li>`;
    }
    const pts = r.points || [];
    const partial = r.status === "partially_in_effect" ? " " + badge("warn", STATUS[r.status]) : "";
    return `<li class="rule">${extLink(r.source, r.title, "rule-title")}${partial}${cite}
      <p class="rsum">${esc(r.summary)}</p>
      ${pts.length ? `<details><summary>${plural(pts.length, "citable point")}</summary><ul class="facts">${pts.map(factHtml).join("")}</ul></details>` : ""}
    </li>`;
  }

  function ladderHtml(ladder, channels) {
    const chan = (id) => (channels || []).find((c) => c.id === id);
    return `<ol class="ladder">${(ladder || []).map((step) => {
      let detail = "";
      if (step.channel) detail = channelLine(step.channel);
      else if (step.candidate_channels && step.candidate_channels.length) {
        detail = step.candidate_channels.slice(0, 2).map(chan).filter(Boolean).map(channelLine).join("");
      }
      if (step.regulator) detail = regulatorLine(step.regulator);
      if (step.rung === "state_agency") {
        const kind = AGENCY[step.agency_kind];
        detail = `<a href="#/states">${kind ? "Your state's " + kind.toLowerCase() : "Your state agency"}</a>`;
      }
      if (step.rung === "payment_dispute" && step.rules && step.rules.length) {
        detail = step.rules.map((id) => D.rules[id]).filter(Boolean).map((r) => `<div>${extLink(r.source, r.title)}</div>`).join("");
      }
      return `<li><p class="rung">${esc(RUNG[step.rung] || humanize(step.rung))}</p>
        ${detail ? `<div class="rung-detail">${detail}</div>` : ""}
        ${step.note ? `<p class="rung-note">${esc(step.note)}</p>` : ""}</li>`;
    }).join("")}</ol>`;
  }

  function skeleton(n) {
    return `<div class="skel" aria-hidden="true">${"<div></div>".repeat(n)}</div>`;
  }

  function loadError(what, file) {
    return `<div class="empty" role="alert"><h2>Could not load ${esc(what)}</h2>
      <p>The data is in <a href="${esc(file)}">${esc(file)}</a>. If you opened this page as a local file, serve the folder over HTTP instead, for example with <code>python3 -m http.server</code>.</p>
      <p><button type="button" class="linklike" data-retry>Try again</button></p></div>`;
  }

  // ---- data loading --------------------------------------------------------
  const cache = new Map();
  function load(path, as) {
    if (!cache.has(path)) {
      cache.set(path, fetch(path).then((r) => {
        if (!r.ok) throw new Error(r.status + " " + path);
        return as === "text" ? r.text() : r.json();
      }).catch((e) => { cache.delete(path); throw e; }));
    }
    return cache.get(path);
  }
  const getJSON = (path) => load(path, "json");
  const getText = (path) => load(path, "text");

  const SHIELD_ICON = `<svg class="icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false"><path d="M10 1.8 3.2 4.4v5.1c0 4.2 2.9 7.6 6.8 8.7 3.9-1.1 6.8-4.5 6.8-8.7V4.4L10 1.8Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M10 6v4.6M10 13.4v.1" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>`;
  const MD_NOTE = "Every point links to its source. “Reported by customers” marks an anecdote from a forum: a tactic to try, not a fact to quote.";
  const guideFor = (key) => (D.guides || []).find((g) => g.key === key);
  // A dossier or guide as HTML. "Reported by customers" at the start of a bullet becomes a badge.
  const docHtml = (markdown, top) => renderMarkdown(markdown, top)
    .replace(/<li>Reported by customers:?\s*/g, `<li>${badge("warn", "Reported by customers", "An anecdote from a forum: a tactic to try, not a fact to quote")} `);

  // ---- views: home -----------------------------------------------------------
  const ui = { q: "", sector: "", homeScroll: 0, issueSector: "", stateQ: "" };
  D.companies.forEach((c) => {
    c._names = [c.name, c.id.replace(/-/g, " "), ...c.aliases].map(norm);
    c._hay = c._names.join(" | ");
  });
  const sectorCounts = {};
  D.companies.forEach((c) => [c.sector, ...c.also].forEach((s) => (sectorCounts[s] = (sectorCounts[s] || 0) + 1)));

  function matchCompanies() {
    const q = norm(ui.q);
    let list = D.companies.filter((c) => !ui.sector || c.sector === ui.sector || c.also.includes(ui.sector));
    if (!q) return list;
    const toks = q.split(" ");
    return list.map((c) => {
      let score = -1;
      if (c._names.includes(q)) score = 0;
      else if (c._names[0].startsWith(q)) score = 1;
      else if (c._names.some((n) => n.startsWith(q))) score = 2;
      else if (c._names.some((n) => (" " + n).includes(" " + q))) score = 3;
      else if (toks.every((t) => c._hay.includes(t))) score = 4;
      return [score, c];
    }).filter((x) => x[0] >= 0).sort((a, b) => a[0] - b[0]).map((x) => x[1]);
  }

  function matchIssues() {
    const q = norm(ui.q);
    if (q.length < 3) return [];
    const toks = q.split(" ");
    return D.issues.filter((i) => toks.every((t) => norm(i.name + " " + i.id).includes(t))).slice(0, 4);
  }

  function cardHtml(c) {
    const n = c.issues.length;
    return `<li><a class="card" href="#/c/${esc(c.id)}">
      <span class="card-name">${esc(c.name)}</span>
      <span class="card-sector">${esc(sectorShort(c.sector))}</span>
      <span class="card-meta"><span><b>${n}</b> ${n === 1 ? "playbook" : "playbooks"}</span><span><b>${c.channels}</b> ${c.channels === 1 ? "contact" : "contacts"}</span>${c.grade ? `<span class="grade grade-${esc(c.grade)}" title="Credibility grade ${esc(c.grade)}, verified ${esc(c.verified)}">${esc(c.grade)}</span>` : ""}</span>
    </a></li>`;
  }

  function sectorChips(active, counts, total, allLabel) {
    const chips = [`<li><button type="button" class="chip" data-sector="" aria-pressed="${!active}">${esc(allLabel)} <span class="n">${fmt(total)}</span></button></li>`];
    D.sectors.forEach((s) => {
      if (!counts[s.id]) return;
      chips.push(`<li><button type="button" class="chip" data-sector="${esc(s.id)}" aria-pressed="${active === s.id}" title="${esc(s.name)}">${esc(sectorShort(s.id))} <span class="n">${fmt(counts[s.id])}</span></button></li>`);
    });
    return chips.join("");
  }

  function renderHome() {
    const s = D.stats;
    main.innerHTML = `
      <section class="hero" aria-labelledby="h1">
        <h1 id="h1" tabindex="-1">How to actually get it fixed</h1>
        <p class="lede">Verified contacts, playbooks and escalation paths for ${fmt(s.companies)} US companies.</p>
        <ul class="stats" aria-label="What the registry holds">
          <li><b>${fmt(s.playbooks)}</b>playbooks</li>
          <li><b>${fmt(s.channels)}</b>contact channels</li>
          <li><b>${fmt(s.states)}</b>state directories</li>
          <li><b>${fmt(s.rules)}</b>consumer rules</li>
        </ul>
      </section>
      <section class="finder" aria-label="Find a company">
        <div class="field">
          <label for="q">Find a company</label>
          <div class="search">
            <input id="q" type="search" autocomplete="off" spellcheck="false" placeholder="United, Comcast, Chase, Netflix" value="${esc(ui.q)}" aria-describedby="q-hint" aria-controls="results">
            <kbd aria-hidden="true">/</kbd>
          </div>
          <p class="hint" id="q-hint">Search by name or alias. Every value links to its source and the date it was checked.</p>
        </div>
        <ul class="chips scroll" id="sector-chips" aria-label="Filter by sector">${sectorChips(ui.sector, sectorCounts, D.companies.length, "All")}</ul>
      </section>
      <div class="results-bar"><h2 id="count" aria-live="polite"></h2><button type="button" class="clear" id="clear" hidden>Clear search</button></div>
      <div id="issue-hits"></div>
      <ul class="grid" id="results"></ul>
      <section class="agents-teaser" aria-labelledby="agents-h">
        <div>
          <h2 id="agents-h">Use it from an agent</h2>
          <p>No MCP server needed. Each company is a static JSON file with resolved playbooks, sources and the escalation ladder. The person approves every message.</p>
          <p style="margin-top:10px"><a href="#/agents">How agents should use this data</a></p>
        </div>
        <pre class="code"><code>GET ${esc(D.base)}llms.txt
GET ${esc(D.base)}companies/united-airlines.json
GET ${esc(D.base)}registry.json</code></pre>
      </section>`;
    const input = document.getElementById("q");
    input.addEventListener("input", () => { ui.q = input.value; renderResults(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && input.value) { input.value = ""; ui.q = ""; renderResults(); }
      if (e.key === "Enter") {
        const first = document.querySelector("#results .card");
        if (first && matchCompanies().length === 1) first.click();
      }
    });
    document.getElementById("clear").addEventListener("click", () => {
      ui.q = ""; ui.sector = ""; input.value = "";
      setSectorHash(); renderResults(); input.focus();
    });
    document.getElementById("sector-chips").addEventListener("click", (e) => {
      const b = e.target.closest("[data-sector]");
      if (!b) return;
      ui.sector = b.dataset.sector === ui.sector ? "" : b.dataset.sector;
      setSectorHash();
      renderResults();
    });
    renderResults();
  }

  function setSectorHash() {
    history.replaceState(null, "", ui.sector ? "#/sector/" + ui.sector : "#/");
  }

  function renderResults() {
    const list = matchCompanies();
    const grid = document.getElementById("results");
    if (!grid) return;
    document.querySelectorAll("#sector-chips [data-sector]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sector === ui.sector)));
    const where = ui.sector ? ` in ${sectorShort(ui.sector)}` : "";
    const filtered = !!(ui.q || ui.sector);
    document.getElementById("count").textContent = ui.q
      ? `${plural(list.length, "company", "companies")} matching “${ui.q.trim()}”${where}`
      : `${plural(list.length, "company", "companies")}${where}`;
    document.getElementById("clear").hidden = !filtered;
    document.getElementById("clear").textContent = ui.q ? "Clear search" : "Show all";
    const issues = matchIssues();
    document.getElementById("issue-hits").innerHTML = issues.length
      ? `<p class="hint" style="margin:-4px 0 14px">Looking for an issue? ${issues.map((i) => `<a href="#/issues/${esc(i.id)}">${esc(i.name)}</a>`).join(", ")}</p>`
      : "";
    if (!list.length) {
      grid.innerHTML = `<li class="empty" style="grid-column:1/-1"><h2>No company matches</h2>
        <p>The registry covers ${fmt(D.companies.length)} companies. Try another spelling or the company's parent.</p>
        <p>For a company that is not listed, the <a href="#/issues">issue guides</a> have generic steps, and <a href="#/states">state agencies</a> take complaints about any business.</p></li>`;
      return;
    }
    grid.innerHTML = list.map(cardHtml).join("");
  }

  // ---- views: company ------------------------------------------------------
  function companyHead(c, doc) {
    const rec = doc ? doc.company : null;
    const meta = [];
    if (rec && rec.parent) meta.push(`Part of ${esc(rec.parent)}`);
    const actions = rec ? `<div class="actions">
        ${isUrl(rec.website) ? `<a class="btn primary" href="${esc(rec.website)}">Website <span class="ext" aria-hidden="true"></span></a>` : ""}
        ${isUrl(rec.account_url) ? `<a class="btn" href="${esc(rec.account_url)}">Sign in to your account <span class="ext" aria-hidden="true"></span></a>` : ""}
        <button type="button" class="btn" data-scroll="contacts">All contacts</button>
        <a class="btn" href="companies/${esc(c.id)}.json">JSON data</a>
        <a class="btn" href="c/${esc(c.id)}/">Open as a page</a>
      </div>` : "";
    const jump = c.issues.length ? `<div class="jump"><p class="label" id="jump-l">Get help with</p>
        <ul class="chips" aria-labelledby="jump-l">${c.issues.map((i) => `<li><a class="chip" href="#/c/${esc(c.id)}/${esc(i)}">${esc(issueName(i))}</a></li>`).join("")}</ul></div>` : "";
    return `<div class="page-head">
      <nav class="crumbs" aria-label="Breadcrumb"><a href="#/">Companies</a><span aria-hidden="true">/</span><a href="#/sector/${esc(c.sector)}">${esc(sectorShort(c.sector))}</a></nav>
      <h1 id="h1" tabindex="-1">${esc(c.name)}</h1>
      <p class="meta-line">${esc(sectorName(c.sector))}${meta.length ? ". " + meta.join(". ") + "." : ""}</p>
      ${doc && doc.credibility ? credLine(doc.credibility) : ""}
      ${actions}${jump}
    </div>`;
  }

  function credLine(cr) {
    const pct = Math.round((cr.primary_share || 0) * 100);
    const weak = (cr.verified_from && ((cr.verified_from.search_snippet || 0) + (cr.verified_from.archive || 0))) || 0;
    const dossier = cr.dossier_last_verified ? ` · dossier ${esc(cr.dossier_last_verified)}` : "";
    return `<div class="cred-line"><span class="grade grade-${esc(cr.grade)}">${esc(cr.grade)}</span>
      <span>Last verified <b>${esc(cr.last_verified || "unknown")}</b>${dossier} · ${pct}% official or government sources${weak ? ` · ${weak} from search snippets or archives` : ""}</span>
      <details class="cred-more"><summary>What does this mean?</summary><p>${esc(cr.explanation || "")}</p></details></div>`;
  }

  function playbookHtml(c, issue, p) {
    const stepIds = new Set();
    const steps = (p.steps || []).map((st) => {
      if (st.channel) stepIds.add(st.channel.id);
      return `<li><p class="step-do">${esc(st.do)}</p>
        ${st.note ? `<p class="step-note">${esc(st.note)}</p>` : ""}
        ${st.channel ? channelLine(st.channel) : ""}${st.regulator ? regulatorLine(st.regulator) : ""}</li>`;
    }).join("");
    const more = (p.channels || []).filter((ch) => !stepIds.has(ch.id) && (ch.purposes || []).includes(issue));
    const rules = (p.rules && p.rules.in_force) || [];
    const off = (p.rules && p.rules.not_in_force) || [];
    const warn = (p.warnings || []).filter((w) => !/^No .* playbook/.test(w));
    return `<details class="pb" id="pb-${esc(issue)}" data-issue="${esc(issue)}">
      <summary><span class="pb-title">${esc(issueName(issue))}</span>${p.summary ? `<span class="pb-sum">${esc(p.summary)}</span>` : ""}</summary>
      <div class="pb-body">
        ${(p.evidence || []).length ? `<h3>Have this ready</h3><ul class="evidence">${p.evidence.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}
        <h3>Steps</h3><ol class="steps">${steps}</ol>
        ${more.length ? `<h3>More contacts for this issue</h3>${more.map(channelLine).join("")}` : ""}
        ${(p.facts || []).length ? `<h3>Facts you can cite</h3><ul class="facts">${p.facts.map(factHtml).join("")}</ul>` : ""}
        ${(p.tips || []).length ? `<h3>Tips</h3><ul class="facts">${p.tips.map(tipHtml).join("")}</ul>` : ""}
        ${rules.length ? `<h3>Rules that may apply</h3><ul class="rules">${rules.map(ruleHtml).join("")}</ul>` : ""}
        ${off.length ? `<h3>Rules not in force</h3><ul class="rules">${off.map(ruleHtml).join("")}</ul>` : ""}
        ${warn.length ? `<div class="box warn" style="margin-top:16px"><ul class="blockers">${warn.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>` : ""}
        <div class="pb-actions"><a class="linklike" href="c/${esc(c.id)}/${esc(issue.replace(/_/g, "-"))}/">Open as a page</a><button type="button" class="linklike" data-copylink="${esc(issue)}">Copy link to this playbook</button></div>
      </div>
    </details>`;
  }

  // Scam warnings: official domains, what the company never asks for, known scams, where to report phishing.
  function hasShield(doc) {
    const s = doc.security || {};
    return ["official_domains", "never_asks", "known_scams", "report_phishing"].some((k) => (s[k] || []).length);
  }

  function shieldHtml(c, doc) {
    if (!hasShield(doc)) return "";
    const s = doc.security;
    const claim = (f) => `<li class="fact"><p class="claim">${esc(f.claim)}</p>${srcHtml(f)}</li>`;
    const parts = [];
    if ((s.official_domains || []).length) {
      parts.push(`<div class="shield-part"><h3>Official domains</h3>
        <ul class="domains">${s.official_domains.map((d) => `<li><code>${esc(d)}</code></li>`).join("")}</ul>
        <p class="notes">Real links and emails from ${esc(c.name)} end in one of these. Look-alike sites add words such as “-support” or “-refund”, or put the real name in front of another domain.</p></div>`);
    }
    if ((s.never_asks || []).length) parts.push(`<div class="shield-part"><h3>${esc(c.name)} will never ask you for…</h3><ul class="facts">${s.never_asks.map(claim).join("")}</ul></div>`);
    if ((s.known_scams || []).length) parts.push(`<div class="shield-part"><h3>Known scams</h3><ul class="facts">${s.known_scams.map(claim).join("")}</ul></div>`);
    if ((s.report_phishing || []).length) parts.push(`<div class="shield-part"><h3>Report phishing</h3><ul class="ch-list">${s.report_phishing.map(channelHtml).join("")}</ul></div>`);
    return `<section class="shield" aria-labelledby="sh-h" id="scams">
      <div class="shield-head"><h2 id="sh-h">${SHIELD_ICON}Scam warnings</h2></div>
      <div class="shield-grid">${parts.join("")}</div>
    </section>`;
  }

  // "How it actually goes": the company's dossier and a link to the sector guide.
  function dossierHtml(c, doc) {
    const d = doc.dossier;
    const g = doc.guide;
    if (!d && !g) return "";
    const guideLink = g ? `<a href="#/guides/${esc(g.key)}">${esc(g.title || sectorName(g.key) + " guide")}</a>` : "";
    if (!d) {
      return `<section class="section" aria-labelledby="hg-h"><h2 id="hg-h">How it actually goes</h2>
        <div class="box"><p>There is no dossier for ${esc(c.name)} yet. The guide ${guideLink} tells how complaints work across the industry.</p></div></section>`;
    }
    return `<section class="section" aria-labelledby="hg-h" id="dossier"><h2 id="hg-h">How it actually goes</h2>
      <p class="notes section-note">${esc(MD_NOTE)}${d.last_verified ? ` Checked ${esc(d.last_verified)}.` : ""}</p>
      <div class="box md">${docHtml(d.markdown, 3)}</div>
      ${g ? `<p class="notes guide-link">For the whole industry, read ${guideLink}.</p>` : ""}
    </section>`;
  }

  function companyBody(c, doc) {
    const rec = doc.company;
    const issues = (rec.playbooks || []).map((p) => p.issue);
    const covered = (x) => !x.issues || !x.issues.length || x.issues.some((i) => issues.includes(i));
    const otherFacts = (rec.facts || []).filter((f) => !issues.length || !covered(f));
    const otherTips = (rec.tips || []).filter((t) => !issues.length || !covered(t));
    const pbs = issues.map((i) => doc.playbooks[i] ? playbookHtml(c, i, doc.playbooks[i]) : "").join("");
    const blockers = rec.known_blockers || [];
    const contacts = `<section class="section contacts" aria-labelledby="ch-h" id="contacts"><h2 id="ch-h">Contacts <span class="n">${(rec.channels || []).length}</span></h2>
      <div class="${issues.length ? "ch-cols" : ""}">${channelGroups(rec.channels)}</div></section>`;
    return `<div class="layout">
      <div class="primary">
        ${issues.length ? `<section class="section" aria-labelledby="pb-h"><h2 id="pb-h">Playbooks <span class="n">${issues.length}</span></h2>${pbs}</section>` : contacts}
        ${dossierHtml(c, doc)}
        ${otherFacts.length || otherTips.length ? `<section class="section" aria-labelledby="f-h"><h2 id="f-h">More facts</h2><div class="box"><ul class="facts">${otherFacts.map(factHtml).join("")}${otherTips.map(tipHtml).join("")}</ul></div></section>` : ""}
      </div>
      <aside class="aside" aria-label="Escalation and blockers">
        <section class="section box" aria-labelledby="esc-h"><h2 id="esc-h">Escalation path</h2>
          <p class="notes" style="margin:-6px 0 14px">Go up one step at a time. Keep reference numbers and dates from each contact.</p>
          ${ladderHtml(doc.escalation, rec.channels)}</section>
        ${blockers.length ? `<section class="section box warn" aria-labelledby="bl-h"><h2 id="bl-h">Known blockers</h2><ul class="blockers">${blockers.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></section>` : ""}
        ${rec.notes ? `<section class="section" aria-labelledby="n-h"><h2 id="n-h">Notes</h2><p class="notes">${esc(rec.notes)}</p></section>` : ""}
        <section class="section" aria-labelledby="d-h"><h2 id="d-h">Data</h2>
          <p class="notes">For agents: <a class="datafile" href="companies/${esc(c.id)}.json">companies/${esc(c.id)}.json</a> has this page as JSON, with every playbook resolved.</p></section>
      </aside>
    </div>
    ${issues.length ? contacts : ""}`;
  }

  let shownCompany = null;
  async function showCompany(id, issue, token) {
    const c = COMPANY[id];
    if (!c) return showNotFound(`No company with the id “${id}”.`);
    document.title = `${c.name}: contacts, playbooks and escalation | Escalate Anything`;
    if (shownCompany === id && document.getElementById("pb-h") !== null) { openPlaybook(issue, true); return; }
    shownCompany = null;
    main.innerHTML = companyHead(c, null) + skeleton(4);
    focusHeading();
    let doc;
    try {
      doc = await getJSON(`companies/${id}.json`);
    } catch (e) {
      if (token !== navToken) return;
      main.innerHTML = companyHead(c, null) + loadError(c.name, `companies/${id}.json`);
      return;
    }
    if (token !== navToken) return;
    main.innerHTML = companyHead(c, doc) + shieldHtml(c, doc) + companyBody(c, doc);
    shownCompany = id;
    if (issue) openPlaybook(issue, true);
    else focusHeading();
  }

  function openPlaybook(issue, scroll) {
    if (!issue) { window.scrollTo(0, 0); focusHeading(); return; }
    const el = document.getElementById("pb-" + issue);
    if (!el) return;
    el.open = true;
    if (scroll) {
      el.scrollIntoView({ block: "start" });
      el.querySelector("summary").focus({ preventScroll: true });
    }
  }

  // ---- views: issues -------------------------------------------------------
  function showIssues(focus) {
    document.title = "Issues: what to do for each kind of problem | Escalate Anything";
    const counts = {};
    D.issues.forEach((i) => i.sectors.forEach((s) => (counts[s] = (counts[s] || 0) + 1)));
    const any = D.issues.filter((i) => i.sectors.includes("all")).length;
    const list = D.issues.filter((i) => !ui.issueSector || i.sectors.includes("all") || i.sectors.includes(ui.issueSector));
    Object.keys(counts).forEach((k) => (counts[k] += any));
    main.innerHTML = `<div class="page-head">
        <h1 id="h1" tabindex="-1">Issues</h1>
        <p class="lede">${fmt(D.issues.length)} kinds of problems, each with generic steps and the evidence to gather. Where a company has its own playbook, it replaces the generic steps.</p>
      </div>
      <ul class="chips scroll" id="issue-chips" aria-label="Filter by sector" style="margin-bottom:22px">${sectorChips(ui.issueSector, counts, D.issues.length, "All issues")}</ul>
      <div>${list.map(issueHtml).join("")}</div>`;
    document.getElementById("issue-chips").addEventListener("click", (e) => {
      const b = e.target.closest("[data-sector]");
      if (!b) return;
      ui.issueSector = b.dataset.sector === ui.issueSector ? "" : b.dataset.sector;
      showIssues();
      const again = document.querySelector(`#issue-chips [data-sector="${ui.issueSector}"]`);
      if (again) again.focus();
    });
    if (focus) {
      const el = document.getElementById("issue-" + focus);
      if (el) { el.open = true; el.scrollIntoView({ block: "start" }); el.querySelector("summary").focus({ preventScroll: true }); return; }
    }
  }

  function issueHtml(i) {
    const sectors = i.sectors.includes("all") ? "Any company" : i.sectors.map(sectorShort).join(", ");
    const cos = i.companies.map((id) => COMPANY[id]).filter(Boolean);
    return `<details class="pb" id="issue-${esc(i.id)}">
      <summary><span class="pb-title">${esc(i.name)}</span><span class="pb-sum">${esc(i.description)}</span></summary>
      <div class="pb-body">
        <p class="src" style="margin-top:12px">${esc(sectors)}</p>
        ${i.evidence.length ? `<h3>Have this ready</h3><ul class="evidence">${i.evidence.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}
        <h3>Generic steps</h3><ol class="steps">${i.steps.map((s) => `<li><p class="step-do">${esc(s)}</p></li>`).join("")}</ol>
        <h3>Company playbooks <span class="muted" style="font-weight:400">${cos.length}</span></h3>
        ${cos.length ? `<ul class="inline-links">${cos.map((c) => `<li><a href="#/c/${esc(c.id)}/${esc(i.id)}">${esc(c.name)}</a></li>`).join("")}</ul>` : `<p class="notes">No company has its own playbook for this issue yet. Use the generic steps.</p>`}
      </div>
    </details>`;
  }

  // ---- views: states -------------------------------------------------------
  function showStates() {
    document.title = "State agencies | Escalate Anything";
    main.innerHTML = `<div class="page-head">
        <h1 id="h1" tabindex="-1">State agencies</h1>
        <p class="lede">Attorneys general, utility commissions, insurance departments and financial regulators for all 50 states and DC. Open a state for complaint forms and phone numbers.</p>
      </div>
      <div class="field" style="margin-top:18px;max-width:420px">
        <label for="sq">Find a state</label>
        <div class="search"><input id="sq" type="search" autocomplete="off" placeholder="New York or NY" value="${esc(ui.stateQ)}" aria-controls="state-list"></div>
      </div>
      <ul class="state-grid" id="state-list"></ul>`;
    const input = document.getElementById("sq");
    const draw = () => {
      const q = norm(ui.stateQ);
      const list = D.states.filter((s) => !q || norm(s.name).includes(q) || s.id === q);
      document.getElementById("state-list").innerHTML = list.length ? list.map(stateCard).join("")
        : `<li class="empty" style="grid-column:1/-1"><h2>No state matches</h2><p>Type a state name or its two-letter code.</p></li>`;
    };
    input.addEventListener("input", () => { ui.stateQ = input.value; draw(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { const a = document.querySelector("#state-list h2 a"); if (a) a.click(); }
    });
    draw();
  }

  function stateCard(s) {
    return `<li class="state-card"><h2><a href="#/states/${esc(s.id)}">${esc(s.name)}</a></h2>
      <ul class="agency-list">${s.agencies.map((a) => `<li><span class="k">${esc(AGENCY[a.kind] || humanize(a.kind))}</span>${isUrl(a.website) ? `<a href="${esc(a.website)}">${esc(a.name)}</a>` : esc(a.name)}</li>`).join("")}</ul>
      <p class="state-more"><a href="#/states/${esc(s.id)}" aria-label="${esc(s.name)}: complaint forms and phone numbers">Complaint forms and phone numbers</a></p></li>`;
  }

  async function showState(code, token) {
    const s = STATE[code];
    if (!s) return showNotFound(`No state with the code “${code}”.`);
    document.title = `${s.name} state agencies | Escalate Anything`;
    const head = `<div class="page-head">
        <nav class="crumbs" aria-label="Breadcrumb"><a href="#/states">States</a></nav>
        <h1 id="h1" tabindex="-1">${esc(s.name)}</h1>
        <p class="lede">${plural(s.agencies.length, "agency", "agencies")} that take consumer complaints.</p>
      </div>`;
    main.innerHTML = head + skeleton(3);
    focusHeading();
    let doc;
    try {
      doc = await getJSON(`states/${code}.json`);
    } catch (e) {
      if (token !== navToken) return;
      main.innerHTML = head + loadError(s.name, `states/${code}.json`);
      return;
    }
    if (token !== navToken) return;
    const agencies = (doc.agencies || []).map((a) => `<section class="agency box" aria-labelledby="ag-${esc(a.id)}">
        <h2 id="ag-${esc(a.id)}">${esc(a.name)}</h2>
        <p class="kindline">${esc(AGENCY[a.kind] || humanize(a.kind))}${a.covers_sectors && a.covers_sectors.length ? `. Covers ${esc(a.covers_sectors.map(sectorShort).join(", "))}` : ""}</p>
        ${isUrl(a.website) ? `<p style="margin-top:6px"><a href="${esc(a.website)}">${esc(shortUrl(a.website))}</a></p>` : ""}
        ${a.notes ? `<p class="ch-notes">${esc(a.notes)}</p>` : ""}
        ${channelGroups(a.channels)}
        ${(a.facts || []).length ? `<h3 style="font-size:.9375rem;margin:16px 0 8px">Facts</h3><ul class="facts">${a.facts.map(factHtml).join("")}</ul>` : ""}
      </section>`).join("");
    const facts = (doc.facts || []).length ? `<section class="section box" style="margin-top:18px"><h2>State facts</h2><ul class="facts">${doc.facts.map(factHtml).join("")}</ul></section>` : "";
    main.innerHTML = head + agencies + facts + `<p class="notes" style="margin-top:24px">JSON: <a class="datafile" href="states/${esc(code)}.json">states/${esc(code)}.json</a></p>`;
    focusHeading();
  }

  // ---- views: guides ---------------------------------------------------------
  function guideCard(g) {
    const what = g.key === "scams" ? "Scams" : sectorShort(g.sector || g.key);
    return `<li><a class="card" href="#/guides/${esc(g.key)}">
      <span class="card-name">${esc(g.title || humanize(g.key))}</span>
      <span class="card-sector">${esc(what)}</span>
      ${g.last_verified ? `<span class="card-meta">Checked ${esc(g.last_verified)}</span>` : ""}
    </a></li>`;
  }

  function showGuides() {
    document.title = "Guides | Escalate Anything";
    const list = D.guides || [];
    main.innerHTML = `<div class="page-head">
        <h1 id="h1" tabindex="-1">Guides</h1>
        <p class="lede">How complaints work in each industry, what gives you leverage, and the scams to watch for. ${esc(MD_NOTE)}</p>
      </div>
      ${list.length ? `<ul class="grid guide-grid">${list.map(guideCard).join("")}</ul>`
        : `<div class="empty"><h2>Guides are coming soon</h2><p>Meanwhile, every company page has its contacts, playbooks and escalation path.</p></div>`}`;
    focusHeading();
  }

  function showScamsSoon() {
    document.title = "Scams | Escalate Anything";
    main.innerHTML = `<div class="page-head">
        <nav class="crumbs" aria-label="Breadcrumb"><a href="#/guides">Guides</a></nav>
        <h1 id="h1" tabindex="-1">Scams</h1>
        <p class="lede">A guide to the scams that use company names, with sources, is coming soon. Meanwhile, a company page shows its scam warnings when the registry has them.</p>
      </div>`;
    focusHeading();
  }

  async function showGuide(key, token) {
    const g = guideFor(key);
    if (!g) return key === "scams" ? showScamsSoon() : showNotFound(`No guide called “${key}”.`);
    document.title = `${g.title || humanize(key)} | Escalate Anything`;
    const head = `<div class="page-head">
        <nav class="crumbs" aria-label="Breadcrumb"><a href="#/guides">Guides</a></nav>
        <h1 id="h1" tabindex="-1">${esc(g.title || humanize(key))}</h1>
        <p class="meta-line">${g.last_verified ? `Checked ${esc(g.last_verified)}. ` : ""}${esc(MD_NOTE)}</p>
      </div>`;
    main.innerHTML = head + skeleton(4);
    focusHeading();
    let text;
    try {
      text = await getText(`guides/${key}.md`);
    } catch (e) {
      if (token !== navToken) return;
      main.innerHTML = head + loadError(g.title || key, `guides/${key}.md`);
      return;
    }
    if (token !== navToken) return;
    const sector = g.sector && SECTOR[g.sector] ? g.sector : null;
    const others = (D.guides || []).filter((x) => x.key !== key);
    main.innerHTML = head + `<div class="layout">
        <article class="md guide-body">${docHtml(stripFrontMatter(text), 2)}</article>
        <aside class="aside" aria-label="Related">
          ${sector ? `<section class="section"><h2>Companies</h2><p class="notes"><a href="#/sector/${esc(sector)}">${plural(sectorCounts[sector] || 0, "company", "companies")} in ${esc(sectorShort(sector))}</a>, each with contacts, playbooks and an escalation path.</p></section>` : ""}
          ${others.length ? `<section class="section"><h2>More guides</h2><ul class="list-plain notes">${others.map((x) => `<li><a href="#/guides/${esc(x.key)}">${esc(x.title || humanize(x.key))}</a></li>`).join("")}</ul></section>` : ""}
          <section class="section"><h2>Data</h2><p class="notes">Markdown: <a class="datafile" href="guides/${esc(key)}.md">guides/${esc(key)}.md</a></p></section>
        </aside>
      </div>`;
    focusHeading();
  }

  // ---- views: agents, not found --------------------------------------------
  function showAgents() {
    document.title = "For agents and developers | Escalate Anything";
    const b = esc(D.base);
    main.innerHTML = `<div class="page-head prose">
        <h1 id="h1" tabindex="-1">For agents and developers</h1>
        <p class="lede">The data behind this site is static JSON. No API key, no account and no MCP server needed.</p>
      </div>
      <div class="prose">
        <h2>Files</h2>
        <ul>
          <li><a href="llms.txt">llms.txt</a>: how to use the data, and the URL of every company file.</li>
          <li><a href="companies.json">companies.json</a>: id, name, aliases, sector and playbook issues for each company.</li>
          <li><code>companies/&lt;id&gt;.json</code>: the company record, every playbook resolved (steps with their channels, evidence, facts, rules) and the escalation ladder. Example: <a href="companies/united-airlines.json">companies/united-airlines.json</a>.</li>
          <li><a href="issues.json">issues.json</a>: issue vocabulary with generic steps and the companies that have a playbook.</li>
          <li><code>states/&lt;code&gt;.json</code>: state agencies with their channels. Example: <a href="states/ny.json">states/ny.json</a>.</li>
          <li><code>dossiers/&lt;id&gt;.md</code> and <code>guides/&lt;key&gt;.md</code>: how complaints actually go at a company and in an industry, as Markdown with a source on every point. The company JSON also has them.</li>
          <li><a href="registry.json">registry.json</a>: everything in one file.</li>
        </ul>
        <pre class="code" style="margin-top:14px"><code>curl ${b}companies/united-airlines.json</code></pre>
        <h2>Rules for agents</h2>
        <ul>
          <li>Use the phone numbers, links and email addresses in the company's file, not ones from a search result or a message.</li>
          <li>Cite only facts and rule points that have a <code>source</code>, and give the source URL. Do not cite a rule whose status is not in force.</li>
          <li>Draft messages and forms. The person approves every message and form submission before it is sent.</li>
          <li>Never enter passwords or payment details. A channel marked sign-in required, CAPTCHA or account holder only needs the person.</li>
          <li>On a call or chat, say that you are an AI assistant acting for the person.</li>
          <li>If a phone number or URL is wrong, <a href="${esc(D.repo)}/issues">report it</a>.</li>
        </ul>
        <h2>Case log and drafting</h2>
        <p>The <a href="${esc(D.repo)}">Escalate Anything MCP server</a> adds a local case log with reference numbers and follow-up dates, draft briefs with citable facts and tone rules, and bill tracking. Run it with <code>escalate serve</code>.</p>
      </div>`;
    focusHeading();
  }

  function showNotFound(msg) {
    document.title = "Not found | Escalate Anything";
    main.innerHTML = `<div class="page-head"><h1 id="h1" tabindex="-1">Not found</h1></div>
      <div class="empty"><p>${esc(msg)}</p><p><a href="#/">Search all companies</a></p></div>`;
    focusHeading();
  }

  // ---- routing ---------------------------------------------------------------
  let navToken = 0;
  let view = "";
  let firstRender = true;

  function focusHeading() {
    if (firstRender) return;
    const h = document.getElementById("h1");
    if (h) h.focus({ preventScroll: true });
  }

  function setNav(name) {
    document.querySelectorAll("[data-nav]").forEach((a) => {
      if (a.dataset.nav === name) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
  }

  const normHash = (h) => (!h || h === "#" ? "#/" : h);

  function route(event) {
    const token = ++navToken;
    const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map((p) => {
      try { return decodeURIComponent(p); } catch (e) { return p; }
    });
    const [a, b, c] = parts;
    // The contact checker was removed. Old links go to the company page or the scam guide.
    if (a === "check") {
      history.replaceState(null, "", b && COMPANY[b] ? `#/c/${encodeURIComponent(b)}` : "#/guides/scams");
      route(event);
      return;
    }
    if (view === "home") {
      ui.homeScroll = window.scrollY;
      ui.homeHash = normHash(event && event.oldURL ? new URL(event.oldURL).hash : "");
    }
    const prev = view;

    if (a === "c" && b) {
      setNav("home");
      if (prev !== "company:" + b) { shownCompany = null; window.scrollTo(0, 0); }
      view = "company:" + b;
      showCompany(b, c, token);
    } else if (a === "issues") {
      setNav("issues"); view = "issues"; window.scrollTo(0, 0); showIssues(b);
    } else if (a === "states" && b) {
      setNav("states"); view = "state"; window.scrollTo(0, 0); showState(b.toLowerCase(), token);
    } else if (a === "states") {
      setNav("states"); view = "states"; window.scrollTo(0, 0); showStates();
    } else if (a === "guides" && b) {
      setNav(b === "scams" ? "scams" : "guides"); view = "guide:" + b; window.scrollTo(0, 0); showGuide(b, token);
    } else if (a === "guides") {
      setNav("guides"); view = "guides"; window.scrollTo(0, 0); showGuides();
    } else if (a === "agents") {
      setNav("agents"); view = "agents"; window.scrollTo(0, 0); showAgents();
    } else {
      setNav("home");
      ui.sector = a === "sector" && b && SECTOR[b] ? b : "";
      document.title = `Escalate Anything: how to get it fixed with ${D.stats.companies} US companies`;
      if (prev !== "home") {
        view = "home";
        renderHome();
        // Back from a company page to the same list: restore the scroll position and focus the card.
        const back = prev.startsWith("company:") && normHash(location.hash) === ui.homeHash;
        window.scrollTo(0, back ? ui.homeScroll : 0);
        const card = back && document.querySelector(`#results a[href="#/c/${prev.slice(8)}"]`);
        if (card && !firstRender) card.focus({ preventScroll: true });
        else focusHeading();
      } else {
        renderResults();
      }
    }
    if (view !== "home" && !view.startsWith("company:")) shownCompany = null;
    firstRender = false;
  }

  // ---- global events -------------------------------------------------------
  main.addEventListener("click", (e) => {
    const copy = e.target.closest("[data-copy]");
    if (copy) {
      navigator.clipboard.writeText(copy.dataset.copy).then(() => {
        const old = copy.textContent;
        copy.textContent = "Copied";
        setTimeout(() => (copy.textContent = old), 1400);
      });
      return;
    }
    const link = e.target.closest("[data-copylink]");
    if (link) {
      const url = D.base + "#/c/" + shownCompany + "/" + link.dataset.copylink;
      if (canCopy) navigator.clipboard.writeText(url).then(() => { link.textContent = "Link copied"; setTimeout(() => (link.textContent = "Copy link to this playbook"), 1600); });
      else history.replaceState(null, "", "#/c/" + shownCompany + "/" + link.dataset.copylink);
      return;
    }
    const jump = e.target.closest("[data-scroll]");
    if (jump) {
      const el = document.getElementById(jump.dataset.scroll);
      if (el) { el.scrollIntoView({ block: "start" }); const h = el.querySelector("h2"); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); } }
      return;
    }
    if (e.target.closest("[data-retry]")) { cache.clear(); view = ""; route(); }
  });

  main.addEventListener("toggle", (e) => {
    const d = e.target;
    if (!d.matches || !d.matches("details.pb[data-issue]") || !shownCompany) return;
    const want = d.open ? `#/c/${shownCompany}/${d.dataset.issue}` : `#/c/${shownCompany}`;
    if (d.open || location.hash === `#/c/${shownCompany}/${d.dataset.issue}`) history.replaceState(null, "", want);
  }, true);

  document.addEventListener("keydown", (e) => {
    if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    const input = document.getElementById("q") || document.getElementById("sq");
    if (input) { e.preventDefault(); input.focus(); input.select(); }
  });

  window.addEventListener("hashchange", route);
  route();
})();
