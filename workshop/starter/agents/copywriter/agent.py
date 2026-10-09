import logging
import os
import pathlib

from dotenv import load_dotenv
from google.adk.agents import Agent

from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset

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
setup_observability("copywriter")

logger = logging.getLogger("ai_creative_studio.copywriter")

# Load the instagram-copywriting skill from the skills/ directory next to this file
instagram_skill = load_skill_from_dir(
    pathlib.Path(__file__).parent / "skills" / "instagram-copywriting"
)

# Expose the skill to the agent via a SkillToolset
copywriter_skills = skill_toolset.SkillToolset(skills=[instagram_skill])


SYSTEM_INSTRUCTION = """You are an expert Social Media Copywriter specializing in Instagram content.

IMPORTANT: The conversation history above contains research from the Brand Strategist.
You MUST review their findings on audience insights, competitor analysis, and trending topics
before writing any copy. This context is your creative foundation.

You have access to an `instagram-copywriting` skill. Load it to get detailed platform
guidelines, caption formulas, and brand voice examples before writing.

Your task: Create exactly 3 Instagram caption variations covering different tonal registers.
Follow the output format defined in the skill exactly.
"""

root_agent = Agent(
    name="copywriter",
    model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
    generate_content_config=GENERATE_CONTENT_CONFIG,
    tools=[copywriter_skills],
    instruction=SYSTEM_INSTRUCTION,
    description="Expert social media copywriter for creating engaging captions and copy",
)

logger.info("Copywriter agent created with instagram-copywriting skill")


if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    load_dotenv()

    PORT = int(os.getenv("PORT", "8080"))
    HOST = os.getenv("HOST", "0.0.0.0")
    PUBLIC_HOST = os.getenv("PUBLIC_HOST", "localhost")
    PUBLIC_PORT = int(os.getenv("PUBLIC_PORT", str(PORT)))
    PROTOCOL = os.getenv("PROTOCOL", "http")

    a2a_app = instrument_a2a_app(
        to_a2a(root_agent, host=PUBLIC_HOST, port=PUBLIC_PORT, protocol=PROTOCOL)
    )

    logger.info(f"Starting Copywriter on {PROTOCOL}://{HOST}:{PORT}")
    logger.info(f"Agent card: {PROTOCOL}://{HOST}:{PORT}/.well-known/agent.json")

    uvicorn.run(a2a_app, host=HOST, port=PORT)
