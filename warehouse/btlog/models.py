# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from uuid import UUID

from sqlalchemy import ForeignKey, Index, orm
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import File


class TransparencyLogEntry(db.Model):
    """
    A table for binary transparency log entries.

    Each entry contains the response from the transparency log service,
    including the inclusion proof and metadata that allows clients to
    verify that a package was logged.
    """

    __tablename__ = "transparency_log_entries"

    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_files.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    file: Mapped[File] = orm.relationship(back_populates="transparency_log")

    # Response from transparency log service (inclusion proof + metadata)
    log_entry: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (Index("ix_transparency_log_entries_file_id", file_id),)
