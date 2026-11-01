# Demo Guide: AI Creative Studio

A first-timer's guide to demoing the Multi-Agent Creative Studio. Plan for a 10 to 12 minute demo plus questions.

Everything below is based on the repo and your `.env`. I have **not** run the ADK web UI or a full campaign on this machine, so do the dry run in Step 3 before the real thing.

Your current setup (from `.env`): project `multi-agent-creative-studio-ik`, region `us-central1`, model `gemini-3.8-flash`, `BRAND_PROFILE=mcdonalds`, Notion and Langfuse keys set (Langfuse region: US).

---

## The story to tell (30 seconds)

> "Marketing teams juggle research, copy, visuals, review and project planning. I built a studio of six AI agents that do this together. A Creative Director agent coordinates five specialists, and each specialist is its own service on Google Cloud, talking over the A2A protocol."

The six agents:

| Agent | Job |
|---|---|
| Creative Director | Orchestrator. Runs the campaign, enforces the Critic's verdict |
| Brand Strategist | Researches audience, competitors, trends (Google Search) |
| Copywriter | Writes 3 Instagram captions |
| Designer | Generates images, stores them in Cloud Storage |
| Critic | Scores captions and images; APPROVED or NEEDS_REVISION |
| Project Manager | Timeline, tasks, budget; writes to Notion (MCP) |

---

## Step 1: The day before (setup)

1. Check Google Cloud credentials still work:
   ```bash
   gcloud auth application-default login
   gcloud config set project multi-agent-creative-studio-ik
   ```
2. Confirm the five services are deployed:
   ```bash
   gcloud run services list --region us-central1 --project multi-agent-creative-studio-ik
   ```
3. Check that billing is on and you have no quota surprises. Image generation is the most likely place to hit one.
4. Run `uv sync` in `workshop/starter` once on good wifi so dependencies are cached.
5. Open Langfuse (https://us.cloud.langfuse.com) and Notion, and check you're logged in to both.
6. **Decide your brand.** `BRAND_PROFILE=mcdonalds` means every campaign is McDonald's-flavoured. Change it to `ecoflow` in `.env` if you'd rather demo the water bottle. Leave it empty for a brand-neutral run.

---

## Step 2: Right before the demo (10 minutes ahead)

**Warm up the agents.** Cloud Run services scale to zero. The Designer took about 40 seconds and the Project Manager about 60 seconds on a cold start when I tested.

```bash
cd workshop/starter
set -a; source .env; set +a
for url in "$STRATEGIST_AGENT_URL" "$COPYWRITER_AGENT_URL" "$DESIGNER_AGENT_URL" \
           "$CRITIC_AGENT_URL" "$PM_AGENT_URL"; do
  curl -s -m 120 -o /dev/null -w "%{http_code}  $url\n" "$url/.well-known/agent.json"
done
```

You want five `200` lines.

**Start the UI:**
```bash
uv run adk web agents --allow_origins='*'
```
Open `http://localhost:8000` and pick `creative_director` from the dropdown. The orchestrator runs on your laptop and calls the deployed specialists.

**Open these tabs, in this order:**
1. ADK web UI (main stage)
2. One agent card in the browser, e.g. `<CRITIC_AGENT_URL>/.well-known/agent.json`
3. Langfuse Traces
4. Notion project database
5. Google Cloud console, Cloud Run services page

Close everything else. Turn off notifications. Zoom the browser to about 125% so the room can read it.

---

## Step 3: Dry run (do this once, the day before)

Run the whole demo once, start to finish, with the exact brief you'll use. Time it. A full campaign (research, 3 captions, images, review, plan) can take several minutes; I don't know how long yours takes, so measure it.

Note down:
- how long it took
- whether images showed up inline
- whether the Critic asked for a revision
- the Langfuse trace and Notion entries that appeared

---

## Step 4: The demo script

### Part A: The idea (1 min)
Show the architecture diagram in the README (`workshop/diagrams/`). Say the one-line story above.

### Part B: Show the agents are real services (2 min)
1. Show the Cloud Run page: five separate services.
2. Open one agent card in the browser. Say: "This is the agent's business card. Any other agent can discover what it does, and that's the A2A protocol."
3. Point out it's JSON with a name, description and skills.

### Part C: Run a campaign (4 to 5 min)
1. In ADK web, select `creative_director`.
2. Paste a short brief, for example:
   ```
   Create a complete Instagram campaign for:
   - Product: EcoFlow Smart Water Bottle (tracks hydration, keeps drinks cold 24h)
   - Target Audience: Health-conscious millennials, 25-35
   - Goal: Brand awareness + drive website traffic
   - Brand Voice: Motivational, clean, science-backed
   - Budget: $3,000
   - Timeline: Launch in 2 weeks
   ```
   (With `BRAND_PROFILE=mcdonalds`, use a McDonald's-style brief instead, or switch the profile.)
3. While it works, **narrate what's happening**: "It's asking the Brand Strategist for research first... now the Copywriter... now the Designer." The events panel in ADK web shows each call.
4. When the Critic returns, point out the verdict. If it says `NEEDS_REVISION`, that's the best moment of the demo: say "the orchestrator can't ignore this, it has to revise and re-review, up to two rounds."

### Part D: Behind the scenes (2 min)
1. **Langfuse:** open the trace. "One campaign is one trace across all six agents. I can see every LLM call and tool call."
2. **Notion:** open the project database. "The Project Manager used MCP to create the project and tasks here."
3. **Images:** open one generated image.

### Part E: Close (30 sec)
- What you'd do next (see "Next steps" below)
- Invite questions

---

## Step 5: Backup plan (important for a first demo)

Things go wrong in live demos. Prepare for it.

| If this happens | Do this |
|---|---|
| Wifi drops or is slow | Switch to a screen recording or screenshots you captured during the dry run. **Record your dry run.** |
| Campaign is slow | Fill the time by explaining the architecture. Don't stare at a spinner |
| An agent times out | Cold start. Say so, wait, or re-send the message |
| Images don't show inline | Ask the Creative Director for the image links; it has a tool that returns signed URLs |
| Notion write fails | The Project Manager is built to report Notion errors; show the timeline in the chat instead |
| Everything breaks | Show the README screenshots and GIF (`workshop/diagrams/adkweb-fullcampain.gif`) |

Save these before the demo: a screen recording of a full successful run, plus screenshots of the final output, the Langfuse trace and the Notion page.

---

## Step 6: Likely questions

- **Why separate services instead of one big agent?** Each specialist can be scaled, deployed and replaced independently; A2A is the standard way they talk.
- **What is MCP doing here?** It connects the Project Manager to Notion without custom integration code.
- **How do you stop it producing bad content?** The Critic scores every deliverable and the orchestrator must act on it.
- **Does it cost a lot?** I don't have cost numbers. Don't quote one. Say you'd measure it before production.
- **Where does the data go?** Prompts and outputs go to Vertex AI (Gemini). Traces go to Langfuse's US region. Both worth knowing.
- **Why not a custom UI?** The dev UI shows tool calls clearly; a custom UI or A2UI would be a next step.

---

## Next steps to mention

- A custom front end (e.g. a caption approval card for the Critic's loop)
- More brand profiles
- Cost and latency tuning
- Warm instances for the slow cold-start services

---

## Checklist

- [ ] Credentials work (`gcloud auth application-default login`)
- [ ] Five Cloud Run services listed
- [ ] Agents warmed up, five `200`s
- [ ] `adk web` running, `creative_director` selected
- [ ] Dry run done and timed
- [ ] Backup recording and screenshots saved
- [ ] Langfuse, Notion, Cloud Run tabs open
- [ ] Brand profile chosen and brief matches it
- [ ] Notifications off, browser zoomed
