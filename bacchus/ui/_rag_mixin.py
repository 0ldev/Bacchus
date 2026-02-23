"""
RAG mixin for MainWindow.

Extracted from main_window.py. Contains all RAG-related methods including
document attachment, embedding generation, and context retrieval.
Now supports both per-conversation and per-project embeddings.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class RAGMixin:
    """
    Mixin providing RAG (retrieval-augmented generation) methods for MainWindow.

    Requires self to have:
        - self.database (Database)
        - self.model_manager (ModelManager or None)
        - self.prompt_area (PromptArea)
        - self._current_conversation_id (Optional[int])
        - self._doc_process_worker (Optional[QThread])
    """

    def _on_document_attached(self, file_path: str):
        """Handle document attachment — copy file, update DB, start embedding."""
        if self._current_conversation_id is None:
            logger.warning("Cannot attach document: no conversation selected")
            return

        import shutil
        from bacchus import constants

        src = Path(file_path)
        conv_id = self._current_conversation_id

        dest_dir = constants.DOCUMENTS_DIR / str(conv_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        try:
            shutil.copy2(str(src), str(dest))
        except OSError as e:
            logger.error(f"Failed to copy document: {e}")
            return

        try:
            content = src.read_text(encoding="utf-8")
        except OSError as e:
            logger.error(f"Failed to read document: {e}")
            return

        self.database.update_conversation(
            conversation_id=conv_id,
            document_path=str(dest),
            document_content=content,
            rag_enabled=True,
        )

        logger.info(f"Document copied to {dest} and DB updated")

        if self.model_manager and self.model_manager.is_embedding_model_loaded():
            self._start_document_processing(conv_id, dest, content)
        else:
            logger.info("Embedding model not loaded — skipping embedding generation")

    def _on_document_removed(self):
        """Handle document removal — delete files, clear DB."""
        if self._current_conversation_id is None:
            return

        from bacchus import constants

        conv_id = self._current_conversation_id

        conversation = self.database.get_conversation(conv_id)
        if conversation and conversation.document_path:
            doc_path = Path(conversation.document_path)
            try:
                if doc_path.exists():
                    doc_path.unlink()
                    if doc_path.parent.exists() and not any(doc_path.parent.iterdir()):
                        doc_path.parent.rmdir()
            except OSError as e:
                logger.warning(f"Failed to delete document file: {e}")

        npz_path = constants.EMBEDDINGS_DIR / f"{conv_id}.npz"
        try:
            if npz_path.exists():
                npz_path.unlink()
        except OSError as e:
            logger.warning(f"Failed to delete embeddings file: {e}")

        self.database.clear_conversation_document(conv_id)
        logger.info(f"Document removed for conversation {conv_id}")

    def _start_document_processing(self, conv_id: int, document_path: Path, content: str):
        """Start background DocumentProcessWorker for embedding generation."""
        from bacchus.rag.embeddings import DocumentProcessWorker
        from bacchus import constants
        from transformers import AutoTokenizer

        compiled_model = self.model_manager.get_embedding_compiled_model()
        if compiled_model is None:
            logger.warning("No embedding compiled model available")
            return

        tokenizer_path = constants.MODELS_DIR / "all-minilm-l6-v2"
        try:
            tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path))
        except Exception as e:
            logger.error(f"Failed to load tokenizer: {e}")
            return

        npz_path = constants.EMBEDDINGS_DIR / f"{conv_id}.npz"

        if self._doc_process_worker and self._doc_process_worker.isRunning():
            self._doc_process_worker.quit()
            self._doc_process_worker.wait(2000)

        self._doc_process_worker = DocumentProcessWorker(
            conversation_id=conv_id,
            document_path=document_path,
            npz_path=npz_path,
            compiled_model=compiled_model,
            tokenizer=tokenizer,
        )
        self._doc_process_worker.processing_complete.connect(
            self._on_document_processing_complete
        )
        self._doc_process_worker.processing_failed.connect(
            self._on_document_processing_failed
        )
        self._doc_process_worker.start()
        logger.info(f"Document processing started for conversation {conv_id}")

    def _on_document_processing_complete(self, conv_id: int):
        """Called from DocumentProcessWorker when embeddings are ready."""
        logger.info(f"Document embeddings ready for conversation {conv_id}")

    def _on_document_processing_failed(self, conv_id: int, error: str):
        """Called from DocumentProcessWorker on failure."""
        logger.error(f"Document embedding failed for conversation {conv_id}: {error}")

    def _build_rag_context(self, formatted_messages: list) -> tuple:
        """
        Build RAG context string by retrieving the most relevant chunks.

        Loads chunks from both the conversation's attached document and the
        project's shared documents (if any). Retrieves from the combined pool.

        Args:
            formatted_messages: List of {"role": ..., "content": ...} dicts

        Returns:
            (rag_context_str, document_name) or (None, None) if RAG not applicable
        """
        from bacchus import constants
        from bacchus.rag.embeddings import load_embeddings, embed_text
        from bacchus.rag.retrieval import find_top_k_chunks, merge_and_retrieve

        conv_id = self._current_conversation_id
        conversation = self.database.get_conversation(conv_id)

        # Load per-conversation chunks
        conv_chunks = []
        document_name = None
        if conversation and conversation.rag_enabled and conversation.document_path:
            npz_path = constants.EMBEDDINGS_DIR / f"{conv_id}.npz"
            conv_chunks = load_embeddings(npz_path)
            if conv_chunks:
                document_name = Path(conversation.document_path).name
            else:
                logger.info(
                    f"RAG: conversation {conv_id} has document but no embeddings at {npz_path} "
                    f"(embedding model may not have been loaded when doc was attached)"
                )

        # Load per-project chunks
        proj_chunks = []
        project_name = None
        if conversation and conversation.project_id:
            project = self.database.get_project(conversation.project_id)
            if project:
                project_name = project.name
                proj_npz = constants.PROJECTS_DIR / str(conversation.project_id) / "embeddings.npz"
                proj_chunks = load_embeddings(proj_npz)
                if not proj_chunks:
                    logger.info(
                        f"RAG: project '{project_name}' (id={conversation.project_id}) has no "
                        f"embeddings at {proj_npz} — "
                        f"ensure the all-minilm-l6-v2 embedding model is loaded when adding documents"
                    )
                else:
                    logger.info(
                        f"RAG: loaded {len(proj_chunks)} chunks from project '{project_name}'"
                    )
        elif conversation and conversation.project_id is None:
            logger.debug(
                f"RAG: conversation {conv_id} has no project_id — "
                f"create conversations via the '+' button inside a project section to enable project RAG"
            )

        if not conv_chunks and not proj_chunks:
            return None, None

        # Ensure embedding model is available
        if not self.model_manager or not self.model_manager.is_embedding_model_loaded():
            logger.warning(
                "RAG: embedding model (all-minilm-l6-v2) is not loaded — "
                "cannot embed query. Load it from Settings > Models."
            )
            return None, None

        compiled_model = self.model_manager.get_embedding_compiled_model()

        tokenizer_path = constants.MODELS_DIR / "all-minilm-l6-v2"
        try:
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path))
        except Exception as e:
            logger.error(f"Failed to load tokenizer for RAG: {e}")
            return None, None

        # Use last user message as query
        query = ""
        for msg in reversed(formatted_messages):
            if msg.get("role") == "user":
                query = msg.get("content", "")
                break

        if not query:
            return None, None

        try:
            query_embedding = embed_text(query, compiled_model, tokenizer)
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            return None, None

        # Tag chunks with source labels before merging
        if document_name:
            for c in conv_chunks:
                c._rag_source = document_name
        if project_name:
            for c in proj_chunks:
                c._rag_source = project_name

        # Retrieve top-k from combined or single pool
        if conv_chunks and proj_chunks:
            top_chunks = merge_and_retrieve(
                conv_chunks, proj_chunks, query_embedding,
                k=constants.RAG_TOP_K,
                min_similarity=constants.RAG_MIN_SIMILARITY
            )
        elif conv_chunks:
            top_chunks = find_top_k_chunks(
                conv_chunks, query_embedding,
                k=constants.RAG_TOP_K,
                min_similarity=constants.RAG_MIN_SIMILARITY
            )
        else:
            top_chunks = find_top_k_chunks(
                proj_chunks, query_embedding,
                k=constants.RAG_TOP_K,
                min_similarity=constants.RAG_MIN_SIMILARITY
            )

        if not top_chunks:
            return None, None

        # Build context string, grouping by source
        from collections import defaultdict
        by_source: dict = defaultdict(list)
        for chunk in top_chunks:
            source = getattr(chunk, '_rag_source', document_name or project_name or "Document")
            by_source[source].append(chunk)

        rag_lines = []
        for source, chunks in by_source.items():
            rag_lines.append(f"[Relevant excerpts from '{source}']")
            for chunk in chunks:
                rag_lines.append(
                    f"(Lines {chunk.start_line}–{chunk.end_line})\n{chunk.content}"
                )
        rag_context = "\n\n".join(rag_lines)

        # Return the primary document name (used as label in prompt header)
        # If mixed sources, return None so the prompt uses the generic header
        ret_document_name = document_name if not proj_chunks else None

        logger.info(
            f"RAG: retrieved {len(top_chunks)} chunks for query ({len(query)} chars) "
            f"conv={len(conv_chunks)} proj={len(proj_chunks)}"
        )
        return rag_context, ret_document_name
