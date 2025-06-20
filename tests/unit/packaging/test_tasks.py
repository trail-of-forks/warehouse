# SPDX-License-Identifier: Apache-2.0

import tempfile

from contextlib import contextmanager

import pretend
import pytest

from google.cloud.bigquery import SchemaField
from wtforms import Field, Form, StringField

import warehouse.packaging.tasks

from warehouse.accounts.models import WebAuthn
from warehouse.packaging.models import DependencyKind, Description
from warehouse.packaging.tasks import (
    check_file_cache_tasks_outstanding,
    compute_2fa_metrics,
    compute_packaging_metrics,
    compute_top_dependents_corpus,
    sync_file_to_cache,
    update_bigquery_release_files,
    update_description_html,
    update_release_description,
)
from warehouse.utils import readme
from warehouse.utils.row_counter import compute_row_counts

from ...common.db.packaging import (
    DependencyFactory,
    DescriptionFactory,
    FileFactory,
    ProjectFactory,
    ReleaseFactory,
    UserFactory,
)


@pytest.mark.parametrize("cached", [True, False])
def test_sync_file_to_cache(db_request, monkeypatch, cached):
    file = FileFactory(cached=cached)
    archive_stub = pretend.stub(
        get_metadata=pretend.call_recorder(lambda path: {"fizz": "buzz"}),
        get=pretend.call_recorder(
            lambda path: pretend.stub(read=lambda: b"my content")
        ),
    )
    cache_stub = pretend.stub(
        store=pretend.call_recorder(lambda filename, path, meta=None: None)
    )
    db_request.find_service = pretend.call_recorder(
        lambda iface, name=None: {"cache": cache_stub, "archive": archive_stub}[name]
    )

    @contextmanager
    def mock_named_temporary_file():
        yield pretend.stub(
            name="/tmp/wutang",
            write=lambda bites: None,
            flush=lambda: None,
        )

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", mock_named_temporary_file)

    sync_file_to_cache(db_request, file.id)

    assert file.cached

    if not cached:
        assert archive_stub.get_metadata.calls == [pretend.call(file.path)]
        assert archive_stub.get.calls == [pretend.call(file.path)]
        assert cache_stub.store.calls == [
            pretend.call(file.path, "/tmp/wutang", meta={"fizz": "buzz"}),
        ]
    else:
        assert archive_stub.get_metadata.calls == []
        assert archive_stub.get.calls == []
        assert cache_stub.store.calls == []


def test_compute_packaging_metrics(db_request, metrics):
    project1 = ProjectFactory()
    project2 = ProjectFactory()
    release1 = ReleaseFactory(project=project1)
    release2 = ReleaseFactory(project=project2)
    release3 = ReleaseFactory(project=project2)
    FileFactory(release=release1)
    FileFactory(release=release2)
    FileFactory(release=release3, packagetype="sdist")
    FileFactory(release=release3, packagetype="bdist_wheel")

    # Make sure that the task to update the database counts has been
    # called.
    compute_row_counts(db_request)

    compute_packaging_metrics(db_request)

    assert metrics.gauge.calls == [
        pretend.call("warehouse.packaging.total_projects", 2),
        pretend.call("warehouse.packaging.total_releases", 3),
        pretend.call("warehouse.packaging.total_files", 4),
    ]


@pytest.mark.parametrize("cached", [True, False])
def test_sync_file_to_cache_includes_bonus_files(db_request, monkeypatch, cached):
    file = FileFactory(
        cached=cached,
        metadata_file_sha256_digest="deadbeefdeadbeefdeadbeefdeadbeef",
    )
    archive_stub = pretend.stub(
        get_metadata=pretend.call_recorder(lambda path: {"fizz": "buzz"}),
        get=pretend.call_recorder(
            lambda path: pretend.stub(read=lambda: b"my content")
        ),
    )
    cache_stub = pretend.stub(
        store=pretend.call_recorder(lambda filename, path, meta=None: None)
    )
    db_request.find_service = pretend.call_recorder(
        lambda iface, name=None: {"cache": cache_stub, "archive": archive_stub}[name]
    )

    @contextmanager
    def mock_named_temporary_file():
        yield pretend.stub(
            name="/tmp/wutang",
            write=lambda bites: None,
            flush=lambda: None,
        )

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", mock_named_temporary_file)

    sync_file_to_cache(db_request, file.id)

    assert file.cached

    if not cached:
        assert archive_stub.get_metadata.calls == [
            pretend.call(file.path),
            pretend.call(file.metadata_path),
        ]
        assert archive_stub.get.calls == [
            pretend.call(file.path),
            pretend.call(file.metadata_path),
        ]
        assert cache_stub.store.calls == [
            pretend.call(file.path, "/tmp/wutang", meta={"fizz": "buzz"}),
            pretend.call(file.metadata_path, "/tmp/wutang", meta={"fizz": "buzz"}),
        ]
    else:
        assert archive_stub.get_metadata.calls == []
        assert archive_stub.get.calls == []
        assert cache_stub.store.calls == []


def test_check_file_cache_tasks_outstanding(db_request, metrics):
    FileFactory.create_batch(12, cached=True)
    FileFactory.create_batch(3, cached=False)

    check_file_cache_tasks_outstanding(db_request)

    assert metrics.gauge.calls == [
        pretend.call("warehouse.packaging.files.not_cached", 3)
    ]


def test_fetch_checksums():
    file_stub = pretend.stub(
        path="/path",
        metadata_path="/path.metadata",
    )
    storage_stub = pretend.stub(
        get_checksum=lambda pth: f"{pth}-deadbeef",
    )

    assert warehouse.packaging.tasks.fetch_checksums(storage_stub, file_stub) == (
        "/path-deadbeef",
        "/path.metadata-deadbeef",
    )


def test_fetch_checksums_none():
    file_stub = pretend.stub(
        path="/path",
        metadata_path="/path.metadata",
    )
    storage_stub = pretend.stub(get_checksum=pretend.raiser(FileNotFoundError))

    assert warehouse.packaging.tasks.fetch_checksums(storage_stub, file_stub) == (
        None,
        None,
    )


def test_reconcile_file_storages_all_good(db_request, metrics):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    all_good = FileFactory.create(release=release, cached=False)
    all_good.md5_digest = f"{all_good.path}-deadbeef"
    all_good.metadata_file_sha256_digest = f"{all_good.path}-feedbeef"

    storage_service = pretend.stub(get_checksum=lambda pth: f"{pth}-deadbeef")
    db_request.find_service = pretend.call_recorder(
        lambda svc, name=None, context=None: {
            "warehouse.packaging.interfaces.IFileStorage-cache": storage_service,
            "warehouse.packaging.interfaces.IFileStorage-archive": storage_service,
            "warehouse.metrics.interfaces.IMetricsService-None": metrics,
        }.get(f"{svc}-{name}")
    )
    db_request.registry.settings = {
        "reconcile_file_storages.batch_size": 3,
    }

    warehouse.packaging.tasks.reconcile_file_storages(db_request)

    assert metrics.increment.calls == []
    assert all_good.cached is True


def test_reconcile_file_storages_fixable(db_request, monkeypatch, metrics):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    fixable = FileFactory.create(release=release, cached=False)
    fixable.md5_digest = f"{fixable.path}-deadbeef"
    fixable.metadata_file_sha256_digest = f"{fixable.path}-feedbeef"

    storage_service = pretend.stub(get_checksum=lambda pth: f"{pth}-deadbeef")
    broke_storage_service = pretend.stub(get_checksum=lambda pth: None)
    db_request.find_service = pretend.call_recorder(
        lambda svc, name=None, context=None: {
            "warehouse.packaging.interfaces.IFileStorage-cache": broke_storage_service,
            "warehouse.packaging.interfaces.IFileStorage-archive": storage_service,
            "warehouse.metrics.interfaces.IMetricsService-None": metrics,
        }.get(f"{svc}-{name}")
    )
    db_request.registry.settings = {
        "reconcile_file_storages.batch_size": 3,
    }

    copy_file = pretend.call_recorder(lambda archive, cache, path: None)
    monkeypatch.setattr(warehouse.packaging.tasks, "_copy_file_to_cache", copy_file)

    warehouse.packaging.tasks.reconcile_file_storages(db_request)

    assert metrics.increment.calls == [
        pretend.call("warehouse.filestorage.reconciled", tags=["type:dist"]),
        pretend.call("warehouse.filestorage.reconciled", tags=["type:metadata"]),
    ]
    assert copy_file.calls == [
        pretend.call(storage_service, broke_storage_service, fixable.path),
        pretend.call(storage_service, broke_storage_service, fixable.metadata_path),
    ]
    assert fixable.cached is True


@pytest.mark.parametrize(
    (
        "borked_ext",
        "metrics_tag",
    ),
    [
        (
            "",
            "type:dist",
        ),
        (
            ".metadata",
            "type:metadata",
        ),
    ],
)
def test_reconcile_file_storages_borked(
    db_request, monkeypatch, metrics, borked_ext, metrics_tag
):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    borked = FileFactory.create(release=release, cached=False)
    borked.md5_digest = f"{borked.path}-deadbeef"
    borked.metadata_file_sha256_digest = f"{borked.path}-feedbeef"

    storage_service = pretend.stub(get_checksum=lambda pth: f"{pth}-deadbeef")
    bad_storage_service = pretend.stub(
        get_checksum=lambda pth: (
            None if pth == borked.path + borked_ext else f"{pth}-deadbeef"
        )
    )
    db_request.find_service = pretend.call_recorder(
        lambda svc, name=None, context=None: {
            "warehouse.packaging.interfaces.IFileStorage-cache": storage_service,
            "warehouse.packaging.interfaces.IFileStorage-archive": bad_storage_service,
            "warehouse.metrics.interfaces.IMetricsService-None": metrics,
        }.get(f"{svc}-{name}")
    )
    db_request.registry.settings = {
        "reconcile_file_storages.batch_size": 3,
    }

    copy_file = pretend.call_recorder(lambda archive, cache, path: None)
    monkeypatch.setattr(warehouse.packaging.tasks, "_copy_file_to_cache", copy_file)

    warehouse.packaging.tasks.reconcile_file_storages(db_request)

    assert copy_file.calls == []
    assert metrics.increment.calls == [
        pretend.call("warehouse.filestorage.unreconciled", tags=[metrics_tag])
    ]
    assert borked.cached is False


@pytest.mark.parametrize(
    (
        "borked_ext",
        "metrics_tag",
    ),
    [
        (
            ".metadata",
            "type:metadata",
        ),
    ],
)
def test_not_all_files(db_request, monkeypatch, metrics, borked_ext, metrics_tag):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    just_dist = FileFactory.create(release=release, cached=False)
    just_dist.md5_digest = f"{just_dist.path}-deadbeef"

    storage_service = pretend.stub(get_checksum=lambda pth: f"{pth}-deadbeef")
    bad_storage_service = pretend.stub(
        get_checksum=lambda pth: (
            None if pth == just_dist.path + borked_ext else f"{pth}-deadbeef"
        )
    )
    db_request.find_service = pretend.call_recorder(
        lambda svc, name=None, context=None: {
            "warehouse.packaging.interfaces.IFileStorage-cache": storage_service,
            "warehouse.packaging.interfaces.IFileStorage-archive": bad_storage_service,
            "warehouse.metrics.interfaces.IMetricsService-None": metrics,
        }.get(f"{svc}-{name}")
    )
    db_request.registry.settings = {
        "reconcile_file_storages.batch_size": 3,
    }

    copy_file = pretend.call_recorder(lambda archive, cache, path: None)
    monkeypatch.setattr(warehouse.packaging.tasks, "_copy_file_to_cache", copy_file)

    warehouse.packaging.tasks.reconcile_file_storages(db_request)

    assert copy_file.calls == []
    assert metrics.increment.calls == []
    assert just_dist.cached is True


def test_update_description_html(monkeypatch, db_request):
    current_version = "24.0"
    previous_version = "23.0"

    monkeypatch.setattr(readme, "renderer_version", lambda: current_version)

    descriptions = [
        DescriptionFactory.create(html="rendered", rendered_by=current_version),
        DescriptionFactory.create(html="not this one", rendered_by=previous_version),
        DescriptionFactory.create(html="", rendered_by=""),  # Initial migration state
    ]

    update_description_html(db_request)

    assert set(
        db_request.db.query(
            Description.raw, Description.html, Description.rendered_by
        ).all()
    ) == {
        (descriptions[0].raw, "rendered", current_version),
        (descriptions[1].raw, readme.render(descriptions[1].raw), current_version),
        (descriptions[2].raw, readme.render(descriptions[2].raw), current_version),
    }


def test_update_release_description(db_request):
    description = DescriptionFactory.create(
        raw="rst\n===\n\nbody text",
        html="",
        rendered_by="0.0",
    )
    release = ReleaseFactory.create(description=description)

    task = pretend.stub()
    update_release_description(task, db_request, release.id)

    updated_description = db_request.db.get(Description, description.id)
    assert updated_description.html == "<p>body text</p>\n"
    assert updated_description.rendered_by == readme.renderer_version()


bq_schema = [
    SchemaField("metadata_version", "STRING", "NULLABLE"),
    SchemaField("name", "STRING", "REQUIRED"),
    SchemaField("version", "STRING", "REQUIRED"),
    SchemaField("summary", "STRING", "NULLABLE"),
    SchemaField("description", "STRING", "NULLABLE"),
    SchemaField("description_content_type", "STRING", "NULLABLE"),
    SchemaField("author", "STRING", "NULLABLE"),
    SchemaField("author_email", "STRING", "NULLABLE"),
    SchemaField("maintainer", "STRING", "NULLABLE"),
    SchemaField("maintainer_email", "STRING", "NULLABLE"),
    SchemaField("license", "STRING", "NULLABLE"),
    SchemaField("license_expression", "STRING", "NULLABLE"),
    SchemaField("license_files", "STRING", "REPEATED"),
    SchemaField("keywords", "STRING", "NULLABLE"),
    SchemaField("classifiers", "STRING", "REPEATED"),
    SchemaField("platform", "STRING", "REPEATED"),
    SchemaField("home_page", "STRING", "NULLABLE"),
    SchemaField("download_url", "STRING", "NULLABLE"),
    SchemaField("requires_python", "STRING", "NULLABLE"),
    SchemaField("requires", "STRING", "REPEATED"),
    SchemaField("provides", "STRING", "REPEATED"),
    SchemaField("obsoletes", "STRING", "REPEATED"),
    SchemaField("requires_dist", "STRING", "REPEATED"),
    SchemaField("provides_dist", "STRING", "REPEATED"),
    SchemaField("obsoletes_dist", "STRING", "REPEATED"),
    SchemaField("requires_external", "STRING", "REPEATED"),
    SchemaField("project_urls", "STRING", "REPEATED"),
    SchemaField("uploaded_via", "STRING", "NULLABLE"),
    SchemaField("upload_time", "TIMESTAMP", "REQUIRED"),
    SchemaField("filename", "STRING", "REQUIRED"),
    SchemaField("size", "INTEGER", "REQUIRED"),
    SchemaField("path", "STRING", "REQUIRED"),
    SchemaField("python_version", "STRING", "REQUIRED"),
    SchemaField("packagetype", "STRING", "REQUIRED"),
    SchemaField("comment_text", "STRING", "NULLABLE"),
    SchemaField("has_signature", "BOOLEAN", "REQUIRED"),
    SchemaField("md5_digest", "STRING", "REQUIRED"),
    SchemaField("sha256_digest", "STRING", "REQUIRED"),
    SchemaField("blake2_256_digest", "STRING", "REQUIRED"),
]


class TestUpdateBigQueryMetadata:
    class ListField(Field):
        def process_formdata(self, valuelist):
            self.data = [v.strip() for v in valuelist if v.strip()]

    input_parameters = [
        (
            {
                "metadata_version": StringField(default="1.2").bind(Form(), "test"),
                "name": StringField(default="OfDABTihRTmE").bind(Form(), "test"),
                "version": StringField(default="1.0").bind(Form(), "test"),
                "summary": StringField(default="").bind(Form(), "test"),
                "description": StringField(default="an example description").bind(
                    Form(), "test"
                ),
                "author": StringField(default="").bind(Form(), "test"),
                "description_content_type": StringField(default="").bind(Form(), "a"),
                "author_email": StringField(default="").bind(Form(), "test"),
                "maintainer": StringField(default="").bind(Form(), "test"),
                "maintainer_email": StringField(default="").bind(Form(), "test"),
                "license": StringField(default="").bind(Form(), "test"),
                "license_expression": StringField(default="").bind(Form(), "test"),
                "license_files": StringField(default=["LICENSE"]).bind(Form(), "test"),
                "keywords": StringField(default="").bind(Form(), "test"),
                "classifiers": ListField(
                    default=["Environment :: Other Environment"]
                ).bind(Form(), "test"),
                "platform": StringField(default="test_platform").bind(Form(), "test"),
                "home_page": StringField(default="").bind(Form(), "test"),
                "download_url": StringField(default="").bind(Form(), "test"),
                "requires_python": StringField(default="").bind(Form(), "test"),
                "pyversion": StringField(default="source").bind(Form(), "test"),
                "filetype": StringField(default="sdist").bind(Form(), "test"),
                "comment": StringField(default="").bind(Form(), "test"),
                "md5_digest": StringField(
                    default="7fcdcb15530ea82d2a5daf98a4997c57"
                ).bind(Form(), "test"),
                "sha256_digest": StringField(
                    default=(
                        "a983cbea389641f78541e25c14ab1a488ede2641119a5be807e"
                        "94645c4f3d25d"
                    )
                ).bind(Form(), "test"),
                "blake2_256_digest": StringField(default="").bind(Form(), "test"),
                "requires": ListField(default=[]).bind(Form(), "test"),
                "provides": ListField(default=[]).bind(Form(), "test"),
                "obsoletes": ListField(default=[]).bind(Form(), "test"),
                "requires_dist": ListField(default=[]).bind(Form(), "test"),
                "provides_dist": ListField(default=[]).bind(Form(), "test"),
                "obsoletes_dist": ListField(default=[]).bind(Form(), "test"),
                "requires_external": ListField(default=[]).bind(Form(), "test"),
                "project_urls": ListField(default=[]).bind(Form(), "test"),
            },
            bq_schema,
        )
    ]

    @pytest.mark.parametrize(
        ("release_files_table", "expected_get_table_calls"),
        [
            (
                "example.pypi.distributions",
                [pretend.call("example.pypi.distributions", timeout=5.0, retry=None)],
            ),
            (
                "example.pypi.distributions some.other.table",
                [
                    pretend.call("example.pypi.distributions", timeout=5.0, retry=None),
                    pretend.call("some.other.table", timeout=5.0, retry=None),
                ],
            ),
        ],
    )
    @pytest.mark.parametrize(("form_factory", "bq_schema"), input_parameters)
    def test_insert_new_row(
        self,
        db_request,
        release_files_table,
        expected_get_table_calls,
        form_factory,
        bq_schema,
    ):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        release_file = FileFactory.create(
            release=release, filename=f"foobar-{release.version}.tar.gz"
        )

        # Process the mocked wtform fields
        for key, value in form_factory.items():
            if isinstance(value, StringField) or isinstance(value, self.ListField):
                value.process(None)

        get_table = pretend.stub(schema=bq_schema)
        bigquery = pretend.stub(
            get_table=pretend.call_recorder(lambda *a, **kw: get_table),
            insert_rows_json=pretend.call_recorder(lambda *a, **kw: []),
        )

        @pretend.call_recorder
        def find_service(name=None):
            if name == "gcloud.bigquery":
                return bigquery
            raise LookupError

        db_request.find_service = find_service
        db_request.registry.settings = {
            "warehouse.release_files_table": release_files_table
        }

        dist_metadata = {
            "metadata_version": form_factory["metadata_version"].data,
            "name": form_factory["name"].data,
            "version": form_factory["version"].data,
            "summary": form_factory["summary"].data,
            "description": form_factory["description"].data,
            "author": form_factory["author"].data,
            "description_content_type": form_factory["description_content_type"].data,
            "author_email": form_factory["author_email"].data,
            "maintainer": form_factory["maintainer"].data,
            "maintainer_email": form_factory["maintainer_email"].data,
            "license": form_factory["license"].data,
            "license_expression": form_factory["license_expression"].data,
            "license_files": form_factory["license_files"].data,
            "keywords": form_factory["keywords"].data,
            "classifiers": form_factory["classifiers"].data,
            "platform": form_factory["platform"].data,
            "home_page": form_factory["home_page"].data,
            "download_url": form_factory["download_url"].data,
            "requires_python": form_factory["requires_python"].data,
            "pyversion": form_factory["pyversion"].data,
            "filetype": form_factory["filetype"].data,
            "comment": form_factory["comment"].data,
            "requires": form_factory["requires"].data,
            "provides": form_factory["provides"].data,
            "obsoletes": form_factory["obsoletes"].data,
            "requires_dist": form_factory["requires_dist"].data,
            "provides_dist": form_factory["provides_dist"].data,
            "obsoletes_dist": form_factory["obsoletes_dist"].data,
            "requires_external": form_factory["requires_external"].data,
            "project_urls": form_factory["project_urls"].data,
            "filename": release_file.filename,
            "python_version": release_file.python_version,
            "packagetype": release_file.packagetype,
            "comment_text": release_file.comment_text,
            "size": release_file.size,
            "has_signature": False,
            "md5_digest": release_file.md5_digest,
            "sha256_digest": release_file.sha256_digest,
            "blake2_256_digest": release_file.blake2_256_digest,
            "path": release_file.path,
            "uploaded_via": release_file.uploaded_via,
            "upload_time": release_file.upload_time,
        }

        task = pretend.stub()
        update_bigquery_release_files(task, db_request, dist_metadata)

        assert db_request.find_service.calls == [pretend.call(name="gcloud.bigquery")]
        assert bigquery.get_table.calls == expected_get_table_calls
        assert bigquery.insert_rows_json.calls == [
            pretend.call(
                table=table,
                json_rows=[
                    {
                        "metadata_version": form_factory["metadata_version"].data,
                        "name": form_factory["name"].data,
                        "version": release_file.release.version,
                        "summary": form_factory["summary"].data or None,
                        "description": form_factory["description"].data or None,
                        "description_content_type": form_factory[
                            "description_content_type"
                        ].data
                        or None,
                        "author": form_factory["author"].data or None,
                        "author_email": form_factory["author_email"].data or None,
                        "maintainer": form_factory["maintainer"].data or None,
                        "maintainer_email": form_factory["maintainer_email"].data
                        or None,
                        "license": form_factory["license"].data or None,
                        "license_expression": form_factory["license_expression"].data
                        or None,
                        "license_files": form_factory["license_files"].data or [],
                        "keywords": form_factory["description_content_type"].data
                        or None,
                        "classifiers": form_factory["classifiers"].data or [],
                        "platform": [form_factory["platform"].data] or [],
                        "home_page": form_factory["home_page"].data or None,
                        "download_url": form_factory["download_url"].data or None,
                        "requires_python": form_factory["requires_python"].data or None,
                        "requires": form_factory["requires"].data or [],
                        "provides": form_factory["provides"].data or [],
                        "obsoletes": form_factory["obsoletes"].data or [],
                        "requires_dist": form_factory["requires_dist"].data or [],
                        "provides_dist": form_factory["provides_dist"].data or [],
                        "obsoletes_dist": form_factory["obsoletes_dist"].data or [],
                        "requires_external": form_factory["requires_external"].data
                        or [],
                        "project_urls": form_factory["project_urls"].data or [],
                        "uploaded_via": release_file.uploaded_via,
                        "upload_time": release_file.upload_time.isoformat(),
                        "filename": release_file.filename,
                        "size": release_file.size,
                        "path": release_file.path,
                        "python_version": release_file.python_version,
                        "packagetype": release_file.packagetype,
                        "comment_text": release_file.comment_text or None,
                        "has_signature": False,
                        "md5_digest": release_file.md5_digest,
                        "sha256_digest": release_file.sha256_digest,
                        "blake2_256_digest": release_file.blake2_256_digest,
                    },
                ],
                timeout=5.0,
                retry=None,
            )
            for table in release_files_table.split()
        ]

    def test_var_is_none(self):
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.release_files_table": None})
        )
        task = pretend.stub()
        dist_metadata = pretend.stub()
        update_bigquery_release_files(task, request, dist_metadata)


def test_compute_2fa_metrics(db_request, monkeypatch):
    # A user without 2FA enabled
    UserFactory.create(totp_secret=None, webauthn=[])

    # A user with TOTP enabled
    UserFactory.create(totp_secret=b"foo", webauthn=[])

    # A user with two WebAuthn methods enabled
    some_user = UserFactory.create(totp_secret=None)
    webauthn = WebAuthn(
        user_id=some_user.id,
        label="wu",
        credential_id="wu",
        public_key="wu",
    )
    webauthn2 = WebAuthn(
        user_id=some_user.id,
        label="tang",
        credential_id="tang",
        public_key="tang",
    )
    db_request.db.add(webauthn)
    db_request.db.add(webauthn2)
    some_user.webauthn = [webauthn, webauthn2]

    gauge = pretend.call_recorder(lambda metric, value: None)
    db_request.find_service = lambda *a, **kw: pretend.stub(gauge=gauge)

    compute_2fa_metrics(db_request)

    assert gauge.calls == [
        pretend.call("warehouse.2fa.total_users_with_totp_enabled", 1),
        pretend.call("warehouse.2fa.total_users_with_webauthn_enabled", 1),
        pretend.call("warehouse.2fa.total_users_with_two_factor_enabled", 2),
    ]


@pytest.mark.parametrize(
    ("project_name", "specifier_string"),
    [
        (
            "requests",
            'requests [security,tests] >= 2.8.1, == 2.8.* ; python_version < "2.7"',
        ),
        ("xml.parsers.expat", "xml.parsers.expat (>1.0)"),
        ("zope.event", "zope.event (==4.5.0)"),
    ],
)
def test_compute_top_dependents_corpus(db_request, project_name, specifier_string):
    # A base project, others depend on it
    base_proj = ProjectFactory.create(name=project_name)
    # A project with no recent dependents
    leaf_proj = ProjectFactory.create()

    # A Project with multiple Releases, the most recent of which is yanked
    project_a = ProjectFactory.create()
    release_a1 = ReleaseFactory.create(project=project_a, version="1.0")
    release_a2 = ReleaseFactory.create(project=project_a, version="2.0", yanked=True)
    # Add dependency relationships
    DependencyFactory.create(
        release=release_a1, kind=DependencyKind.requires_dist, specifier=base_proj.name
    )
    DependencyFactory.create(
        release=release_a2, kind=DependencyKind.requires_dist, specifier=base_proj.name
    )

    # A project with an older release depending on leaf_proj, now base_proj instead
    project_b = ProjectFactory.create()
    release_b1 = ReleaseFactory.create(project=project_b, version="1.0")
    release_b2 = ReleaseFactory.create(project=project_b, version="2.0")
    DependencyFactory.create(
        release=release_b1, kind=DependencyKind.requires_dist, specifier=leaf_proj.name
    )
    DependencyFactory.create(
        release=release_b2, kind=DependencyKind.requires_dist, specifier=base_proj.name
    )

    # legacy `project_url` kind, should not be included in corpus
    legacy_proj = ProjectFactory.create()
    legacy_release = ReleaseFactory.create(project=legacy_proj, version="1.0")
    DependencyFactory.create(
        release=legacy_release, kind=8, specifier="https://example.com"
    )

    results = compute_top_dependents_corpus(db_request)

    assert results == {base_proj.normalized_name: 2}
