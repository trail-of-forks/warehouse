# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


class IBinaryTransparencyLogService(Interface):
    def submit_entry(*, checksum: str, filename: str) -> dict:
        """Submit file to transparency log. Returns log entry response."""
