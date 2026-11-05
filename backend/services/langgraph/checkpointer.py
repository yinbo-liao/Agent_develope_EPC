"""
LangGraph Checkpointer factory — persistent state storage for AI workflows.

Supports:
- memory: InMemorySaver (default, dev only — lost on restart)
- postgres: AsyncPostgresSaver (production — survives restarts)
- sqlite: SqliteSaver (alternative — file-based persistence)
"""

import logging
from config import settings

logger = logging.getLogger(__name__)


async def create_checkpointer():
    """Create a LangGraph checkpointer based on FPSO_LANGGRAPH_CHECKPOINTER setting."""
    checkpointer_type = settings.langgraph_checkpointer

    if checkpointer_type == "postgres":
        try:
            from langgraph_checkpoint_postgres import AsyncPostgresSaver
            # Use the database URL from settings (strip +asyncpg suffix for checkpointer)
            db_url = settings.database_url.replace("+asyncpg", "")
            checkpointer = AsyncPostgresSaver.from_conn_string(db_url)
            await checkpointer.setup()
            logger.info("LangGraph checkpointer: postgres (AsyncPostgresSaver)")
            return checkpointer
        except ImportError:
            logger.warning(
                "langgraph-checkpoint-postgres not installed. "
                "Install with: pip install langgraph-checkpoint-postgres. "
                "Falling back to memory checkpointer."
            )
        except Exception as e:
            logger.error(f"Postgres checkpointer setup failed: {e}. Falling back to memory.")

    if checkpointer_type == "sqlite":
        try:
            from langgraph_checkpoint_sqlite import SqliteSaver
            checkpointer = SqliteSaver.from_conn_string("epc_agent_checkpoint.db")
            logger.info("LangGraph checkpointer: sqlite (SqliteSaver)")
            return checkpointer
        except ImportError:
            logger.warning("langgraph-checkpoint-sqlite not installed. Falling back to memory.")

    # Default: memory
    try:
        from langgraph.checkpoint.memory import InMemorySaver
        logger.info("LangGraph checkpointer: memory (InMemorySaver)")
        return InMemorySaver()
    except ImportError:
        logger.warning("LangGraph not installed — no checkpointer available. State will not persist.")
        return None
