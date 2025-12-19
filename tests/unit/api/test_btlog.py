# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.api import btlog


class TestTransparencyInfo:
    def test_transparency_info_not_present(self):
        file = pretend.stub(
            transparency_log=None,
            filename="pkg-1.0.tar.gz",
        )
        request = pretend.stub(
            response=pretend.stub(
                content_type=None,
                headers={},
            ),
        )

        response = btlog.transparency_info(file, request)

        assert response.status_code == 404
        assert response.json == {"message": "No transparency log entry for pkg-1.0.tar.gz"}

    def test_transparency_info_success(self):
        # The stored log_entry already has the full structure from upload time
        stored_log_entry = {
            "version": 1,
            "log_origin": "bt-log.pypi.org",
            "entry_index": 12345,
            "entry": {
                "checksum": "sha256:abc123",
                "filename": "pkg-1.0.tar.gz",
            },
            "checkpoint": "base64checkpoint",
            "inclusion_proof": ["hash1", "hash2"],
        }
        file = pretend.stub(
            transparency_log=pretend.stub(log_entry=stored_log_entry),
        )
        request = pretend.stub(
            response=pretend.stub(
                content_type=None,
                headers={},
            ),
        )

        result = btlog.transparency_info(file, request)

        assert result == stored_log_entry
        assert request.response.content_type == "application/json"

    def test_transparency_info_sets_cors_headers(self):
        file = pretend.stub(
            transparency_log=pretend.stub(
                log_entry={"version": 1, "entry": {}}
            ),
        )
        headers = {}
        request = pretend.stub(
            response=pretend.stub(
                content_type=None,
                headers=headers,
            ),
        )

        btlog.transparency_info(file, request)

        assert "Access-Control-Allow-Origin" in headers
        assert headers["Access-Control-Allow-Origin"] == "*"
