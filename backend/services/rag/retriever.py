"""
RAG Retriever — semantic search over database schema metadata and project summaries.

Given a user query, retrieves:
1. Top-K relevant database tables based on schema description similarity
2. Relevant columns within those tables
3. This information guides the LLM to select the right function tools
"""

import logging
from config import settings
from services.rag.embedder import embedder
from services.rag.schema_indexer import schema_indexer

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Retrieves relevant database schema information for a user query."""

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """Ensure the schema index is built and embedded."""
        if not self._initialized:
            await schema_indexer.build_index()
            await schema_indexer.embed_index()
            self._initialized = True

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[dict]:
        """
        Retrieve the most relevant database tables for a user query.

        Args:
            query: Natural language user query
            top_k: Number of results to return (default from config)

        Returns:
            List of matched schema documents with similarity scores
        """
        await self.initialize()
        k = top_k or settings.ai_rag_top_k

        # Embed the query
        query_vec = await embedder.embed_query(query)
        embeddings = schema_indexer.get_embeddings()
        documents = schema_indexer.get_index()

        if not embeddings or not documents:
            logger.warning("Schema index is empty — returning empty results")
            return []

        # Compute cosine similarity
        scores = []
        for i, doc_vec in enumerate(embeddings):
            similarity = self._cosine_similarity(query_vec, doc_vec)
            scores.append((similarity, i))

        # Sort by similarity (descending) and take top-k
        scores.sort(key=lambda x: x[0], reverse=True)

        threshold = settings.ai_rag_similarity_threshold
        results = []
        for sim, idx in scores[:k]:
            if sim >= threshold:
                doc = documents[idx].copy()
                doc["similarity"] = round(sim, 4)
                results.append(doc)

        logger.info(f"RAG retrieved {len(results)}/{len(documents)} tables for query (top_k={k})")
        return results

    async def retrieve_tool_suggestions(self, query: str) -> list[str]:
        """
        Retrieve suggested tool names based on schema relevance to the query.

        Returns:
            List of tool names (e.g., ['query_activities', 'calculate_kpi'])
        """
        results = await self.retrieve(query, top_k=5)

        # Map table names to tool names
        table_to_tool = {
            "activities": "query_activities",
            "drawings": "query_drawings",
            "procurement_purchase_orders": "query_procurement",
            "quality_ncr": "query_quality_ncr",
            "safety_incidents": "query_safety_incidents",
            "personnel_training": "query_training_records",
            "stage_gates": "query_stage_gates",
            "conflicts": "query_conflicts",
            "sub_systems": "query_traceability",
            "punch_items": "calculate_kpi",
            "commissioning_procedures": "calculate_kpi",
            "schedule_alerts": "calculate_kpi",
            "resource_shortages": "calculate_kpi",
        }

        tools = []
        for r in results:
            tool = table_to_tool.get(r["table_name"])
            if tool and tool not in tools:
                tools.append(tool)

        # Always include calculate_kpi as a fallback
        if "calculate_kpi" not in tools:
            tools.append("calculate_kpi")

        return tools

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b:
            return 0.0
        # Pad shorter vector
        max_len = max(len(a), len(b))
        a_padded = a + [0.0] * (max_len - len(a))
        b_padded = b + [0.0] * (max_len - len(b))

        dot = sum(x * y for x, y in zip(a_padded, b_padded))
        norm_a = (sum(x * x for x in a_padded)) ** 0.5
        norm_b = (sum(x * x for x in b_padded)) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# Singleton
rag_retriever = RAGRetriever()
