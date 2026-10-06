# AGENT.md

Guidance for AI coding agents (and humans) working in this repository.

## Project overview

**AI Creative Studio** turns one campaign brief into a complete Instagram campaign using six collaborating agents built on Google ADK, the A2A protocol and MCP. It is deployed as five Cloud Run specialists plus one orchestrator on Vertex AI Agent Engine.

This repo is a **teaching scaffold** (a capstone based on the Google codelab "Build a Multi-Agent Creative Studio with Google's Agent Stack"). The deploy scripts and infrastructure are complete. The agent logic in `workshop/starter/agents/` has guided `# TODO` markers that are meant to be implemented.

```
User / run_campaign.py
        │
        ▼
Creative Director  (Vertex AI Agent Engine, ADK App + LoggingPlugin)
  tools: display_image, get_image_links, + AgentTool(RemoteA2aAgent) × 5
        │  A2A over HTTPS (agent card at /.well-known/agent.json)
        ├─► brand_strategist   (Cloud Run) google_search
        ├─► copywriter         (Cloud Run) ADK Skill: instagram-copywriting
        ├─► designer           (Cloud Run) generate_image → Gemini image model → GCS
        ├─► critic             (Cloud Run) review_image → Gemini multimodal (Part.from_uri)
        └─► project_manager    (Cloud Run) Notion MCP (stdio, notion-mcp-server via npm)
                                after_tool_callback rewrites Notion errors
```

Campaign flow: Strategist → Copywriter → Designer → Critic → (at most one revision round) → Project Manager.

## Tech stack

| Layer | Tech |
|---|---|
| Agent framework | `google-adk[a2a]==1.31.1` (pinned, keep it pinned), `google-genai` |
| Models | `GEMINI_MODEL` (default `gemini-3-flash-preview`), `GEMINI_IMAGE_MODEL` (`gemini-3.1-flash-image`), Vertex AI with `GOOGLE_CLOUD_LOCATION=global` |
| Agent-to-agent | A2A: `to_a2a()` + uvicorn on each specialist; `RemoteA2aAgent` wrapped in `AgentTool` in the orchestrator |
| External tools | MCP over stdio (`@notionhq/notion-mcp-server@1.9.1`) |
| Runtime | Cloud Run (specialists), Vertex AI Agent Engine (orchestrator), GCS (images), Secret Manager (Notion) |
| Observability | OpenTelemetry + ADK tracing |
| Python | >= 3.11, managed with `uv` |

## Repository layout

```
README.md, LICENSE, NOTICE        Project docs; Apache-2.0 (keep upstream notices)
docs/                             Prebuilt static codelab (GitHub Pages) — generated, do not hand-edit
workshop/
  README.md                       Workshop overview
  setup_inspector.sh              Installs A2A Inspector to ~/a2a-inspector
  diagrams/                       Architecture images and screenshots
  starter/                        <- all runnable code lives here
    pyproject.toml                Local dev dependencies
    .env.example                  Config template (copy to .env, which is git-ignored)
    run_campaign.py               Runs an end-to-end campaign against the deployed Agent Engine
    agents/
      creative_director/          Orchestrator: agent.py, prompt.py, display_image_tool.py,
                                  get_image_links_tool.py, retry.py
      brand_strategist/           Research agent (google_search)
      copywriter/                 Caption agent + skills/instagram-copywriting/
      designer/                   Visual agent + image_gen_tool.py
      critic/                     QA agent + image_review_tool.py (Pydantic structured output)
      project_manager/            Timeline agent + Notion MCP + handle_notion_error callback
    deploy/
      deploy_all_specialists.py   Deploys the 5 specialists to Cloud Run (sequentially), writes *_AGENT_URL to .env
      deploy_orchestrator.py      Deploys the orchestrator to Agent Engine (deploy | test | cleanup)
      env_utils.py                .env loading / rewriting helpers
      teardown_gcp.sh             Deletes all GCP resources (interactive)
```

## Commands

Run everything from `workshop/starter/`.

```bash
uv sync                                         # install deps
cp .env.example .env                            # then fill in values
gcloud auth application-default login           # ADC for local runs

uv run adk web agents --allow_origins='*'       # ADK dev UI, chat with any agent
uv run python agents/<agent>/agent.py           # run one specialist as an A2A server (card at /.well-known/agent.json)

uv run python deploy/deploy_all_specialists.py  # deploy 5 specialists to Cloud Run
uv run python deploy/deploy_orchestrator.py --action deploy [--auto-deploy-specialists]
uv run python deploy/deploy_orchestrator.py --action test
uv run run_campaign.py                          # end-to-end campaign against Agent Engine
bash deploy/teardown_gcp.sh                     # tear down (asks for confirmation)
```

There is **no test suite and no CI** (intentional, per the README). To verify a change, run the agent in `adk web` or run `run_campaign.py` against a deployment.

## Configuration

All configuration is read from `workshop/starter/.env`. See `.env.example` for the full list.

- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_PROJECT_NUMBER`: the GCP project.
- `GOOGLE_CLOUD_LOCATION`: the **model** endpoint (`global` for preview models). It is not a deploy region.
- `CLOUD_RUN_REGION`: the **deploy** region for Cloud Run and Agent Engine. It must be a real region. Never mix it up with `GOOGLE_CLOUD_LOCATION`.
- `GCS_IMAGES_BUCKET`, `SIGNING_SERVICE_ACCOUNT`: image storage and signed URLs.
- `*_AGENT_URL`, `AGENT_ENGINE_ID`, `AGENT_ENGINE_RESOURCE_NAME`: filled in automatically by the deploy scripts.
- `NOTION_TOKEN`, `NOTION_PROJECT_DATABASE_ID`, `NOTION_TASKS_DATABASE_ID`: optional. The PM agent needs **all three** to enable Notion.

## Code conventions

- **Each agent is deployed independently.** Each agent directory has its own `Dockerfile`, `pyproject.toml` and `retry.py`. The duplication is deliberate: do not extract shared modules across agent directories, because each Cloud Run build only sees its own folder.
- **Dual imports.** Agents use `try: from .x import y / except ImportError: from x import y` so they work both as a package (`adk web`, Agent Engine) and as a script (`python agent.py` in the container). Keep this pattern.
- Each specialist exposes `root_agent`. The orchestrator also exposes `root_app` (an ADK `App`), which `deploy_orchestrator.py` imports.
- Every `Agent` receives `generate_content_config=GENERATE_CONTENT_CONFIG` from its `retry.py`, which handles retries for 429/500/503/504.
- Tools return `{"status": "success" | "error", ...}` dicts (the Critic returns the `ImageReviewResult` Pydantic model). Tools catch exceptions and return errors; they do not raise.
- The Critic's output format is **parsed by the orchestrator prompt** (`POSTS REVIEW` / `VISUALS REVIEW` / `OVERALL ASSESSMENT`, `APPROVED` / `NEEDS_REVISION`). If you change one side, change the other in `creative_director/prompt.py`.
- Model names come from env vars (`GEMINI_MODEL`, `GEMINI_IMAGE_MODEL`). Do not hardcode new model IDs.
- Never commit `.env`, service-account keys or Notion tokens. Secrets go to Secret Manager through the deploy script.

## Implementation TODOs (the capstone work)

| File | What to implement | Current behavior |
|---|---|---|
| `agents/brand_strategist/agent.py` | `SYSTEM_INSTRUCTION`, `instruction`, `description`, `tools=[google_search]` | Runs with no instruction or tools |
| `agents/copywriter/agent.py` | Import `load_skill_from_dir` / `skill_toolset`, load `skills/instagram-copywriting`, add the `SkillToolset` to `tools` | `tools=[]` |
| `agents/designer/image_gen_tool.py` | genai client call → extract `inline_data` bytes → upload to GCS → `gcs_uri` | Always returns "Image generation incomplete" |
| `agents/critic/image_review_tool.py` | `Part.from_uri` → structured `generate_content` → `ImageReviewResult` | Returns `None` |
| `agents/project_manager/agent.py` | System instruction; plain agent; `McpToolset` + `StdioConnectionParams` for Notion | Runs with no instruction or tools |
| `agents/creative_director/agent.py` | `RemoteA2aAgent` + `AgentTool` for each `*_AGENT_URL`; `App` with `EventsCompactionConfig` | Only has the image tools |

Suggested order: strategist → copywriter → designer → critic → PM → orchestrator. Test each one alone in `adk web` before deploying.

## Known issues (not yet fixed)

### Correctness
1. **`display_image` hides bad URIs.** In `creative_director/display_image_tool.py`, a malformed `gcs_uri` raises `ValueError` while splitting into bucket and path. The `except ValueError` meant for "no artifact service" catches it and returns `status: success`.
2. **`teardown_gcp.sh` uses the wrong env var names.** It reads `GCP_PROJECT_ID`/`PROJECT_ID` and `GCP_REGION`/`LOCATION`, but `.env.example` defines `GOOGLE_CLOUD_PROJECT` / `CLOUD_RUN_REGION`. The embedded Python therefore gets an empty project. The script also hardcodes `${PROJECT_ID}-campaign-images` instead of `GCS_IMAGES_BUCKET`.
3. **The Agent Engine delete calls disagree.** `deploy_orchestrator.py` (cleanup) calls `client.agent_engines.delete(resource_name=...)`, while the teardown script uses `name=..., force=True`. Verify against the vertexai `Client` API.
4. **The Notion checks disagree.** The deploy script stores Notion secrets when only the token and project DB are set. The PM agent requires the tasks DB too, so it silently runs without Notion.

### Reliability
5. **The Designer can hit Cloud Run's timeout.** Cloud Run `--timeout=300` is shorter than the Designer's worst case: 3 images in sequence, each with a 180s timeout and up to 5 retries at 30/60/120/240s backoff.
6. **Some workflow control lives only in the prompt.** The "max 1 revision round" limit and "wait 30 seconds and retry" exist only in the orchestrator prompt. Consider ADK `SequentialAgent` / `LoopAgent` or session-state flags.
7. **Prompts assume conversation history that A2A doesn't send.** The Copywriter and Designer instructions say "the conversation history above contains…", but remote A2A agents receive no history. The orchestrator has to pass all context explicitly in each request.
8. **`deploy_orchestrator.py` is fragile.** It runs `gcloud projects describe` when the module is imported, even for `test` and `cleanup`. Its console output also contains leftover "single-stage vs two-stage deployment" experiment text.

### Security and cost
9. **All specialists are public.** They are deployed with `--allow-unauthenticated`, so anyone with a URL can use your model quota, write to the bucket (Designer) or write to Notion (PM). For production, require IAM auth and send ID tokens from the orchestrator.
10. **Traces store full message content.** The OTel settings record every prompt and response in traces. Turn this off for real customer data.
11. **Some IAM grants may be missing.** Only the Designer gets `storage.objectCreator`. The orchestrator also needs GCS read access and the ability to sign as the compute service account (`iam.serviceAccountTokenCreator`).

### Hygiene
12. **Builds are not reproducible.** There are no lockfiles except `designer/uv.lock`, the Dockerfiles use `uv:latest`, and the `google-genai` minimum differs between local (`>=1.51`) and Agent Engine (`>=1.70`).
13. **`vertexai` is not declared.** It is imported by `run_campaign.py` and `deploy_orchestrator.py` but missing from `starter/pyproject.toml`; it currently arrives through `google-adk`'s dependencies.
14. **The caption count is inconsistent.** `SKILL.md` asks for 3–5 captions; the Copywriter instruction says exactly 3.
15. **There are no unit tests.** Good first targets: GCS URI parsing, `env_utils.update_env_file_with_urls`, `handle_notion_error`.

## Guardrails for agents

- Do not edit `docs/` by hand. It is the generated codelab.
- Do not remove the Apache-2.0 copyright headers or `NOTICE` attributions.
- Do not run `deploy/*` or `teardown_gcp.sh` without explicit user approval. They create, modify or delete billable GCP resources and rewrite `.env`.
- Keep `google-adk` pinned unless you are deliberately upgrading it and testing all six agents.
