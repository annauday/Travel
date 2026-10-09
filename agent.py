"""A small tool-using AI agent designed to run inside GitHub Actions.

Reads its task from the TASK env var, works inside the repo checkout,
and reports back to the job summary and (optionally) an issue comment.
"""
import json
import os
import pathlib
import subprocess
import urllib.request

import anthropic

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "15"))
ALLOW_SHELL = os.environ.get("AGENT_ALLOW_SHELL", "false").lower() == "true"
ROOT = pathlib.Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()

SYSTEM = (
    "You are an autonomous repo assistant running inside a GitHub Actions job. "
    "You can inspect and edit files in the checked-out repository using your tools. "
    "Work step by step, keep changes minimal, and finish with a short summary "
    "of what you found or changed."
)

TOOLS = [
    {
        "name": "list_files",
        "description": "List files in the repo, optionally under a subdirectory.",
        "input_schema": {
            "type": "object",
            "properties": {"directory": {"type": "string", "default": "."}},
        },
    },
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file from the repo.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a text file in the repo.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
]
if ALLOW_SHELL:
    TOOLS.append(
        {
            "name": "run_command",
            "description": "Run a shell command in the repo root (60s timeout).",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        }
    )


def safe_path(rel: str) -> pathlib.Path:
    p = (ROOT / rel).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError("path escapes the repository")
    if ".git" in p.relative_to(ROOT).parts:
        raise ValueError(".git is off limits")
    return p


def run_tool(name: str, args: dict) -> str:
    try:
        if name == "list_files":
            base = safe_path(args.get("directory", "."))
            files = [
                str(f.relative_to(ROOT))
                for f in sorted(base.rglob("*"))
                if f.is_file() and ".git" not in f.relative_to(ROOT).parts
            ]
            return "\n".join(files[:500]) or "(empty)"
        if name == "read_file":
            return safe_path(args["path"]).read_text(encoding="utf-8")[:50_000]
        if name == "write_file":
            p = safe_path(args["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8")
            return f"wrote {args['path']}"
        if name == "run_command" and ALLOW_SHELL:
            r = subprocess.run(
                args["command"], shell=True, cwd=ROOT,
                capture_output=True, text=True, timeout=60,
            )
            return (r.stdout + r.stderr)[-10_000:] or "(no output)"
        return f"unknown tool {name}"
    except Exception as e:  # return errors to the model so it can recover
        return f"error: {e}"


def run_agent(task: str) -> str:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": task}]
    for _ in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL, max_tokens=4096, system=SYSTEM,
            tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                print(f"[tool] {block.name} {json.dumps(block.input)[:200]}")
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": run_tool(block.name, block.input),
                    }
                )
        messages.append({"role": "user", "content": results})
    return "Stopped: reached the maximum number of turns."


def post_issue_comment(body: str) -> None:
    repo, number, token = (
        os.environ.get("GITHUB_REPOSITORY"),
        os.environ.get("ISSUE_NUMBER"),
        os.environ.get("GITHUB_TOKEN"),
    )
    if not (repo and number and token):
        return
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{number}/comments",
        data=json.dumps({"body": body}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        method="POST",
    )
    urllib.request.urlopen(req)


if __name__ == "__main__":
    task = os.environ.get("TASK", "").replace("@agent", "").strip()
    if not task:
        raise SystemExit("No TASK provided.")
    answer = run_agent(task)
    print(answer)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## Agent result\n\n{answer}\n")
    post_issue_comment(answer)
