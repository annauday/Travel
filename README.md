# GitHub AI Agent

A small Claude-powered agent that lives in your repo and runs on GitHub Actions. It can list, read and write files in the checkout, and optionally run shell commands. If it changes files, it opens a pull request for you to review.

## Setup (2 minutes)

1. Copy these files into your repo (keep the paths):
   - `agent.py`
   - `requirements.txt`
   - `.github/workflows/agent.yml`
2. Add your API key: **Settings → Secrets and variables → Actions → New repository secret**, name it `ANTHROPIC_API_KEY`.
3. Allow PRs from Actions: **Settings → Actions → General → Workflow permissions** → "Read and write permissions" and tick "Allow GitHub Actions to create and approve pull requests".

## Ways to run it

| Trigger | How |
|---|---|
| Manual | **Actions → AI Agent → Run workflow**, type a task |
| Chat-style | Comment `@agent fix the typos in the docs` on any issue or PR (owners, members and collaborators only) |
| Scheduled | Runs daily at 13:00 UTC. Set the repo variable `SCHEDULED_TASK` to change what it does |

Results appear in the run's **Summary** tab and as an issue comment when triggered from an issue.

## Configuration

Environment variables (set in the workflow):

- `AGENT_MODEL` — defaults to `claude-sonnet-5-5`
- `AGENT_MAX_TURNS` — defaults to `15`
- `AGENT_ALLOW_SHELL` — `true` enables the `run_command` tool (off by default)

## Safety notes

- File access is sandboxed to the repo checkout, and `.git` is blocked.
- Shell access is off by default; enable it only for trusted triggers.
- Comment triggers are limited to trusted author associations so strangers can't drive the agent.
- Changes always land in a PR, never directly on your default branch.

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
TASK="Summarize this repo" python agent.py
```
