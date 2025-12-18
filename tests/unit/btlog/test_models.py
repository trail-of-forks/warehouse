# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.common.db.packaging import FileFactory
from warehouse.btlog.models import TransparencyLogEntry


class TestTransparencyLogEntry:
    def test_create(self, db_session):
        file = FileFactory.create()
        entry = TransparencyLogEntry(
            file=file,
            log_entry={"inclusion_proof": "...", "entry_id": "123"},
        )
        db_session.add(entry)
        db_session.flush()

        assert entry.id is not None
        assert entry.file_id == file.id
        assert entry.log_entry == {"inclusion_proof": "...", "entry_id": "123"}

    def test_file_relationship(self, db_session):
        file = FileFactory.create()
        entry = TransparencyLogEntry(
            file=file,
            log_entry={"inclusion_proof": "test"},
        )
        db_session.add(entry)
        db_session.flush()

        # Verify bidirectional relationship
        assert entry.file is file
        assert file.transparency_log is entry

    def test_cascade_delete(self, db_session):
        file = FileFactory.create()
        entry = TransparencyLogEntry(
            file=file,
            log_entry={"inclusion_proof": "test"},
        )
        db_session.add(entry)
        db_session.flush()

        entry_id = entry.id

        # Delete the file - entry should be deleted too
        db_session.delete(file.release)
        db_session.flush()

        # Entry should no longer exist
        result = db_session.query(TransparencyLogEntry).filter_by(id=entry_id).first()
        assert result is None
