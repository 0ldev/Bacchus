"""
Embedding generation and persistence for RAG.

Handles converting text chunks to vector embeddings using the OpenVINO
compiled all-MiniLM-L6-v2 model, and saving/loading embeddings to/from disk.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from bacchus.rag.document import Chunk

logger = logging.getLogger(__name__)


# ── Tokenisation ──────────────────────────────────────────────────────────────

def _tokenize(text: str, tokenizer) -> dict:
    """
    Tokenize a single string using the HuggingFace tokenizer.

    Returns a dict with 'input_ids', 'attention_mask', 'token_type_ids'
    as numpy arrays of shape (1, seq_len).
    """
    encoded = tokenizer(
        text,
        padding="max_length",
        truncation=True,
        max_length=128,
        return_tensors="np",
    )
    return {
        "input_ids": encoded["input_ids"].astype(np.int64),
        "attention_mask": encoded["attention_mask"].astype(np.int64),
        "token_type_ids": encoded.get(
            "token_type_ids",
            np.zeros_like(encoded["input_ids"], dtype=np.int64)
        ),
    }


def _mean_pool(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    """
    Apply attention-masked mean pooling over token embeddings.

    Args:
        token_embeddings: (1, seq_len, hidden_dim)
        attention_mask:   (1, seq_len)

    Returns:
        Normalised 1-D embedding vector of shape (hidden_dim,)
    """
    mask = attention_mask[..., np.newaxis].astype(np.float32)  # (1, seq_len, 1)
    summed = (token_embeddings * mask).sum(axis=1)             # (1, hidden_dim)
    counts = mask.sum(axis=1).clip(min=1e-9)                   # (1, 1)
    pooled = (summed / counts)[0]                              # (hidden_dim,)
    norm = np.linalg.norm(pooled)
    return pooled / norm if norm > 0 else pooled


# ── Public embedding helpers ───────────────────────────────────────────────────

def embed_text(text: str, compiled_model, tokenizer) -> np.ndarray:
    """
    Generate a normalised embedding for a single text string.

    Args:
        text:           Input text
        compiled_model: OpenVINO CompiledModel (all-MiniLM-L6-v2)
        tokenizer:      HuggingFace tokenizer for the same model

    Returns:
        1-D numpy array of shape (384,)
    """
    inputs = _tokenize(text, tokenizer)
    outputs = compiled_model(inputs)
    # The model returns last_hidden_state as first output
    last_hidden = list(outputs.values())[0]  # (1, seq_len, 384)
    return _mean_pool(last_hidden, inputs["attention_mask"])


def generate_embeddings(
    chunks: List[Chunk],
    compiled_model,
    tokenizer,
) -> List[Chunk]:
    """
    Generate embeddings for a list of chunks in-place.

    Each chunk's .embedding field is populated.

    Args:
        chunks:         List of Chunk objects
        compiled_model: OpenVINO CompiledModel (all-MiniLM-L6-v2)
        tokenizer:      HuggingFace tokenizer

    Returns:
        Same list of chunks with embeddings populated
    """
    for chunk in chunks:
        chunk.embedding = embed_text(chunk.content, compiled_model, tokenizer)
    return chunks


# ── Persistence ───────────────────────────────────────────────────────────────

def save_embeddings(chunks: List[Chunk], npz_path: Path) -> None:
    """
    Save chunk embeddings and metadata to a .npz file.

    Args:
        chunks:   List of Chunk objects with embeddings populated
        npz_path: Destination path for the .npz file
    """
    npz_path = Path(npz_path)
    npz_path.parent.mkdir(parents=True, exist_ok=True)

    embeddings = np.array([c.embedding for c in chunks], dtype=np.float32)
    contents = np.array([c.content for c in chunks], dtype=object)
    start_lines = np.array([c.start_line for c in chunks], dtype=np.int32)
    end_lines = np.array([c.end_line for c in chunks], dtype=np.int32)
    chunk_indices = np.array([c.chunk_index for c in chunks], dtype=np.int32)

    np.savez(
        str(npz_path),
        embeddings=embeddings,
        contents=contents,
        start_lines=start_lines,
        end_lines=end_lines,
        chunk_indices=chunk_indices,
    )
    logger.info(f"Saved {len(chunks)} embeddings to {npz_path}")


def load_embeddings(npz_path: Path) -> List[Chunk]:
    """
    Load chunk embeddings from a .npz file.

    Args:
        npz_path: Path to the .npz file

    Returns:
        List of Chunk objects with embeddings populated
    """
    npz_path = Path(npz_path)
    if not npz_path.exists():
        return []

    data = np.load(str(npz_path), allow_pickle=True)
    chunks = []
    for i in range(len(data["embeddings"])):
        chunk = Chunk(
            content=str(data["contents"][i]),
            start_line=int(data["start_lines"][i]),
            end_line=int(data["end_lines"][i]),
            chunk_index=int(data["chunk_indices"][i]),
            embedding=data["embeddings"][i],
        )
        chunks.append(chunk)

    logger.info(f"Loaded {len(chunks)} embeddings from {npz_path}")
    return chunks


# ── Background worker ─────────────────────────────────────────────────────────

class DocumentProcessWorker(QThread):
    """
    Background thread for chunking a document and generating embeddings.

    Signals:
        processing_complete(int): conversation_id — emitted on success
        processing_failed(int, str): conversation_id, error_message — emitted on failure
    """

    processing_complete = pyqtSignal(int)
    processing_failed = pyqtSignal(int, str)

    def __init__(
        self,
        conversation_id: int,
        document_path: Path,
        npz_path: Path,
        compiled_model,
        tokenizer,
        parent=None,
    ):
        """
        Args:
            conversation_id: ID of the conversation this document belongs to
            document_path:   Path to the copied document file
            npz_path:        Destination path for the embeddings .npz
            compiled_model:  OpenVINO CompiledModel (all-MiniLM-L6-v2)
            tokenizer:       HuggingFace tokenizer
        """
        super().__init__(parent)
        self.conversation_id = conversation_id
        self.document_path = Path(document_path)
        self.npz_path = Path(npz_path)
        self.compiled_model = compiled_model
        self.tokenizer = tokenizer

    def run(self) -> None:
        """Run chunking + embedding generation in background thread."""
        try:
            from bacchus.rag.document import process_document
            from bacchus.constants import RAG_CHUNK_SIZE, RAG_OVERLAP

            logger.info(
                f"[conv {self.conversation_id}] Processing document: {self.document_path}"
            )
            chunks = process_document(
                self.document_path,
                chunk_size=RAG_CHUNK_SIZE,
                overlap=RAG_OVERLAP,
            )

            if not chunks:
                logger.warning(
                    f"[conv {self.conversation_id}] Document produced no chunks"
                )
                self.processing_complete.emit(self.conversation_id)
                return

            generate_embeddings(chunks, self.compiled_model, self.tokenizer)
            save_embeddings(chunks, self.npz_path)

            logger.info(
                f"[conv {self.conversation_id}] Embeddings saved: "
                f"{len(chunks)} chunks → {self.npz_path}"
            )
            self.processing_complete.emit(self.conversation_id)

        except Exception as e:
            logger.error(
                f"[conv {self.conversation_id}] Document processing failed: {e}",
                exc_info=True,
            )
            self.processing_failed.emit(self.conversation_id, str(e))


class ProjectDocumentProcessWorker(QThread):
    """
    Background thread for processing all documents in a project and generating
    a single combined embeddings file.

    Signals:
        processing_complete(int): project_id — emitted on success
        processing_failed(int, str): project_id, error_message — emitted on failure
    """

    processing_complete = pyqtSignal(int)
    processing_failed = pyqtSignal(int, str)

    def __init__(
        self,
        project_id: int,
        document_paths: List[Path],
        npz_path: Path,
        compiled_model,
        tokenizer,
        parent=None,
    ):
        """
        Args:
            project_id:      ID of the project these documents belong to
            document_paths:  List of paths to document files
            npz_path:        Destination path for the combined embeddings .npz
            compiled_model:  OpenVINO CompiledModel (all-MiniLM-L6-v2)
            tokenizer:       HuggingFace tokenizer
        """
        super().__init__(parent)
        self.project_id = project_id
        self.document_paths = [Path(p) for p in document_paths]
        self.npz_path = Path(npz_path)
        self.compiled_model = compiled_model
        self.tokenizer = tokenizer

    def run(self) -> None:
        """Run chunking + embedding generation for all project documents."""
        try:
            from bacchus.rag.document import process_document
            from bacchus.constants import RAG_CHUNK_SIZE, RAG_OVERLAP

            logger.info(
                f"[project {self.project_id}] Processing {len(self.document_paths)} document(s)"
            )

            all_chunks = []
            for doc_path in self.document_paths:
                try:
                    chunks = process_document(
                        doc_path,
                        chunk_size=RAG_CHUNK_SIZE,
                        overlap=RAG_OVERLAP,
                    )
                    all_chunks.extend(chunks)
                    logger.info(
                        f"[project {self.project_id}] {doc_path.name}: {len(chunks)} chunks"
                    )
                except Exception as e:
                    logger.warning(
                        f"[project {self.project_id}] Skipping {doc_path.name}: {e}"
                    )

            if not all_chunks:
                logger.warning(
                    f"[project {self.project_id}] No chunks produced from any document"
                )
                self.processing_complete.emit(self.project_id)
                return

            generate_embeddings(all_chunks, self.compiled_model, self.tokenizer)
            save_embeddings(all_chunks, self.npz_path)

            logger.info(
                f"[project {self.project_id}] Embeddings saved: "
                f"{len(all_chunks)} chunks → {self.npz_path}"
            )
            self.processing_complete.emit(self.project_id)

        except Exception as e:
            logger.error(
                f"[project {self.project_id}] Document processing failed: {e}",
                exc_info=True,
            )
            self.processing_failed.emit(self.project_id, str(e))
