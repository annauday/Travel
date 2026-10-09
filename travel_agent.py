"""Holiday travel deal hunter: Atlanta -> Punta Cana / Cusco / Cairo / Aspen / Costa Rica.

Runs one web-search research pass per destination, then a final pass that ranks
the results. The report goes to the Actions job summary, reports/*.md, and a
tracking GitHub issue (each run adds a comment, so you get notified).

Set DRY_RUN=1 to print the live-search links only (no API key needed).
"""
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
MAX_SEARCHES = int(os.environ.get("MAX_SEARCHES_PER_DEST", "10"))
TRAVELERS = int(os.environ.get("TRAVELERS", "2"))
WINDOW_START = dt.date.fromisoformat(os.environ.get("WINDOW_START", "2026-12-18"))
WINDOW_END = dt.date.fromisoformat(os.environ.get("WINDOW_END", "2027-01-03"))
ORIGIN = "ATL"

# "nights" = trip length: depart on day D, return on day D + nights.
DESTINATIONS = [
    {
        "name": "Punta Cana, Dominican Republic",
        "airports": ["PUJ"],
        "nights": 3,
        "hotel": "beach resorts; compare all-inclusive vs room-only pricing",
    },
    {
        "name": "Cusco, Peru",
        "airports": ["CUZ", "LIM"],
        "nights": 4,
        "hotel": "well-reviewed hotels near the Plaza de Armas / San Blas",
    },
    {
        "name": "Cairo, Egypt",
        "airports": ["CAI"],
        "nights": 6,
        "hotel": "hotels in Giza with pyramid views or central Cairo/Zamalek",
    },
    {
        "name": "Aspen, Colorado",
        "airports": ["ASE", "DEN", "EGE"],
        "nights": 3,
        "hotel": "Aspen or Snowmass lodging; also consider flying into Denver or Eagle and driving/shuttling",
    },
    {
        "name": "Costa Rica",
        "airports": ["SJO", "LIR"],
        "nights": 4,
        "hotel": "San Jose/Alajuela, Guanacaste beaches (via LIR), or La Fortuna/Arenal",
    },
]


def search_links(dest):
    """Deterministic live-search links for date pairs across the window."""
    code = dest["airports"][0]
    links = []
    d = WINDOW_START
    last_depart = WINDOW_END - dt.timedelta(days=dest["nights"])
    while d <= last_depart:
        r = d + dt.timedelta(days=dest["nights"])
        q = urllib.parse.quote(f"Flights from {ORIGIN} to {code} on {d} through {r}")
        links.append(
            (
                f"{d:%b %d} - {r:%b %d}",
                f"https://www.google.com/travel/flights?q={q}",
                f"https://www.kayak.com/flights/{ORIGIN}-{code}/{d}/{r}/{TRAVELERS}adults",
            )
        )
        d += dt.timedelta(days=3)
    return links


def links_markdown():
    out = ["## Live search links", "", "Prices move fast; use these to confirm before booking.", ""]
    for dest in DESTINATIONS:
        out.append(f"**{dest['name']}** ({dest['nights']} nights)")
        for label, g, k in search_links(dest):
            out.append(f"- {label}: [Google Flights]({g}) · [Kayak]({k})")
        out.append("")
    return "\n".join(out)


def ask(client, prompt, tools=None, max_tokens=3000):
    messages = [{"role": "user", "content": prompt}]
    resp = None
    for _ in range(8):  # pause_turn can interrupt long search turns
        kwargs = dict(model=MODEL, max_tokens=max_tokens, messages=messages)
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    sources = []
    for b in resp.content:
        if b.type == "text":
            for c in getattr(b, "citations", None) or []:
                url = getattr(c, "url", None)
                if url and url not in sources:
                    sources.append(url)
    return text, sources


def research(client, dest):
    prompt = f"""Find the best flight + hotel deals for a trip from Atlanta ({ORIGIN}) to {dest['name']}.

Constraints
- Trip length: exactly {dest['nights']} nights. Depart on/after {WINDOW_START:%b %d, %Y} and return on/before {WINDOW_END:%b %d, %Y}.
- {TRAVELERS} adult traveler(s) sharing one room.
- Airports to consider: {', '.join(dest['airports'])} (from {ORIGIN}).
- Hotels: {dest['hotel']}. Aim for 3 stars or better with solid guest reviews.

How to research
- Search for current fares (Google Flights, Kayak, Skyscanner, airline sites, deal sites like Going, Secret Flying, The Flight Deal) and current hotel rates (Booking, Expedia, Hotels.com, hotel sites) for these dates.
- Compare several departure dates inside the window. Christmas and New Year's dates are usually the most expensive.

Rules
- Only report prices you actually found in a source, and name the source. Never invent a price.
- If you only find a typical range rather than a live quote, label it "typical range, not a live quote".
- Mention airline, nonstop vs connections, and baggage/fees if relevant.

Reply in concise markdown using exactly these labels:
**Best date pair:**
**Flight:** (price per person, airline, stops, source)
**Hotel:** (name, nightly rate, stars/rating, source)
**Estimated total for {TRAVELERS}:**
**Deal rating:** Fantastic / Good / Average / Pricey, plus one line of reasoning versus typical holiday prices
**Confidence:** High / Medium / Low
**Notes:** (visa, altitude, entry rules, anything that changes the cost; max 2 lines)"""
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}]
    return ask(client, prompt, tools=tools)


def synthesize(client, findings):
    blob = "\n\n".join(f"### {name}\n{text}" for name, text in findings)
    prompt = f"""You are writing a holiday travel deal report for a traveler leaving Atlanta between {WINDOW_START:%b %d} and {WINDOW_END:%b %d, %Y} ({TRAVELERS} adults).

Research findings per destination:

{blob}

Write the report in markdown:
1. A 3-4 sentence headline: which trip(s) are the best value right now and whether it is worth booking soon.
2. A comparison table with columns: Destination | Nights | Best dates | Flight pp | Hotel/night | Est. total | Deal | Confidence.
3. "Top picks": a ranked list of the top 3 with one or two sentences each on why.
4. "Heads-up": caveats that matter (low-confidence numbers, visas, connections, peak-season pricing).

Use only facts from the findings. Do not add prices that are not in them. Keep it tight."""
    text, _ = ask(client, prompt, max_tokens=2500)
    return text


# ---- GitHub helpers -------------------------------------------------------
def gh(method, path, body=None):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        method=method,
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or "null")


def post_to_issue(title, body):
    try:
        issues = gh("GET", "/issues?labels=travel-deals&state=open&per_page=1") or []
        if issues:
            gh("POST", f"/issues/{issues[0]['number']}/comments", {"body": body})
        else:
            gh("POST", "/issues", {"title": title, "body": body, "labels": ["travel-deals"]})
    except Exception as e:
        print(f"Could not post to issue: {e}")


def main():
    today = dt.date.today()
    if os.environ.get("DRY_RUN"):
        print(links_markdown())
        return
    if today >= WINDOW_END:
        print("Travel window has passed; nothing to do.")
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set.")

    import anthropic

    client = anthropic.Anthropic()
    findings, all_sources = [], []
    for dest in DESTINATIONS:
        print(f"Researching {dest['name']}...")
        try:
            text, sources = research(client, dest)
        except Exception as e:
            text, sources = f"Research failed: {e}", []
        findings.append((dest["name"], text))
        all_sources += [s for s in sources if s not in all_sources]

    summary = synthesize(client, findings)
    details = "\n\n".join(f"### {n}\n{t}" for n, t in findings)
    src_md = "\n".join(f"- {u}" for u in all_sources[:40]) or "- (none cited)"
    report = (
        f"# Atlanta holiday travel deals - {today:%b %d, %Y}\n\n{summary}\n\n"
        f"## Details by destination\n\n{details}\n\n{links_markdown()}\n\n"
        f"## Sources\n\n{src_md}\n"
    )

    out = pathlib.Path("reports")
    out.mkdir(exist_ok=True)
    (out / f"travel-deals-{today}.md").write_text(report, encoding="utf-8")
    print(report)

    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as f:
            f.write(report)
    post_to_issue(f"Atlanta holiday travel deals ({WINDOW_START:%b %d} - {WINDOW_END:%b %d})", report)


if __name__ == "__main__":
    main()
