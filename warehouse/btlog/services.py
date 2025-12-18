# SPDX-License-Identifier: Apache-2.0

from requests.exceptions import RequestException
from zope.interface import implementer

from warehouse.btlog.interfaces import IBinaryTransparencyLogService


class BinaryTransparencyLogError(Exception):
    pass


@implementer(IBinaryTransparencyLogService)
class BinaryTransparencyLogService:
    def __init__(self, *, session, endpoint):
        self.http = session
        self.endpoint = endpoint

    @classmethod
    def create_service(cls, _context, request):
        return cls(
            session=request.http,
            endpoint=request.registry.settings.get(
                "btlog.endpoint", "http://localhost:8181"
            ),
        )

    def submit_entry(self, *, checksum, filename):
        try:
            resp = self.http.post(
                f"{self.endpoint}/add",
                json={"checksum": checksum, "filename": filename},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except RequestException as e:
            raise BinaryTransparencyLogError(
                f"Failed to submit to transparency log: {e}"
            ) from e
