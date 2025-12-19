# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest
from requests.exceptions import RequestException
from zope.interface.verify import verifyClass

from warehouse.btlog.interfaces import IBinaryTransparencyLogService
from warehouse.btlog.services import (
    BinaryTransparencyLogError,
    BinaryTransparencyLogService,
)


class TestBinaryTransparencyLogService:
    def test_interface_matches(self):
        assert verifyClass(IBinaryTransparencyLogService, BinaryTransparencyLogService)

    def test_create_service(self):
        http = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(
                settings={"btlog.endpoint": "http://localhost:8181"},
            ),
            http=http,
        )

        service = BinaryTransparencyLogService.create_service(None, request)

        assert service.endpoint == "http://localhost:8181"
        assert service.http is http

    def test_create_service_default_endpoint(self):
        http = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(
                settings={},
            ),
            http=http,
        )

        service = BinaryTransparencyLogService.create_service(None, request)

        assert service.endpoint == "http://localhost:8181"

    def test_submit_entry_success(self):
        response = pretend.stub(
            json=lambda: {"inclusion_proof": "...", "entry_id": "123"},
            raise_for_status=lambda: None,
        )
        http = pretend.stub(post=pretend.call_recorder(lambda *a, **kw: response))

        service = BinaryTransparencyLogService(session=http, endpoint="http://localhost:8181")
        result = service.submit_entry(checksum="abc123", filename="pkg-1.0.tar.gz")

        assert result == {"inclusion_proof": "...", "entry_id": "123"}
        assert http.post.calls == [
            pretend.call(
                "http://localhost:8181/add",
                json={"checksum": "abc123", "filename": "pkg-1.0.tar.gz"},
                timeout=10,
            )
        ]

    def test_submit_entry_failure(self):
        http = pretend.stub(post=pretend.raiser(RequestException("Connection failed")))

        service = BinaryTransparencyLogService(session=http, endpoint="http://localhost:8181")

        with pytest.raises(BinaryTransparencyLogError, match="Connection failed"):
            service.submit_entry(checksum="abc123", filename="pkg-1.0.tar.gz")

    def test_submit_entry_http_error(self):
        def raise_for_status():
            from requests import HTTPError

            raise HTTPError("500 Server Error")

        response = pretend.stub(raise_for_status=raise_for_status)
        http = pretend.stub(post=lambda *a, **kw: response)

        service = BinaryTransparencyLogService(session=http, endpoint="http://localhost:8181")

        with pytest.raises(BinaryTransparencyLogError, match="500 Server Error"):
            service.submit_entry(checksum="abc123", filename="pkg-1.0.tar.gz")
