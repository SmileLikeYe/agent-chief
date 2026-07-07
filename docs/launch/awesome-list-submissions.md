# awesome-list submission drafts

Ready-to-paste one-liners for the relevant curated lists. Each list sorts
alphabetically inside its section — match the surrounding format when you open
the PR, and keep the description to one line.

## awesome-mcp-servers
Section: *Productivity* (or *Aggregators*)
```
- [agent-chief](https://github.com/SmileLikeYe/agent-chief) 🐍 🏠 - Local-first "chief of staff" that triages agent/CI/RSS/webhook events into interrupt/digest/dispatch/curate/drop; exposes an MCP server (`propose`, `feedback`, `policy`, `stats`) so agents route through one judgment layer instead of pinging you directly.
```
PR note: "Chief's MCP server lets any agent submit a candidate event and obey
the returned Decision — an attention-management layer, not another tool server."

## awesome-claude-code
Section: *Tooling* / *Workflow*
```
- [agent-chief](https://github.com/SmileLikeYe/agent-chief) - An explainable attention layer for your agents: three-stage worthiness engine (rules → similarity → LLM judge) with per-model cost accounting (`chief trace`), a falsifiable preference-learning eval (`chief eval --learning`), and a ships-in-the-wheel Claude Code skill so background work routes through Chief instead of interrupting you.
```

## awesome-selfhosted
Section: *Personal Dashboards* / *Communication - Custom Notifications*
```
- [Chief](https://github.com/SmileLikeYe/agent-chief) - Local-first attention firewall that decides what deserves an interrupt vs a digest vs the floor; three-stage engine, explainable per-decision cost/trace, local web console, learns from 👍/👎 feedback. No cloud, no telemetry. ([Demo](https://github.com/SmileLikeYe/agent-chief#-60-second-quickstart)) `MIT` `Python`
```
Note: awesome-selfhosted requires a license tag and language, and prefers
projects that are installable/runnable — `uvx agent-chief demo` satisfies that.

## Submission checklist per PR
- [ ] Read the list's CONTRIBUTING — alphabetical order, exact bullet format,
      required tags (emoji/license/language) vary by list.
- [ ] One project per PR; link to the repo, not a marketing page.
- [ ] Confirm the demo command in the description actually works from a clean
      machine before submitting (reviewers check).
- [ ] After PyPI publish, some lists prefer `uvx agent-chief` / `pip install`
      over a git link — update the description then.
