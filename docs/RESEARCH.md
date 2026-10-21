# Research notes (observed 2026-10-21)

Sources were fetched on 2026-10-21. The GitHub Search API hit its shared hourly rate limit partway through,
so competitor checks after that point used GitHub web pages. Star counts are as displayed at fetch time;
several trending totals looked unusually large and were not independently verified.

## Signals

| Source | Observation |
|---|---|
| [GitHub Trending, weekly](https://github.com/trending?since=weekly) | Most entries are coding-agent infrastructure: `anomalyco/opencode` (219k stars), `stablyai/orca` (fleet of coding agents), `mksglu/context-mode` (context window optimisation, 31.6k), `akitaonrails/ai-memory`, `wshobson/agents`, `anthropics/claude-plugins-official`, `HKUDS/CLI-Anything`, `ruvnet/ruflo`, `K-Dense-AI/scientific-agent-skills`, `cursor/plugins`, `android/skills`, `heygen-com/hyperframes`, `earthtojake/text-to-cad`, `debpalash/VoiceStudio`, `morluto/rea`, `NationalSecurityAgency/ghidra`. |
| GitHub Search API, repos created after 2026-07-21 | `yetone/magpie` (agent model routing), `dzhng/jevgrep` (code search for agents), `Louis-CFM/coucou` (agent monitor), `tigerless-labs/agent-memory`, `Human-Agent-Society/reef`, `monid-ai/monid`. |
| [Hacker News Show HN](https://hn.algolia.com/api/v1/search?tags=show_hn) | Local-inference and developer-tool posts dominate the high-point list (Homebrew 6.0.0, local GLM/Gemma runners, tool-calling distillation). |
| [Context-cost articles](https://www.mindstudio.ai/blog/how-to-manage-claude-code-token-usage) (search results; some are vendor content) | Recurring complaints: large fixed overhead per session, MCP tool definitions, re-sent context dominating bills. Figures quoted there are unverified marketing claims and are not used by this project. |

## Competitors checked

| Repo | What it does | Gap |
|---|---|---|
| [ryoppippi/ccusage](https://github.com/ryoppippi/ccusage) (19.1k stars) | Usage and cost reports from local agent logs | Reports totals; no per-pattern waste analysis |
| [mksglu/context-mode](https://github.com/mksglu/context-mode) (31.6k) | Runtime interception that sandboxes tool output | Prevents at runtime; no post-hoc audit of past sessions |
| [agent-sh/agnix](https://github.com/agent-sh/agnix) (456) | Linter for CLAUDE.md / AGENTS.md / SKILL.md | Static config, not behaviour |
| [skillmds/skillmd](https://github.com/skillmds/skillmd) (250) | Skill search/install/lint | Static config |

## Opportunity matrix

Scores 1-5, weights sum to 100. Weighted score = sum(weight x score) / 5.

| Opportunity | Demand (20) | Differentiation (20) | Feasibility (15) | Usefulness (20) | Maintainability (10) | Testability (15) | **Total** |
|---|---|---|---|---|---|---|---|
| Post-hoc session waste auditor (chosen) | 4 | 5 | 5 | 4 | 4 | 5 | **90** |
| SKILL.md / AGENTS.md linter | 4 | 2 | 5 | 3 | 4 | 5 | 74 |
| MCP tool-definition token budget analyser | 4 | 4 | 3 | 4 | 3 | 3 | 72 |
| Repo "agent-readiness" scorer | 3 | 3 | 4 | 3 | 3 | 4 | 66 |
| Cross-vendor agent memory handoff | 4 | 2 | 3 | 3 | 2 | 3 | 58 |

The scores are the author's judgement from the evidence above, not measured values.
