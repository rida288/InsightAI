import pandas as pd
from sqlalchemy.orm import Session
from app.db.models.project_embedding import ProjectEmbedding
from langchain_community.embeddings import FastEmbedEmbeddings

# Runs BAAI/bge-small-en-v1.5 locally via ONNX (fastembed), so there is no API quota
# or per-request cost. It is a quantized ONNX model, not PyTorch: measured ~170MB RAM
# loaded, ~240MB at peak while embedding, which fits Render's 512MB free tier.
# Produces 384-dim vectors to match ProjectEmbedding.embedding (Vector(384)).
# The model (~67MB) is downloaded from the HuggingFace Hub on first load.
print("[InsightAI] Loading local embedding model (BAAI/bge-small-en-v1.5)...")
embedding_model = FastEmbedEmbeddings(
    model_name="BAAI/bge-small-en-v1.5",
    batch_size=16,  # small ONNX batches keep peak memory low
)
print("[InsightAI] Embedding model ready.")

class IngestionService:
    def __init__(self, db: Session):
        self.db = db

    def extract_text_content(self, row: pd.Series) -> str:
        """
        Combine all textual information in a row into a single searchable string.
        """
        parts = []
        for col, val in row.items():
            if pd.notna(val) and isinstance(val, (str, int, float)):
                parts.append(f"{col}: {val}")
        return " | ".join(parts)

    def process_and_embed_project_data(self, project_id: int, file_path: str, batch_size: int = 100):
        """
        Reads a spreadsheet, extracts text, generates embeddings in batches,
        and saves them to the pgvector database.
        """
        from app.core.storage.s3_client import S3Client
        import io

        # Get file stream from B2
        s3_client = S3Client()
        file_stream = s3_client.get_file_stream(file_path)
        file_buffer = io.BytesIO(file_stream.read())

        # Determine file type and read
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_buffer)
        elif file_path.endswith('.xlsx'):
            df = pd.read_excel(file_buffer)
        else:
            raise ValueError("Unsupported file format for ingestion")

        # Clean dataframe
        df = df.dropna(how='all')

        texts_to_embed = []
        row_indices = []

        # Iterate over dataframe
        for idx, row in df.iterrows():
            content = self.extract_text_content(row)
            if content.strip():
                texts_to_embed.append(content)
                row_indices.append(idx)

        total_rows = len(texts_to_embed)
        total_batches = (total_rows + batch_size - 1) // batch_size
        print(f"[InsightAI] Embedding {total_rows} rows in {total_batches} batches...")

        # Embed and save one batch at a time. The model runs on the local CPU, so
        # parallel batches would only add memory, and committing per batch keeps
        # progress if a later batch fails.
        for b, i in enumerate(range(0, total_rows, batch_size), start=1):
            batch_texts = texts_to_embed[i:i + batch_size]
            batch_indices = row_indices[i:i + batch_size]
            embeddings = embedding_model.embed_documents(batch_texts)

            self.db.bulk_save_objects([
                ProjectEmbedding(
                    project_id=project_id,
                    row_index=row_index,
                    content=text,
                    embedding=embedding,
                )
                for row_index, text, embedding in zip(batch_indices, batch_texts, embeddings)
            ])
            self.db.commit()
            print(f"[InsightAI] Project {project_id}: embedded batch {b}/{total_batches}")

        return total_rows
