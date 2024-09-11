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

import packaging.utils
import pretend

from pypi_attestations import Attestation
from sigstore.verify import Verifier
from webtest.forms import Upload

from tests.common.db.oidc import GitHubPublisherFactory
from tests.common.db.packaging import ProjectFactory
from warehouse.macaroons import caveats
from warehouse.macaroons.services import DatabaseMacaroonService
from warehouse.packaging import Release


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
_WHEEL_PACKAGE = _ASSETS / "pypi_hello_world-0.1.0-py3-none-any.whl"


class TestPackageWithAttestations:

    def upload_package(
        self, webtest, monkeypatch, project, wheel_filename: Path, publisher
    ):

        name, version, _, __ = packaging.utils.parse_wheel_filename(wheel_filename.name)
        attestation = Attestation.model_validate_json(
            (
                wheel_filename.parent / f"{wheel_filename.name}.publish.attestation"
            ).read_text()
        )

        md5_digest = hashlib.file_digest(wheel_filename.open("rb"), "md5").hexdigest()

        data = collections.OrderedDict(
            {
                ":action": "file_upload",
                "metadata_version": "1.2",
                "name": project.name,
                "attestations": f"[{attestation.model_dump_json()}]",
                "version": str(version),
                "filetype": "bdist_wheel",
                "pyversion": "cp312",
                "md5_digest": md5_digest,
                "content": (
                    Upload(
                        wheel_filename.name,
                        wheel_filename.read_bytes(),
                        "application/tar",
                    )
                ),
            }
        )

        db_session = webtest.extra_environ["warehouse.db_session"]
        macaroon_service = DatabaseMacaroonService(db_session)
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

        resp = webtest.post("/legacy/", params=data)

        assert resp.status_code == HTTPStatus.OK

        release_db = db_session.query(Release).filter(Release.project == project).one()
        release_file = release_db.files[0]
        assert release_file.filename == wheel_filename.name


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

        project_name = "pypi_hello_world"
        project = ProjectFactory.create(name=project_name)

        # Shortcut here: we directly associate our publisher to the project
        publisher = GitHubPublisherFactory.create(projects=[project])

        self.upload_package(webtest, monkeypatch, project, _WHEEL_PACKAGE, publisher)
        self.view_package(webtest, project)
