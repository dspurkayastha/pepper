"""Database tables.

Nothing here holds patient identifiers: cases link to the phone's encrypted
identity store through `local_ref`, an opaque ID generated on the device.
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pepper.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(20), default="ios")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    apns_token: Mapped[str | None] = mapped_column(String(200), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Thread(Base):
    """One Anthropic session, shown in the app as a thread on the river."""

    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lane: Mapped[str] = mapped_column(String(20), default="company")
    origin: Mapped[str] = mapped_column(String(20), default="app")  # app | scheduled
    state: Mapped[str] = mapped_column(String(20), default="idle")  # idle|working|needs_you|error|terminated|archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ThreadEvent(Base):
    """App-facing events. `id` is monotonically increasing and doubles as the SSE id."""

    __tablename__ = "thread_events"
    __table_args__ = (UniqueConstraint("thread_id", "source_event_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Decision(Base):
    """A structured question from Pepper (the `escalate` tool), answered in the app."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), index=True)
    tool_use_id: Mapped[str] = mapped_column(String(80), unique=True)
    lane: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(30))
    question: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str | None] = mapped_column(String(40), nullable=True)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    risky: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | resolved
    choice: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Credential(Base):
    """Metadata for a secret stored in the Anthropic vault. The secret itself never lands here."""

    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    secret_name: Mapped[str] = mapped_column(String(80), unique=True)
    vault_credential_id: Mapped[str] = mapped_column(String(80))
    allowed_hosts: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    local_ref: Mapped[str] = mapped_column(String(36), index=True)
    template: Mapped[str] = mapped_column(String(20), index=True)
    performed_on: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | confirmed
    histopath_status: Mapped[str] = mapped_column(String(20))  # not_applicable | pending | reported
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    histopath: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    complications: Mapped[dict] = mapped_column(JSON, default=dict)  # {"30": {...}, "90": {...}}
    ot_list_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OtList(Base):
    __tablename__ = "ot_lists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(20))  # whatsapp_text | paper_photo | screenshot
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | confirmed
    items: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookReceipt(Base):
    """Deduplicates Anthropic webhook deliveries (retries reuse the event id)."""

    __tablename__ = "webhook_receipts"

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
