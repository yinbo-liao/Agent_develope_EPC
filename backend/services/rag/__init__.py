"""RAG Vector Store — schema-aware retrieval for database-limited queries.

The RAG pipeline:
  1. User query → embed → vector search over schema metadata + project summaries
  2. Retrieve relevant DB tables/columns
  3. LLM generates tool calls or SQL based on retrieved schema
  4. Tool executes against PostgreSQL → results → LLM response

All data sources are limited to the project database. No external data is used.
"""
from services.rag.retriever import RAGRetriever
from services.rag.schema_indexer import SchemaIndexer

__all__ = ["RAGRetriever", "SchemaIndexer"]
