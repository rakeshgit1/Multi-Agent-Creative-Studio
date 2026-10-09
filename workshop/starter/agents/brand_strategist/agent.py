import datetime
import logging
import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.google_search_tool import google_search
try:
    from .retry import GENERATE_CONTENT_CONFIG
except ImportError:
    from retry import GENERATE_CONTENT_CONFIG

try:
    from .observability import instrument_a2a_app, setup_observability
except ImportError:
    from observability import instrument_a2a_app, setup_observability

load_dotenv()

# Langfuse tracing: agent runs, LLM calls and tool calls (no-op without LANGFUSE_* keys)
setup_observability("brand_strategist")

logger = logging.getLogger("ai_creative_studio.brand_strategist")

TODAY = datetime.date.today()

SYSTEM_INSTRUCTION = f"""You are the Brand Strategist, a RESEARCH-ONLY agent in an AI creative studio.
Today's date is {TODAY.strftime("%B %d, %Y")}. The current year is {TODAY.year}.

YOUR JOB
Given a product or brand brief, research the market with the google_search tool and report your findings.

RESEARCH STEPS
1. Audience: search for who the target audience is, what they care about, and how they behave online.
2. Competitors: analyze 2-3 competitor brands (positioning, tone, messaging, visual style).
3. Trends: identify 3-5 trending topics in the product category.

SEARCH RULES
- ALWAYS include the current year ({TODAY.year}) in every search query, for example "sustainable sneakers audience trends {TODAY.year}".
- Prefer recent, credible sources and do not invent facts. If something cannot be found, say so.

OUTPUT FORMAT
Return exactly these four labelled sections, in this order:

**Audience Insights:**
(demographics, interests, motivations, platforms)

**Competitive Analysis:**
(2-3 competitors, with what each does well and where the gaps are)

**Trending Topics:**
(3-5 topics, each with a one-line note on why it matters)

**Key Strategic Insights:**
(3-5 actionable conclusions that the rest of the team can build on)

STRICT CONSTRAINTS
- You are RESEARCH ONLY. DO NOT write captions, copy, slogans, taglines, or hashtags.
- DO NOT create, describe, or suggest designs, images, or visual concepts.
- If asked for captions or designs, decline that part, deliver the research, and note that the Creative Director coordinates the next steps.
"""

root_agent = Agent(
    name="brand_strategist",
    model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
    generate_content_config=GENERATE_CONTENT_CONFIG,
    instruction=SYSTEM_INSTRUCTION,
    description=(
        "Research-only brand strategist. Uses Google Search to return Audience Insights, "
        "Competitive Analysis, Trending Topics, and Key Strategic Insights. "
        "Does not write captions or designs."
    ),
    tools=[google_search],
)

logger.info("Brand Strategist agent created")


if __name__ == "__main__":
    import uvicorn
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    PORT = int(os.getenv("PORT", "8082"))
    HOST = os.getenv("HOST", "0.0.0.0")
    PUBLIC_HOST = os.getenv("PUBLIC_HOST", "localhost")
    PUBLIC_PORT = int(os.getenv("PUBLIC_PORT", str(PORT)))
    PROTOCOL = os.getenv("PROTOCOL", "http")

    a2a_app = instrument_a2a_app(
        to_a2a(root_agent, host=PUBLIC_HOST, port=PUBLIC_PORT, protocol=PROTOCOL)
    )

    logger.info(f"Starting Brand Strategist on {PROTOCOL}://{HOST}:{PORT}")
    logger.info(f"Agent card: {PROTOCOL}://{HOST}:{PORT}/.well-known/agent.json")

    uvicorn.run(a2a_app, host=HOST, port=PORT)
