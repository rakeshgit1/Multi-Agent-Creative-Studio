import logging
import os
import pathlib

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.tools import FunctionTool
from google.adk.tools.agent_tool import AgentTool
try:
    from .retry import RETRY_CONFIG
    from .display_image_tool import display_image
    from .get_image_links_tool import get_image_links
except ImportError:
    from retry import RETRY_CONFIG
    from display_image_tool import display_image
    from get_image_links_tool import get_image_links

try:
    from .prompt import SYSTEM_INSTRUCTION_TEMPLATE
except ImportError:
    from prompt import SYSTEM_INSTRUCTION_TEMPLATE  # direct execution fallback

try:
    from .observability import setup_observability
except ImportError:
    from observability import setup_observability

logger = logging.getLogger("ai_creative_studio.creative_director")

# Langfuse tracing: agent runs, LLM calls and tool calls, including the A2A calls
# to the specialists (no-op without LANGFUSE_* keys)
setup_observability("creative_director")
logger.setLevel(logging.INFO)


BRANDS_DIR = pathlib.Path(__file__).parent / "brands"


def load_brand_context() -> str:
    """
    Build the brand-context block for the system prompt.

    BRAND_PROFILE selects a file in brands/ (e.g. "mcdonalds" -> brands/mcdonalds.md).
    Returns an empty string when it is unset or the profile is missing, so the
    agent behaves brand-agnostically as before.
    """
    profile = os.getenv("BRAND_PROFILE", "").strip().lower()
    if not profile:
        return ""
    path = BRANDS_DIR / f"{profile}.md"
    if path.parent != BRANDS_DIR or not path.is_file():
        logger.warning("BRAND_PROFILE=%r not found in %s; continuing without a brand", profile, BRANDS_DIR)
        return ""
    return (
        "**Brand Context (applies to every campaign unless the user says otherwise):**\n"
        "Include the following brand profile in the brief you send to EVERY specialist.\n\n"
        + path.read_text(encoding="utf-8").strip()
    )


def create_creative_director():
    """
    Create the Creative Director orchestrator.
    Reads specialist URLs from environment variables at runtime.
    """
    # Read specialist URLs from environment
    copywriter_url = os.getenv("COPYWRITER_AGENT_URL")
    designer_url = os.getenv("DESIGNER_AGENT_URL")
    strategist_url = os.getenv("STRATEGIST_AGENT_URL")
    critic_url = os.getenv("CRITIC_AGENT_URL")
    pm_url = os.getenv("PM_AGENT_URL")

    available_agents_list = []
    agent_tools = [
        FunctionTool(func=display_image),
        FunctionTool(func=get_image_links),
    ]

    # Each configured specialist becomes a RemoteA2aAgent wrapped in an AgentTool.
    specialists = [
        (strategist_url, "brand_strategist",
         "Researches market trends, competitors, and audience insights",
         "Brand strategist for market research and competitive insights"),
        (copywriter_url, "copywriter",
         "Writes Instagram captions, hooks, and hashtags",
         "Copywriter for Instagram captions and hashtags"),
        (designer_url, "designer",
         "Generates campaign images and visual concepts",
         "Designer for campaign image generation"),
        (critic_url, "critic",
         "Reviews content and visuals for quality and brand fit",
         "Critic for reviewing copy and visuals"),
        (pm_url, "project_manager",
         "Builds the campaign timeline and project plan (optional Notion via MCP)",
         "Project manager for campaign timelines and planning"),
    ]
    for url, name, listing, description in specialists:
        if not url:
            continue
        available_agents_list.append(f"- **{name}**: {listing}")
        remote_agent = RemoteA2aAgent(
            name=name,
            description=description,
            agent_card=f"{url}/.well-known/agent.json",
        )
        agent_tools.append(AgentTool(agent=remote_agent))

    available_agents_text = (
        "\n".join(available_agents_list)
        if available_agents_list
        else "No specialist agents configured. Set agent URLs in environment variables."
    )

    system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
        available_agents=available_agents_text,
        brand_context=load_brand_context(),
    )

    from google.genai import types
    generation_config = types.GenerateContentConfig(
        max_output_tokens=20000,
        temperature=0.2,
        http_options=types.HttpOptions(
            retry_options=RETRY_CONFIG,
            timeout=120_000,  # 120 second timeout for model calls
        ),
    )

    agent = Agent(
        name="creative_director",
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        description="Creative Director orchestrator that coordinates specialist agents",
        instruction=system_instruction,
        tools=agent_tools,
        generate_content_config=generation_config,
    )

    # Compact event history so long 5-agent workflows stay within token limits.
    from google.adk.apps import App
    from google.adk.apps.app import EventsCompactionConfig
    from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
    from google.adk.models import Gemini

    compaction_config = EventsCompactionConfig(
        summarizer=LlmEventSummarizer(llm=Gemini(model_id="gemini-2.5-flash")),
        compaction_interval=3,
        overlap_size=1,
    )
    app = App(
        name="creative_director",
        root_agent=agent,
        events_compaction_config=compaction_config,
        plugins=[LoggingPlugin()],
    )
    return agent, app


root_agent, root_app = create_creative_director()
