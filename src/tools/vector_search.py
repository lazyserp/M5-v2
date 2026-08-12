from qdrant_client import QdrantClient
from qdrant_client.models import Distance , VectorParams, PointStruct
from fastembed import TextEmbedding

COLLECTION_NAME = "codebase_index"


class VectorStore:
    """
    Vector Store using FastEmbed and Qdrant for semantic code retrieval.
    """

    def __init__(self,storage_path:str = "./qdrant_storage") -> None:
        self.embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        self.vector_size = 384

        self.client = QdrantClient(path=storage_path)
        self.init_collection()


    def init_collection(self):
        """Creates Qdrant collection if it doesn't exist."""
        if not self.client.collection_exists(COLLECTION_NAME):
            self.client.create_collection(
                collection_name = COLLECTION_NAME,
                vectors_config=VectorParams(size=self.vector_size,distance=Distance.COSINE)
            )

    def index_blocks(self,blocks: list[dict]):
        """
        Generates embeddings for AST code blocks and uploads them to Qdrant.
        """
        if not blocks:
            return

        texts = [b["content"] for b in blocks]
        embeddings = list(self.embedder.embed(texts))

        points = []
        for idx, (b,emb) in enumerate(zip(blocks,embeddings)):
            points.append(
                PointStruct(
                    id=idx,
                    vector=emb.tolist(),
                    payload={
                        "type": b["type"],
                        "name": b["name"],
                        "file_path": b.get("file_path", "unknown"),
                        "start_line": b["start_line"],
                        "end_line": b["end_line"],
                        "content": b["content"]
                    }
                )
            )
        self.client.upsert(collection_name=COLLECTION_NAME, points=points)


    def search_code(self,user_query:str, top_k: int = 3) -> str:
        """
        Vector search tool callable by the AI Agent.
        """
        query_vector = list(self.embedder.embed([user_query]))[0].tolist()

        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=top_k
        ).points

        if not results:
            return f"[INFO] No relevant code found for query: '{user_query}'"

        output = f"--- Vector Search Results for '{user_query}' ---\n"

        for r in results:
            p = r.payload
            output += (
                f"\n[Candidate Match (Score: {r.score:.2f})]\n"
                f"File: {p['file_path']} (Lines {p['start_line']}-{p['end_line']})\n"
                f"Block Name: '{p['name']}' ({p['type']})\n"
                f"Content:\n{p['content']}\n"
            )

        return output

