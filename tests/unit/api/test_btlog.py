# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from warehouse.api import btlog


class TestTransparencyInfo:
    def test_transparency_info_not_present(self, db_request):
        file = pretend.stub(
            transparency_log=None,
            filename="pkg-1.0.tar.gz",
        )
        db_request.response = pretend.stub(
            content_type=None,
            headers={},
        )

        response = btlog.transparency_info(file, db_request)

        assert response.status_code == 404
        assert response.json == {"message": "No transparency log entry for pkg-1.0.tar.gz"}

    def test_transparency_info_success(self, db_request):
        file = pretend.stub(
            transparency_log=pretend.stub(
                log_entry={"inclusion_proof": "...", "entry_id": "123"}
            ),
        )
        db_request.response = pretend.stub(
            content_type=None,
            headers={},
        )

        result = btlog.transparency_info(file, db_request)

        assert result == {"inclusion_proof": "...", "entry_id": "123"}
        assert db_request.response.content_type == "application/json"

    def test_transparency_info_sets_cors_headers(self, db_request):
        file = pretend.stub(
            transparency_log=pretend.stub(
                log_entry={"inclusion_proof": "test"}
            ),
        )
        headers = {}
        db_request.response = pretend.stub(
            content_type=None,
            headers=headers,
        )

        btlog.transparency_info(file, db_request)

        assert "Access-Control-Allow-Origin" in headers
        assert headers["Access-Control-Allow-Origin"] == "*"
