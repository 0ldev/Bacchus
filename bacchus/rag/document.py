"""
Document processing for RAG.

Handles reading documents and chunking text for embedding generation.
Supports .txt and .md files with UTF-8 encoding.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import numpy as np


@dataclass
class Chunk:
    """
    A chunk of text from a document.

    Attributes:
        content: The text content of the chunk
        start_line: Starting line number in original document (1-based)
        end_line: Ending line number in original document (1-based)
        chunk_index: Position of this chunk in the chunk list (0-based)
        embedding: Vector embedding (populated during retrieval setup)
    """
    content: str
    start_line: int
    end_line: int
    chunk_index: int
    embedding: Optional[np.ndarray] = field(default=None)


def read_document(file_path: Union[str, Path]) -> str:
    """
    Read document content from a file.

    Args:
        file_path: Path to the document file

    Returns:
        The text content of the document

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file type is not supported
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Check supported extensions
    supported = {'.txt', '.md'}
    if path.suffix.lower() not in supported:
        raise ValueError(
            f"Unsupported file type: {path.suffix}. "
            f"Supported types: {', '.join(supported)}"
        )

    return path.read_text(encoding='utf-8')


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64
) -> List[Chunk]:
    """
    Split text into chunks for embedding.

    Chunks are created by:
    1. First splitting on paragraph boundaries (double newlines)
    2. Then splitting long paragraphs at chunk_size with overlap

    Args:
        text: The text to chunk
        chunk_size: Maximum characters per chunk
        overlap: Characters to overlap between chunks

    Returns:
        List of Chunk objects with content and line information
    """
    # Handle empty or whitespace-only text
    if not text or not text.strip():
        return []

    chunks = []
    chunk_index = 0

    # Split into paragraphs (on double newlines)
    paragraphs = text.split('\n\n')

    # Track line numbers
    current_line = 1

    for para in paragraphs:
        # Skip empty paragraphs but count the blank line
        if not para.strip():
            current_line += 1  # Count the blank line
            continue

        # Count lines in this paragraph
        para_lines = para.count('\n') + 1
        para_start_line = current_line
        para_end_line = current_line + para_lines - 1

        if len(para) <= chunk_size:
            # Paragraph fits in one chunk
            chunks.append(Chunk(
                content=para,
                start_line=para_start_line,
                end_line=para_end_line,
                chunk_index=chunk_index
            ))
            chunk_index += 1
        else:
            # Paragraph needs splitting
            para_chunks = _split_long_text(
                para, chunk_size, overlap,
                para_start_line, para_end_line, chunk_index
            )
            chunks.extend(para_chunks)
            chunk_index += len(para_chunks)

        # Move to next paragraph (current para lines + 1 blank line)
        current_line = para_end_line + 2

    return chunks


def _split_long_text(
    text: str,
    chunk_size: int,
    overlap: int,
    start_line: int,
    end_line: int,
    start_index: int
) -> List[Chunk]:
    """
    Split a long text into overlapping chunks.

    Args:
        text: Text to split
        chunk_size: Maximum characters per chunk
        overlap: Characters to overlap
        start_line: Starting line number of this text
        end_line: Ending line number of this text
        start_index: Starting chunk index

    Returns:
        List of Chunk objects
    """
    chunks = []
    pos = 0
    index = start_index
    text_len = len(text)

    while pos < text_len:
        # Calculate end position for this chunk
        end_pos = min(pos + chunk_size, text_len)
        chunk_content = text[pos:end_pos]

        # For line tracking in split chunks, we approximate
        # based on position in the text
        line_ratio = pos / text_len if text_len > 0 else 0
        chunk_start = start_line + int(line_ratio * (end_line - start_line))
        chunk_end = end_line if end_pos >= text_len else chunk_start

        chunks.append(Chunk(
            content=chunk_content,
            start_line=chunk_start,
            end_line=chunk_end,
            chunk_index=index
        ))

        index += 1

        # Move position forward (chunk_size - overlap)
        if end_pos >= text_len:
            break
        pos += chunk_size - overlap

    return chunks


def process_document(
    file_path: Union[str, Path],
    chunk_size: int = 512,
    overlap: int = 64
) -> List[Chunk]:
    """
    Read and process a document into chunks.

    Convenience function that combines read_document and chunk_text.

    Args:
        file_path: Path to the document file
        chunk_size: Maximum characters per chunk
        overlap: Characters to overlap between chunks

    Returns:
        List of Chunk objects ready for embedding

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file type is not supported
    """
    content = read_document(file_path)
    return chunk_text(content, chunk_size, overlap)
