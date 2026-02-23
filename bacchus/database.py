"""
Database operations for Bacchus.

Handles SQLite database creation, CRUD operations for conversations and messages.
Database location: %APPDATA%/Bacchus/conversations/bacchus.db
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class Project:
    """Project data object."""
    id: int
    name: str
    created_at: str
    updated_at: str
    description: Optional[str] = None
    custom_prompt: Optional[str] = None


@dataclass
class ProjectDocument:
    """Project document data object."""
    id: int
    project_id: int
    file_path: str
    file_name: str
    created_at: str


@dataclass
class Conversation:
    """Conversation data object."""
    id: int
    title: str
    created_at: str
    updated_at: str
    model_name: Optional[str] = None
    document_path: Optional[str] = None
    document_content: Optional[str] = None
    rag_enabled: bool = False
    project_id: Optional[int] = None


@dataclass
class Message:
    """Message data object."""
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: str
    rag_sources: Optional[str] = None
    mcp_calls: Optional[str] = None
    image_path: Optional[str] = None
    image_description: Optional[str] = None


def get_database_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    """
    Create and return a database connection.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        SQLite connection object with row factory set
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """
    Create database tables if they don't exist.

    Creates:
        - conversations: Stores conversation metadata
        - messages: Stores individual messages with foreign key to conversations
        - projects: Stores project metadata
        - project_documents: Stores documents associated with projects

    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()

    # Create conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            model_name TEXT,
            document_path TEXT,
            document_content TEXT,
            rag_enabled INTEGER DEFAULT 0
        )
    """)

    # Create messages table with foreign key
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            rag_sources TEXT,
            mcp_calls TEXT,
            image_path TEXT,
            image_description TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)

    # Create projects table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            custom_prompt TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create project_documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: add image_path column to existing databases
    try:
        cursor.execute("ALTER TABLE messages ADD COLUMN image_path TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists

    # Migration: add image_description column to existing databases
    try:
        cursor.execute("ALTER TABLE messages ADD COLUMN image_description TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migration: add project_id column to conversations
    try:
        cursor.execute("ALTER TABLE conversations ADD COLUMN project_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Enable foreign key support
    cursor.execute("PRAGMA foreign_keys = ON")

    conn.commit()


def create_conversation(
    conn: sqlite3.Connection,
    title: str,
    model_name: Optional[str] = None,
    document_path: Optional[str] = None,
    document_content: Optional[str] = None,
    rag_enabled: bool = False
) -> int:
    """
    Create a new conversation.

    Args:
        conn: SQLite database connection
        title: Conversation title (truncated to 100 chars)
        model_name: Name of the model used
        document_path: Path to attached document
        document_content: Content of attached document
        rag_enabled: Whether RAG is enabled for this conversation

    Returns:
        ID of the created conversation
    """
    # Truncate title to 100 characters
    title = title[:100]

    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO conversations (
            title, created_at, updated_at, model_name,
            document_path, document_content, rag_enabled
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        title, now, now, model_name,
        document_path, document_content, 1 if rag_enabled else 0
    ))

    conn.commit()
    return cursor.lastrowid


def add_message(
    conn: sqlite3.Connection,
    conversation_id: int,
    role: str,
    content: str,
    rag_sources: Optional[List[Dict]] = None,
    mcp_calls: Optional[List[Dict]] = None,
    image_path: Optional[str] = None,
    image_description: Optional[str] = None
) -> int:
    """
    Add a message to a conversation.

    Args:
        conn: SQLite database connection
        conversation_id: ID of the conversation
        role: Message role ("user" or "assistant")
        content: Message content
        rag_sources: List of RAG source references (stored as JSON)
        mcp_calls: List of MCP tool calls (stored as JSON)
        image_path: Optional path to attached image (VLM messages)
        image_description: Optional text description of attached image

    Returns:
        ID of the created message
    """
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Convert lists to JSON strings
    rag_sources_json = json.dumps(rag_sources) if rag_sources else None
    mcp_calls_json = json.dumps(mcp_calls) if mcp_calls else None

    cursor.execute("""
        INSERT INTO messages (
            conversation_id, role, content, created_at,
            rag_sources, mcp_calls, image_path, image_description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        conversation_id, role, content, now,
        rag_sources_json, mcp_calls_json, image_path, image_description
    ))

    # Update conversation's updated_at timestamp
    cursor.execute("""
        UPDATE conversations SET updated_at = ? WHERE id = ?
    """, (now, conversation_id))

    conn.commit()
    return cursor.lastrowid


def get_conversation_messages(
    conn: sqlite3.Connection,
    conversation_id: int
) -> List[Dict[str, Any]]:
    """
    Get all messages for a conversation in chronological order.

    Args:
        conn: SQLite database connection
        conversation_id: ID of the conversation

    Returns:
        List of message dictionaries
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, conversation_id, role, content, created_at,
               rag_sources, mcp_calls, image_path, image_description
        FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, (conversation_id,))

    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_conversation(
    conn: sqlite3.Connection,
    conversation_id: int
) -> Optional[Dict[str, Any]]:
    """
    Get a conversation by ID.

    Args:
        conn: SQLite database connection
        conversation_id: ID of the conversation

    Returns:
        Conversation dictionary or None if not found
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, created_at, updated_at, model_name,
               document_path, document_content, rag_enabled, project_id
        FROM conversations
        WHERE id = ?
    """, (conversation_id,))

    row = cursor.fetchone()
    return dict(row) if row else None


def delete_conversation(conn: sqlite3.Connection, conversation_id: int) -> None:
    """
    Delete a conversation and all its messages.

    Args:
        conn: SQLite database connection
        conversation_id: ID of the conversation to delete
    """
    cursor = conn.cursor()

    # Delete messages first (in case foreign keys not enforced)
    cursor.execute(
        "DELETE FROM messages WHERE conversation_id = ?",
        (conversation_id,)
    )

    # Delete conversation
    cursor.execute(
        "DELETE FROM conversations WHERE id = ?",
        (conversation_id,)
    )

    conn.commit()


def update_message(
    conn: sqlite3.Connection,
    message_id: int,
    content: Optional[str] = None,
    rag_sources: Optional[List[Dict]] = None,
    mcp_calls: Optional[List[Dict]] = None
) -> None:
    """
    Update a message's content or metadata.

    Args:
        conn: SQLite database connection
        message_id: ID of the message to update
        content: New content (if updating)
        rag_sources: New RAG sources (if updating)
        mcp_calls: New MCP calls (if updating)
    """
    cursor = conn.cursor()
    updates = []
    params = []

    if content is not None:
        updates.append("content = ?")
        params.append(content)

    if rag_sources is not None:
        updates.append("rag_sources = ?")
        params.append(json.dumps(rag_sources))

    if mcp_calls is not None:
        updates.append("mcp_calls = ?")
        params.append(json.dumps(mcp_calls))

    if updates:
        params.append(message_id)
        cursor.execute(
            f"UPDATE messages SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()


def update_message_image_description(
    conn: sqlite3.Connection,
    message_id: int,
    image_description: str
) -> None:
    """
    Set the image_description for a message.

    Args:
        conn: SQLite database connection
        message_id: ID of the message to update
        image_description: Text description of the attached image
    """
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE messages SET image_description = ? WHERE id = ?",
        (image_description, message_id)
    )
    conn.commit()


def list_conversations(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    List all conversations ordered by most recently updated.

    Args:
        conn: SQLite database connection

    Returns:
        List of conversation dictionaries
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, created_at, updated_at, model_name,
               document_path, rag_enabled, project_id
        FROM conversations
        ORDER BY updated_at DESC
    """)

    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def update_conversation(
    conn: sqlite3.Connection,
    conversation_id: int,
    title: Optional[str] = None,
    model_name: Optional[str] = None,
    document_path: Optional[str] = None,
    document_content: Optional[str] = None,
    rag_enabled: Optional[bool] = None
) -> None:
    """
    Update conversation metadata.

    Args:
        conn: SQLite database connection
        conversation_id: ID of the conversation
        title: New title (if updating)
        model_name: New model name (if updating)
        document_path: New document path (if updating)
        document_content: New document content (if updating)
        rag_enabled: New RAG enabled state (if updating)
    """
    cursor = conn.cursor()
    updates = []
    params = []

    if title is not None:
        updates.append("title = ?")
        params.append(title[:100])  # Truncate to 100 chars

    if model_name is not None:
        updates.append("model_name = ?")
        params.append(model_name)

    if document_path is not None:
        updates.append("document_path = ?")
        params.append(document_path)

    if document_content is not None:
        updates.append("document_content = ?")
        params.append(document_content)

    if rag_enabled is not None:
        updates.append("rag_enabled = ?")
        params.append(1 if rag_enabled else 0)

    if updates:
        # Always update the updated_at timestamp
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())

        params.append(conversation_id)
        cursor.execute(
            f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()


def clear_conversation_document(
    conn: sqlite3.Connection,
    conversation_id: int
) -> None:
    """
    Clear document fields from a conversation (set to NULL).

    Used when the user removes an attached document.

    Args:
        conn: SQLite database connection
        conversation_id: ID of the conversation
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE conversations
        SET document_path = NULL,
            document_content = NULL,
            rag_enabled = 0,
            updated_at = ?
        WHERE id = ?
        """,
        (datetime.now().isoformat(), conversation_id)
    )
    conn.commit()


def delete_messages_after(
    conn: sqlite3.Connection,
    conversation_id: int,
    message_id: int
) -> None:
    """
    Delete all messages after a specified message ID.

    Used when editing a previous message to remove subsequent messages.

    Args:
        conn: SQLite database connection
        conversation_id: ID of the conversation
        message_id: ID of the message to keep (all after this are deleted)
    """
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM messages
        WHERE conversation_id = ? AND id > ?
    """, (conversation_id, message_id))

    conn.commit()


# ── Project functions ──────────────────────────────────────────────────────────

def create_project(
    conn: sqlite3.Connection,
    name: str,
    description: Optional[str] = None,
    custom_prompt: Optional[str] = None
) -> int:
    """
    Create a new project.

    Args:
        conn: SQLite database connection
        name: Project name
        description: Optional project description
        custom_prompt: Optional custom system prompt appended after base prompt

    Returns:
        ID of the created project
    """
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO projects (name, description, custom_prompt, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (name, description, custom_prompt, now, now))
    conn.commit()
    return cursor.lastrowid


def get_project(
    conn: sqlite3.Connection,
    project_id: int
) -> Optional[Dict[str, Any]]:
    """
    Get a project by ID.

    Args:
        conn: SQLite database connection
        project_id: ID of the project

    Returns:
        Project dictionary or None if not found
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, description, custom_prompt, created_at, updated_at
        FROM projects WHERE id = ?
    """, (project_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def list_projects(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    List all projects ordered by name.

    Args:
        conn: SQLite database connection

    Returns:
        List of project dictionaries
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, description, custom_prompt, created_at, updated_at
        FROM projects ORDER BY name ASC
    """)
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def update_project(
    conn: sqlite3.Connection,
    project_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    custom_prompt: Optional[str] = None
) -> None:
    """
    Update project metadata.

    Args:
        conn: SQLite database connection
        project_id: ID of the project to update
        name: New name (if updating)
        description: New description (if updating)
        custom_prompt: New custom prompt (if updating)
    """
    cursor = conn.cursor()
    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)

    if description is not None:
        updates.append("description = ?")
        params.append(description)

    if custom_prompt is not None:
        updates.append("custom_prompt = ?")
        params.append(custom_prompt)

    if updates:
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(project_id)
        cursor.execute(
            f"UPDATE projects SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()


def delete_project(conn: sqlite3.Connection, project_id: int) -> None:
    """
    Delete a project and unassign its conversations.

    SQLite's ALTER TABLE ADD COLUMN ignores REFERENCES, so we manually
    NULL out the project_id before deleting.

    Args:
        conn: SQLite database connection
        project_id: ID of the project to delete
    """
    cursor = conn.cursor()
    # Unassign conversations from this project
    cursor.execute(
        "UPDATE conversations SET project_id = NULL WHERE project_id = ?",
        (project_id,)
    )
    # Delete project (cascades to project_documents)
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()


def add_project_document(
    conn: sqlite3.Connection,
    project_id: int,
    file_path: str,
    file_name: str
) -> int:
    """
    Add a document to a project.

    Args:
        conn: SQLite database connection
        project_id: ID of the project
        file_path: Full path to the document file
        file_name: Display name of the document

    Returns:
        ID of the created project_document row
    """
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO project_documents (project_id, file_path, file_name, created_at)
        VALUES (?, ?, ?, ?)
    """, (project_id, file_path, file_name, now))
    conn.commit()
    return cursor.lastrowid


def remove_project_document(conn: sqlite3.Connection, document_id: int) -> None:
    """
    Remove a document from a project.

    Args:
        conn: SQLite database connection
        document_id: ID of the project_document row to remove
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM project_documents WHERE id = ?", (document_id,))
    conn.commit()


def list_project_documents(
    conn: sqlite3.Connection,
    project_id: int
) -> List[Dict[str, Any]]:
    """
    List all documents for a project.

    Args:
        conn: SQLite database connection
        project_id: ID of the project

    Returns:
        List of project_document dictionaries
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, project_id, file_path, file_name, created_at
        FROM project_documents WHERE project_id = ?
        ORDER BY created_at ASC
    """, (project_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_project_conversations(
    conn: sqlite3.Connection,
    project_id: int
) -> List[Dict[str, Any]]:
    """
    Get all conversations belonging to a project.

    Args:
        conn: SQLite database connection
        project_id: ID of the project

    Returns:
        List of conversation dictionaries
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, created_at, updated_at, model_name,
               document_path, rag_enabled, project_id
        FROM conversations
        WHERE project_id = ?
        ORDER BY updated_at DESC
    """, (project_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def assign_conversation_to_project(
    conn: sqlite3.Connection,
    conversation_id: int,
    project_id: int
) -> None:
    """
    Assign a conversation to a project.

    Args:
        conn: SQLite database connection
        conversation_id: ID of the conversation
        project_id: ID of the project
    """
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE conversations SET project_id = ? WHERE id = ?",
        (project_id, conversation_id)
    )
    conn.commit()


def list_unassigned_conversations(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    List conversations not assigned to any project.

    Args:
        conn: SQLite database connection

    Returns:
        List of conversation dictionaries where project_id IS NULL
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, created_at, updated_at, model_name,
               document_path, rag_enabled, project_id
        FROM conversations
        WHERE project_id IS NULL
        ORDER BY updated_at DESC
    """)
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


class Database:
    """
    Database wrapper class for PyQt6 UI components.

    Provides an object-oriented interface to the database functions.
    """

    def __init__(self, db_path: Union[str, Path]):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.conn = get_database_connection(self.db_path)
        create_tables(self.conn)

    def create_conversation(
        self,
        title: str,
        model_name: Optional[str] = None,
        document_path: Optional[str] = None,
        document_content: Optional[str] = None,
        rag_enabled: bool = False
    ) -> int:
        """Create a new conversation."""
        return create_conversation(
            self.conn, title, model_name, document_path, document_content, rag_enabled
        )

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        rag_sources: Optional[List[Dict]] = None,
        mcp_calls: Optional[List[Dict]] = None,
        image_path: Optional[str] = None,
        image_description: Optional[str] = None
    ) -> int:
        """Add a message to a conversation."""
        return add_message(
            self.conn, conversation_id, role, content, rag_sources, mcp_calls,
            image_path, image_description
        )

    def get_conversation_messages(self, conversation_id: int) -> List[Message]:
        """Get all messages for a conversation."""
        dicts = get_conversation_messages(self.conn, conversation_id)
        return [
            Message(
                id=d['id'],
                conversation_id=d['conversation_id'],
                role=d['role'],
                content=d['content'],
                created_at=d['created_at'],
                rag_sources=d.get('rag_sources'),
                mcp_calls=d.get('mcp_calls'),
                image_path=d.get('image_path'),
                image_description=d.get('image_description')
            )
            for d in dicts
        ]

    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        """Get a conversation by ID."""
        data = get_conversation(self.conn, conversation_id)
        if data is None:
            return None
        return Conversation(
            id=data['id'],
            title=data['title'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            model_name=data.get('model_name'),
            document_path=data.get('document_path'),
            document_content=data.get('document_content'),
            rag_enabled=bool(data.get('rag_enabled', 0)),
            project_id=data.get('project_id')
        )

    def delete_conversation(self, conversation_id: int) -> None:
        """Delete a conversation and all its messages."""
        delete_conversation(self.conn, conversation_id)

    def clear_conversation_document(self, conversation_id: int) -> None:
        """Clear document fields from a conversation (set to NULL)."""
        clear_conversation_document(self.conn, conversation_id)

    def update_message(
        self,
        message_id: int,
        content: Optional[str] = None,
        rag_sources: Optional[List[Dict]] = None,
        mcp_calls: Optional[List[Dict]] = None
    ) -> None:
        """Update a message."""
        update_message(self.conn, message_id, content, rag_sources, mcp_calls)

    def update_message_image_description(self, message_id: int, image_description: str) -> None:
        """Set the image_description for a message."""
        update_message_image_description(self.conn, message_id, image_description)

    def list_conversations(self) -> List[Conversation]:
        """List all conversations."""
        data_list = list_conversations(self.conn)
        return [
            Conversation(
                id=data['id'],
                title=data['title'],
                created_at=data['created_at'],
                updated_at=data['updated_at'],
                model_name=data.get('model_name'),
                document_path=data.get('document_path'),
                rag_enabled=bool(data.get('rag_enabled', 0)),
                project_id=data.get('project_id')
            )
            for data in data_list
        ]

    def update_conversation(
        self,
        conversation_id: int,
        title: Optional[str] = None,
        model_name: Optional[str] = None,
        document_path: Optional[str] = None,
        document_content: Optional[str] = None,
        rag_enabled: Optional[bool] = None
    ) -> None:
        """Update conversation metadata."""
        update_conversation(
            self.conn, conversation_id, title, model_name,
            document_path, document_content, rag_enabled
        )

    def delete_messages_after(
        self,
        conversation_id: int,
        message_id: int
    ) -> None:
        """Delete all messages after a specified message ID."""
        delete_messages_after(self.conn, conversation_id, message_id)

    # ── Project wrapper methods ────────────────────────────────────────────────

    def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        custom_prompt: Optional[str] = None
    ) -> int:
        """Create a new project."""
        return create_project(self.conn, name, description, custom_prompt)

    def get_project(self, project_id: int) -> Optional[Project]:
        """Get a project by ID."""
        data = get_project(self.conn, project_id)
        if data is None:
            return None
        return Project(
            id=data['id'],
            name=data['name'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            description=data.get('description'),
            custom_prompt=data.get('custom_prompt')
        )

    def list_projects(self) -> List[Project]:
        """List all projects."""
        data_list = list_projects(self.conn)
        return [
            Project(
                id=data['id'],
                name=data['name'],
                created_at=data['created_at'],
                updated_at=data['updated_at'],
                description=data.get('description'),
                custom_prompt=data.get('custom_prompt')
            )
            for data in data_list
        ]

    def update_project(
        self,
        project_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        custom_prompt: Optional[str] = None
    ) -> None:
        """Update project metadata."""
        update_project(self.conn, project_id, name, description, custom_prompt)

    def delete_project(self, project_id: int) -> None:
        """Delete a project and unassign its conversations."""
        delete_project(self.conn, project_id)

    def add_project_document(
        self,
        project_id: int,
        file_path: str,
        file_name: str
    ) -> int:
        """Add a document to a project."""
        return add_project_document(self.conn, project_id, file_path, file_name)

    def remove_project_document(self, document_id: int) -> None:
        """Remove a document from a project."""
        remove_project_document(self.conn, document_id)

    def list_project_documents(self, project_id: int) -> List[ProjectDocument]:
        """List all documents for a project."""
        data_list = list_project_documents(self.conn, project_id)
        return [
            ProjectDocument(
                id=data['id'],
                project_id=data['project_id'],
                file_path=data['file_path'],
                file_name=data['file_name'],
                created_at=data['created_at']
            )
            for data in data_list
        ]

    def get_project_conversations(self, project_id: int) -> List[Conversation]:
        """Get all conversations belonging to a project."""
        data_list = get_project_conversations(self.conn, project_id)
        return [
            Conversation(
                id=data['id'],
                title=data['title'],
                created_at=data['created_at'],
                updated_at=data['updated_at'],
                model_name=data.get('model_name'),
                document_path=data.get('document_path'),
                rag_enabled=bool(data.get('rag_enabled', 0)),
                project_id=data.get('project_id')
            )
            for data in data_list
        ]

    def assign_conversation_to_project(
        self,
        conversation_id: int,
        project_id: int
    ) -> None:
        """Assign a conversation to a project."""
        assign_conversation_to_project(self.conn, conversation_id, project_id)

    def list_unassigned_conversations(self) -> List[Conversation]:
        """List conversations not assigned to any project."""
        data_list = list_unassigned_conversations(self.conn)
        return [
            Conversation(
                id=data['id'],
                title=data['title'],
                created_at=data['created_at'],
                updated_at=data['updated_at'],
                model_name=data.get('model_name'),
                document_path=data.get('document_path'),
                rag_enabled=bool(data.get('rag_enabled', 0)),
                project_id=data.get('project_id')
            )
            for data in data_list
        ]

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
