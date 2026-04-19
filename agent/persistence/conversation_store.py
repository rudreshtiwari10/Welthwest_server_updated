"""
MongoDB-backed conversation storage for the Welth agent.

Collection: welth_conversations
Document schema:
    {
        _id: ObjectId,
        user_id: str,
        title: str | None,
        messages: [{role, content, tool_calls?, timestamp}],
        summary: str | None,
        created_at: datetime,
        updated_at: datetime,
        message_count: int,
        deleted: bool,
    }

Collection: welth_message_feedback
Document schema:
    {
        _id: ObjectId,
        conversation_id: str,
        message_index: int,
        user_id: str,
        rating: "up" | "down",
        comment: str | None,
        created_at: datetime,
    }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationStore:
    """CRUD operations for Welth agent conversations."""

    COLLECTION = "welth_conversations"
    FEEDBACK_COLLECTION = "welth_message_feedback"

    def __init__(self, db=None):
        """
        Args:
            db: A pymongo Database instance. If None, uses the lazy database
                from database/__init__.py (project standard).
        """
        self._db = db

    @property
    def _col(self):
        if self._db is None:
            from database import get_db
            self._db = get_db()
        return self._db[self.COLLECTION]

    @property
    def _feedback_col(self):
        if self._db is None:
            from database import get_db
            self._db = get_db()
        return self._db[self.FEEDBACK_COLLECTION]

    # ---- Create -------------------------------------------------------------

    def create_conversation(self, user_id: str) -> str:
        """Create a new empty conversation. Returns conversation_id as string."""
        doc = {
            "user_id": user_id,
            "title": None,
            "messages": [],
            "summary": None,
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
            "message_count": 0,
            "deleted": False,
        }
        result = self._col.insert_one(doc)
        return str(result.inserted_id)

    # ---- Read ---------------------------------------------------------------

    def get_conversation(self, conversation_id: str, user_id: str) -> Optional[dict]:
        """Load a full conversation by ID. Returns None if not found or wrong user."""
        try:
            doc = self._col.find_one({
                "_id": ObjectId(conversation_id),
                "user_id": user_id,
                "deleted": {"$ne": True},
            })
        except Exception:
            return None
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def list_conversations(
        self, user_id: str, *, skip: int = 0, limit: int = 20
    ) -> list[dict]:
        """List conversations for a user, newest first."""
        cursor = (
            self._col
            .find(
                {"user_id": user_id, "deleted": {"$ne": True}},
                {"messages": 0},  # exclude messages for list view
            )
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )
        results = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    # ---- Update -------------------------------------------------------------

    def append_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        *,
        tool_calls: Optional[list[dict]] = None,
    ) -> bool:
        """Append a message to a conversation. Returns True on success."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": _utcnow(),
        }
        if tool_calls:
            msg["tool_calls"] = tool_calls

        result = self._col.update_one(
            {
                "_id": ObjectId(conversation_id),
                "user_id": user_id,
                "deleted": {"$ne": True},
            },
            {
                "$push": {"messages": msg},
                "$inc": {"message_count": 1},
                "$set": {"updated_at": _utcnow()},
            },
        )
        return result.modified_count > 0

    def set_title(self, conversation_id: str, user_id: str, title: str) -> bool:
        """Set or update the conversation title."""
        result = self._col.update_one(
            {"_id": ObjectId(conversation_id), "user_id": user_id},
            {"$set": {"title": title, "updated_at": _utcnow()}},
        )
        return result.modified_count > 0

    def set_summary(self, conversation_id: str, user_id: str, summary: str) -> bool:
        """Update the running summary."""
        result = self._col.update_one(
            {"_id": ObjectId(conversation_id), "user_id": user_id},
            {"$set": {"summary": summary, "updated_at": _utcnow()}},
        )
        return result.modified_count > 0

    # ---- Delete (soft) ------------------------------------------------------

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Soft-delete a conversation."""
        result = self._col.update_one(
            {"_id": ObjectId(conversation_id), "user_id": user_id},
            {"$set": {"deleted": True, "updated_at": _utcnow()}},
        )
        return result.modified_count > 0

    # ---- Feedback -----------------------------------------------------------

    def add_feedback(
        self,
        conversation_id: str,
        message_index: int,
        user_id: str,
        rating: str,
        comment: Optional[str] = None,
    ) -> str:
        """Add thumbs up/down feedback on a message. Returns feedback_id."""
        doc = {
            "conversation_id": conversation_id,
            "message_index": message_index,
            "user_id": user_id,
            "rating": rating,
            "comment": comment,
            "created_at": _utcnow(),
        }
        result = self._feedback_col.insert_one(doc)
        return str(result.inserted_id)
