# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import collections
import hashlib
import time

from datetime import datetime
from http import HTTPStatus
from pathlib import Path

import pretend

from pypi_attestations import Attestation, Envelope, VerificationMaterial
from sigstore.verify import Verifier
from webtest.forms import Upload

from tests.common.db.oidc import GitHubPublisherFactory
from tests.common.db.packaging import ProjectFactory
from warehouse.macaroons import caveats
from warehouse.macaroons.services import DatabaseMacaroonService


def get_macaraoon(macaroon_service, publisher):
    not_before = int(time.time())
    expires_at = not_before + 900
    claims = {"sha": "some-sha", "ref": "some-ref"}

    serialized, dm = macaroon_service.create_macaroon(
        "localhost",
        (f"OpenID token: TODO " f"({datetime.fromtimestamp(not_before).isoformat()})"),
        [
            caveats.OIDCPublisher(
                oidc_publisher_id=str(publisher.id),
            ),
            caveats.ProjectID(project_ids=[str(p.id) for p in publisher.projects]),
            caveats.Expiration(expires_at=expires_at, not_before=not_before),
        ],
        oidc_publisher_id=str(publisher.id),
        additional={"oidc": publisher.stored_claims(claims)},
    )

    return serialized


_HERE = Path(__file__).parent
_ASSETS = _HERE / "assets"
_WHEEL_PACKAGE = _ASSETS / "rfc8785-0.1.2-py3-none-any.whl"


class TestPackageWithAttestations:

    def upload_package(self, webtest, monkeypatch, project, publisher):

        filename = "rfc8785-0.1.2-py3-none-any.whl"
        attestation = Attestation(
            version=1,
            verification_material=VerificationMaterial(
                certificate="some_cert", transparency_entries=[dict()]
            ),
            envelope=Envelope(
                statement="somebase64string",
                signature="somebase64string",
            ),
        )

        md5_digest = hashlib.file_digest(open(_WHEEL_PACKAGE, "rb"), "md5").hexdigest()

        data = collections.OrderedDict(
            {
                ":action": "file_upload",
                "protocol_version": "1",  # TODO(dm)
                "metadata_version": "1.2",
                "name": project.name,
                "attestations": f"[{attestation.model_dump_json()}]",
                "version": "0.1.2",
                "filetype": "bdist_wheel",
                "pyversion": "cp312",
                "md5_digest": md5_digest,
                "content": (
                    Upload(
                        filename, open(_WHEEL_PACKAGE, "rb").read(), "application/tar"
                    )
                ),
            }
        )

        macaroon_service = DatabaseMacaroonService(
            webtest.extra_environ["warehouse.db_session"]
        )
        webtest.set_authorization(
            ("Basic", ("__token__", get_macaraoon(macaroon_service, publisher)))
        )

        verify = pretend.call_recorder(
            lambda _self, _verifier, _policy, _dist: (
                "https://docs.pypi.org/attestations/publish/v1",
                None,
            )
        )
        monkeypatch.setattr(Attestation, "verify", verify)
        monkeypatch.setattr(Verifier, "production", lambda: pretend.stub())

        resp = webtest.post(
            "/legacy/",
            params=data,
        )

        # TODO(DM) Improve testing results here

        assert resp.status_code == HTTPStatus.OK

    def view_package(self, webtest, project):
        resp = webtest.get(f"/simple/{project.normalized_name}/")

        release_version = project.releases[0].version
        release_filename = project.releases[0].files[0].filename

        assert resp.status_code == HTTPStatus.OK
        assert release_filename in resp.text

        # Use simple JSON API
        resp = webtest.get(
            f"/simple/{project.normalized_name}/",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        )
        assert resp.status_code == HTTPStatus.OK
        assert resp.json["files"][0]["filename"] == release_filename

        # Use soon-to-be deprecated legacy API
        # Remove me once deprecated
        resp = webtest.get(f"/pypi/{project.normalized_name}/json")
        assert resp.status_code == HTTPStatus.OK
        assert resp.content_type == "application/json"

        content = resp.json
        assert content["releases"][release_version][0]["filename"] == release_filename

    def test_package(self, webtest, monkeypatch):

        project = ProjectFactory.create(name="rfc8785")
        publisher = GitHubPublisherFactory.create(projects=[project])

        self.upload_package(webtest, monkeypatch, project, publisher)
        self.view_package(webtest, project)
