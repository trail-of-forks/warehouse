# SPDX-License-Identifier: Apache-2.0

from warehouse import db


class TransparencyLogEntry(db.Model):
    __tablename__ = "transparency_log_entries"
    # Will add columns later
