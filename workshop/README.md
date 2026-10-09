# AI Creative Studio: Workshop

## Build a Multi-Agent Creative Studio with Google's Agent Stack: ADK, A2A, MCP on Cloud Run & Agent Runtime

This directory contains all the materials for the hands-on workshop codelab.

### Directory Structure

```
workshop/
├── diagrams/               # Screenshots and GIFs used in the codelab
├── setup_inspector.sh      # A2A Inspector setup helper
└── starter/                # Starter code given to participants
    ├── agents/             # Agent stubs with TODO comments
    └── deploy/             # Deployment scripts
```

> The published codelab lives in the `docs/` directory at the **repository root** (a sibling of `workshop/`, not inside it).

### What Participants Build

A distributed multimodal multi-agent system for Instagram campaign generation:

| Agent | Platform | Role |
|---|---|---|
| Brand Strategist | Cloud Run | Market research with Google Search |
| Copywriter | Cloud Run | Instagram captions using ADK Skills |
| Designer | Cloud Run | Visual concepts + real image generation via Gemini |
| Critic | Cloud Run | Quality review and structured feedback |
| Project Manager | Cloud Run | Timeline, tasks, and Notion sync via MCP |
| Creative Director | Gemini Enterprise Agent Platform Runtime | Orchestrator that routes tasks via A2A |

### How a campaign flows over A2A

Each specialist is an independent service with its own HTTPS endpoint. The Creative Director (deployed to Gemini Enterprise Agent Platform Runtime) calls them over the **A2A protocol** as remote agents, one step at a time, and only advances past the Critic once the review comes back `APPROVED`. The Project Manager optionally syncs the resulting tasks to Notion through an MCP toolset.

```mermaid
sequenceDiagram
    actor User
    participant CD as Creative Director (Agent Runtime)
    participant BS as Brand Strategist
    participant CW as Copywriter
    participant DS as Designer
    participant CR as Critic
    participant PM as Project Manager

    User->>CD: Campaign brief
    CD->>BS: A2A: research audience & trends
    BS-->>CD: Insights
    CD->>CW: A2A: write captions (ADK Skill)
    CW-->>CD: Posts
    CD->>DS: A2A: generate visuals
    DS-->>CD: Image URIs (GCS)
    CD->>CR: A2A: review copy & visuals
    CR-->>CD: Score (APPROVED / NEEDS_REVISION)
    opt If NEEDS_REVISION
        CD->>CW: A2A: revise posts with feedback
        CW-->>CD: Revised posts
        CD->>CR: A2A: re-review
        CR-->>CD: APPROVED
    end
    CD->>PM: A2A: build timeline (optional Notion via MCP)
    PM-->>CD: Campaign plan
    CD-->>User: Complete Instagram campaign
```

### Workshop Details

| | |
|---|---|
| **Duration** | ~2.5 hours |
| **Level** | Intermediate |
| **Environment** | GCP Cloud Shell |
| **Topics** | Google ADK, ADK Skills, A2A Protocol, MCP, Multimodal, Cloud Run, Gemini Enterprise Agent Platform Runtime |

### Prerequisites for Participants

- Google Cloud project with billing enabled
- Owner or Editor IAM role
- (Optional) Notion account for MCP integration
- (Optional) [Langfuse](https://langfuse.com) account for tracing (free tier is enough)

### Starter Code

The `starter/` directory contains the code participants start from:

- Agent files have numbered `# TODO` comments guiding participants through each implementation step
- Deploy scripts are fully functional; participants only implement agent logic
- Pre-written infrastructure includes retry config, error handling callbacks, and MCP toolset setup

### Observability with Langfuse

Every agent can send traces to [Langfuse](https://langfuse.com): agent runs, every LLM call, and every tool call (including the A2A calls from the Creative Director to the specialists). A whole campaign shows up as **one trace** across all six agents.

1. Create a Langfuse project and copy its API keys.
2. Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` in `starter/.env` (see `.env.example`). Leave the keys empty to run without tracing.
3. Run or deploy as usual. The deploy scripts store the secret key in Secret Manager and pass the settings to Cloud Run and Agent Runtime.

How it works: each agent folder has an `observability.py` (copied per agent, like `retry.py`, because every agent is its own Docker image). `agent.py` calls `setup_observability("<agent>")`, which turns on the OpenInference ADK instrumentor and OpenTelemetry HTTP instrumentation. Langfuse uses its own `TracerProvider`, so it keeps working next to Cloud Trace on Agent Runtime. Without the keys, all of it is a no-op.

### Published Codelab

The codelab is published via GitHub Pages at [ani-in.github.io/Multi-Agent-Creative-Studio](https://ani-in.github.io/Multi-Agent-Creative-Studio/).

The `docs/` directory (at the repository root) is the GitHub Pages source. Commit changes there to publish updates.
