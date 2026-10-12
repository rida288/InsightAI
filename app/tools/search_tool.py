from langchain.tools import tool
from typing import Callable
from sqlalchemy import select
from pydantic import BaseModel, Field
from app.db.models.project_embedding import ProjectEmbedding
from app.service.ingestion import embedding_model

class SearchInput(BaseModel):
    query: str = Field(default=None, description="The natural language query to search for")
    question: str = Field(default=None, description="The natural language query to search for (alias for query)")

def get_search_tool(db_getter: Callable, project_id: int):
    @tool("semantic_search", args_schema=SearchInput)
    def semantic_search(query: str = None, question: str = None) -> str:
        """
        Use this tool to search for semantic meaning, context, or fuzzy matching in the spreadsheet's text data.
        Input should be a search query.
        """
        actual_query = query or question
        if not actual_query:
            return "Error: Please provide a query or question."
            
        # The embedding model runs locally, so there is no network call to retry
        try:
            query_embedding = embedding_model.embed_query(actual_query)
        except Exception as e:
            return f"Error: Failed to generate query embedding: {e}"

        # Open a fresh DB session or use thread-local if available
        from app.core.database import SessionLocal
        db = db_getter() if db_getter and db_getter() is not None else SessionLocal()
        should_close = db_getter is None or db_getter() is None

        try:
            # Query pgvector for the top 5 closest matches, filtered by project_id
            stmt = select(ProjectEmbedding).where(
                ProjectEmbedding.project_id == project_id
            ).order_by(
                ProjectEmbedding.embedding.cosine_distance(query_embedding)
            ).limit(5)

            results = db.execute(stmt).scalars().all()

            if not results:
                return "No relevant text data found for this query."

            # Combine the results into a string
            result_texts = []
            for res in results:
                result_texts.append(f"Row {res.row_index}: {res.content}")

            return "\n".join(result_texts)
        finally:
            if should_close:
                db.close()
        
    return semantic_search
