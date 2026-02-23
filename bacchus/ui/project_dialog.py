"""
Project dialog for Bacchus.

Modal dialog for creating and editing projects. Supports:
- Name and description
- Custom system prompt (appended after base prompt)
- Document management with background embedding generation
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bacchus.constants import PROJECTS_DIR, SUPPORTED_DOCUMENT_EXTENSIONS
from bacchus.database import Database

logger = logging.getLogger(__name__)


class ProjectDialog(QDialog):
    """
    Dialog for creating or editing a project.

    Emits project_saved(project_id) on successful save.
    """

    project_saved = pyqtSignal(int)

    def __init__(
        self,
        parent: QWidget,
        database: Database,
        model_manager=None,
        project_id: Optional[int] = None,
    ):
        """
        Args:
            parent:      Parent widget
            database:    Database instance
            model_manager: ModelManager (for embedding worker)
            project_id:  If set, opens in edit mode for this project.
                         If None, opens in create mode.
        """
        super().__init__(parent)
        self.database = database
        self.model_manager = model_manager
        self._project_id: Optional[int] = project_id
        self._is_create_mode = project_id is None
        self._embed_worker = None  # prevent GC

        # In create mode: track if we have already persisted the project row
        self._project_created = False

        title = "New Project" if self._is_create_mode else "Edit Project"
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.setMinimumHeight(480)

        self._build_ui()

        if not self._is_create_mode:
            self._populate_fields()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Form: Name + Description
        form = QFormLayout()
        form.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Project name")
        form.addRow("Name:", self._name_edit)

        self._description_edit = QPlainTextEdit()
        self._description_edit.setPlaceholderText("Short description (optional)")
        self._description_edit.setFixedHeight(52)
        form.addRow("Description:", self._description_edit)

        layout.addLayout(form)

        # Custom prompt
        layout.addWidget(QLabel("Custom Prompt:"))
        self._prompt_edit = QPlainTextEdit()
        self._prompt_edit.setPlaceholderText(
            "Additional instructions appended after the base system prompt …"
        )
        self._prompt_edit.setFixedHeight(150)
        layout.addWidget(self._prompt_edit)

        # Documents group
        doc_group = QGroupBox("Documents")
        doc_layout = QVBoxLayout(doc_group)

        self._doc_list = QListWidget()
        self._doc_list.setFixedHeight(120)
        doc_layout.addWidget(self._doc_list)

        btn_row = QHBoxLayout()
        self._add_doc_btn = QPushButton("Add Document")
        self._remove_doc_btn = QPushButton("Remove Document")
        self._add_doc_btn.clicked.connect(self._on_add_document)
        self._remove_doc_btn.clicked.connect(self._on_remove_document)
        btn_row.addWidget(self._add_doc_btn)
        btn_row.addWidget(self._remove_doc_btn)
        btn_row.addStretch()
        doc_layout.addLayout(btn_row)

        layout.addWidget(doc_group)

        # Dialog buttons
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self._on_reject)
        layout.addWidget(self._button_box)

    # ── Pre-populate (edit mode) ───────────────────────────────────────────────

    def _populate_fields(self) -> None:
        """Fill in existing project data for edit mode."""
        project = self.database.get_project(self._project_id)
        if not project:
            logger.error(f"Project {self._project_id} not found")
            return

        self._name_edit.setText(project.name)
        self._description_edit.setPlainText(project.description or "")
        self._prompt_edit.setPlainText(project.custom_prompt or "")

        docs = self.database.list_project_documents(self._project_id)
        for doc in docs:
            item = QListWidgetItem(doc.file_name)
            item.setData(256, doc.id)  # store DB id in UserRole
            self._doc_list.addItem(item)

    # ── Document actions ───────────────────────────────────────────────────────

    def _ensure_project_exists(self) -> bool:
        """
        In create mode, persist the project row on first document add so we
        have a valid project_id for file placement.

        Returns True if project_id is ready to use.
        """
        if self._project_id is not None:
            return True

        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Name Required",
                                "Please enter a project name before adding documents.")
            return False

        pid = self.database.create_project(
            name=name,
            description=self._description_edit.toPlainText().strip() or None,
            custom_prompt=self._prompt_edit.toPlainText().strip() or None,
        )
        self._project_id = pid
        self._project_created = True
        logger.info(f"Created project {pid} (staged, not yet confirmed)")
        return True

    def _on_add_document(self) -> None:
        """Open file dialog and copy selected document into the project."""
        if not self.model_manager or not self.model_manager.is_embedding_model_loaded():
            QMessageBox.warning(
                self,
                "Embedding Model Not Loaded",
                "Please load the embedding model (all-minilm-l6-v2) from Settings > Models "
                "before adding documents."
            )
            return

        if not self._ensure_project_exists():
            return

        ext_filter = "Documents (*.txt *.md)"
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Document", "", ext_filter)
        if not paths:
            return

        project_id = self._project_id
        docs_dir = PROJECTS_DIR / str(project_id) / "documents"
        docs_dir.mkdir(parents=True, exist_ok=True)

        added_paths = []
        for path_str in paths:
            src = Path(path_str)
            dest = docs_dir / src.name
            try:
                shutil.copy2(str(src), str(dest))
            except OSError as e:
                QMessageBox.warning(self, "Copy Failed", f"Could not copy {src.name}: {e}")
                continue

            doc_id = self.database.add_project_document(
                project_id=project_id,
                file_path=str(dest),
                file_name=src.name,
            )
            item = QListWidgetItem(src.name)
            item.setData(256, doc_id)
            self._doc_list.addItem(item)
            added_paths.append(dest)
            logger.info(f"Added document {src.name} to project {project_id}")

        if added_paths:
            self._start_project_embedding(project_id)

    def _on_remove_document(self) -> None:
        """Remove the selected document from the list, DB, and filesystem."""
        if not self.model_manager or not self.model_manager.is_embedding_model_loaded():
            QMessageBox.warning(
                self,
                "Embedding Model Not Loaded",
                "Please load the embedding model (all-minilm-l6-v2) from Settings > Models "
                "before removing documents."
            )
            return

        selected = self._doc_list.selectedItems()
        if not selected:
            return

        item = selected[0]
        doc_id: int = item.data(256)

        # Get file path before removing from DB
        docs = self.database.list_project_documents(self._project_id)
        file_path = None
        for doc in docs:
            if doc.id == doc_id:
                file_path = doc.file_path
                break

        self.database.remove_project_document(doc_id)
        self._doc_list.takeItem(self._doc_list.row(item))

        if file_path:
            try:
                Path(file_path).unlink(missing_ok=True)
            except OSError as e:
                logger.warning(f"Could not delete {file_path}: {e}")

        # Re-embed remaining documents
        if self._project_id is not None:
            self._start_project_embedding(self._project_id)

    def _start_project_embedding(self, project_id: int) -> None:
        """Start background embedding for all current project documents."""
        if not self.model_manager or not self.model_manager.is_embedding_model_loaded():
            logger.warning(
                "Project embedding skipped: the all-minilm-l6-v2 embedding model is not loaded. "
                "Load it from Settings > Models, then re-add the documents to generate embeddings."
            )
            return

        from bacchus.rag.embeddings import ProjectDocumentProcessWorker
        from bacchus.constants import MODELS_DIR
        from transformers import AutoTokenizer

        compiled_model = self.model_manager.get_embedding_compiled_model()
        if compiled_model is None:
            return

        tokenizer_path = MODELS_DIR / "all-minilm-l6-v2"
        try:
            tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path))
        except Exception as e:
            logger.error(f"Failed to load tokenizer for project embedding: {e}")
            return

        docs = self.database.list_project_documents(project_id)
        doc_paths = [Path(doc.file_path) for doc in docs if Path(doc.file_path).exists()]

        if not doc_paths:
            return

        npz_path = PROJECTS_DIR / str(project_id) / "embeddings.npz"

        if self._embed_worker and self._embed_worker.isRunning():
            self._embed_worker.quit()
            self._embed_worker.wait(2000)

        self._embed_worker = ProjectDocumentProcessWorker(
            project_id=project_id,
            document_paths=doc_paths,
            npz_path=npz_path,
            compiled_model=compiled_model,
            tokenizer=tokenizer,
        )
        self._embed_worker.processing_complete.connect(self._on_embed_complete)
        self._embed_worker.processing_failed.connect(self._on_embed_failed)
        self._embed_worker.start()
        logger.info(f"Project embedding started for project {project_id}")

    def _on_embed_complete(self, project_id: int) -> None:
        logger.info(f"Project {project_id} embeddings complete")

    def _on_embed_failed(self, project_id: int, error: str) -> None:
        logger.error(f"Project {project_id} embedding failed: {error}")

    # ── Accept / Reject ────────────────────────────────────────────────────────

    def _on_accept(self) -> None:
        """Validate, save project, and emit project_saved."""
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Name Required", "Please enter a project name.")
            return

        description = self._description_edit.toPlainText().strip() or None
        custom_prompt = self._prompt_edit.toPlainText().strip() or None

        if self._is_create_mode:
            if self._project_id is None:
                # No documents were added, so project row doesn't exist yet
                pid = self.database.create_project(
                    name=name,
                    description=description,
                    custom_prompt=custom_prompt,
                )
            else:
                # Project row was created when first document was added; update it
                pid = self._project_id
                self.database.update_project(
                    project_id=pid,
                    name=name,
                    description=description,
                    custom_prompt=custom_prompt,
                )
        else:
            pid = self._project_id
            self.database.update_project(
                project_id=pid,
                name=name,
                description=description,
                custom_prompt=custom_prompt,
            )

        logger.info(f"Project {pid} saved")
        self.project_saved.emit(pid)
        self.accept()

    def _on_reject(self) -> None:
        """Cancel: if project was pre-created in create mode, delete it."""
        if self._is_create_mode and self._project_created and self._project_id is not None:
            try:
                self.database.delete_project(self._project_id)
                project_dir = PROJECTS_DIR / str(self._project_id)
                if project_dir.exists():
                    shutil.rmtree(str(project_dir))
                logger.info(f"Cancelled: deleted staged project {self._project_id}")
            except Exception as e:
                logger.warning(f"Could not clean up staged project: {e}")
        self.reject()
