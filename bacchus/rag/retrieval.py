"""
RAG retrieval functions.

Handles similarity calculations and chunk retrieval for RAG queries.
"""

from typing import List

import numpy as np

from .document import Chunk


def calculate_cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity value between -1.0 and 1.0
    """
    # Handle zero vectors
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(np.dot(vec1, vec2) / (norm1 * norm2))


def calculate_all_similarities(
    chunks: List[Chunk],
    query_embedding: np.ndarray
) -> np.ndarray:
    """
    Calculate similarity between query and all chunks.

    Args:
        chunks: List of chunks with embeddings
        query_embedding: Query vector

    Returns:
        Array of similarity scores, one per chunk
    """
    if not chunks:
        return np.array([])

    similarities = [
        calculate_cosine_similarity(chunk.embedding, query_embedding)
        for chunk in chunks
    ]
    return np.array(similarities)


def find_top_k_chunks(
    chunks: List[Chunk],
    query_embedding: np.ndarray,
    k: int = 3,
    min_similarity: float = 0.3
) -> List[Chunk]:
    """
    Find the k most similar chunks to a query embedding.

    Args:
        chunks: List of chunks with embeddings
        query_embedding: Query vector
        k: Number of top chunks to return
        min_similarity: Minimum similarity threshold (default 0.3)

    Returns:
        List of k most similar chunks, sorted by similarity (highest first)
    """
    if not chunks:
        return []

    # Calculate similarities
    similarities = calculate_all_similarities(chunks, query_embedding)

    # Create list of (chunk, similarity) pairs
    chunk_scores = list(zip(chunks, similarities))

    # Filter by minimum similarity
    chunk_scores = [
        (chunk, score) for chunk, score in chunk_scores
        if score >= min_similarity
    ]

    # Sort by similarity (descending)
    chunk_scores.sort(key=lambda x: x[1], reverse=True)

    # Return top k chunks
    return [chunk for chunk, _ in chunk_scores[:k]]
