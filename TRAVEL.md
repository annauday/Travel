# Travel Deal Agent

Searches the web for flight + hotel deals from **Atlanta (ATL)** between **Dec 18, 2026 and Jan 3, 2027**:

| Destination | Trip length | Airports |
|---|---|---|
| Punta Cana | 3 nights | PUJ |
| Cusco | 4 nights | CUZ (via LIM) |
| Cairo | 6 nights | CAI |
| Aspen | 3 nights | ASE, plus DEN / EGE as cheaper alternatives |
| Costa Rica | 4 nights | SJO, LIR |

"N days" is treated as N nights: you leave on day D and return on day D+N, always inside the window.

## Setup

1. Copy `travel_agent.py`, `requirements.txt` and `.github/workflows/travel-deals.yml` into your repo.
2. Add the repo secret `ANTHROPIC_API_KEY` (Settings -> Secrets and variables -> Actions). Web search must be enabled for your API org in the Anthropic Console.
3. Run it: **Actions -> Travel Deals -> Run workflow**. It also runs daily.

## Where results go

- A **tracking issue** labeled `travel-deals`. The first run creates it; later runs add a comment, so GitHub notifies you by email/app.
- The run's **Summary** tab and a downloadable `reports/` artifact.

Each report has a ranked comparison, details per destination with sources, and Google Flights / Kayak links for date pairs across the window so you can confirm live prices.

## Tuning

Set these as env vars in the workflow:

- `TRAVELERS` (default 2, sharing one room)
- `WINDOW_START` / `WINDOW_END` (ISO dates)
- `MAX_SEARCHES_PER_DEST` (default 10; lower it to cut cost)
- `AGENT_MODEL` (default `claude-sonnet-5-5`)

To change destinations or trip lengths, edit the `DESTINATIONS` list at the top of `travel_agent.py`.

## Caveat

The agent reads what web search can find (fare articles, aggregator pages, hotel listings). Live fare engines are dynamic, so some prices will be typical ranges rather than bookable quotes. The agent labels these, and the links in each report are for confirming the real price.
