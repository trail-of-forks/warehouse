# SPDX-License-Identifier: Apache-2.0

# NOTE: warehouse.forklift is a temporary package, and it is assumed that it
#       will go away eventually, once we split forklift out into it's own
#       project.

from rfc3986 import builder


def _help_url(request, **kwargs):
    warehouse_domain = request.registry.settings.get("warehouse.domain")
    return request.route_url("help", _host=warehouse_domain, **kwargs)


def _user_docs_url(request, path, anchor: str | None = None):
    docs_domain = request.registry.settings.get("userdocs.domain")
    return (
        builder.URIBuilder()
        .from_uri(docs_domain)
        .add_path(path)
        .add_fragment(anchor)
        .finalize()
        .unsplit()
    )


def includeme(config):
    # We need to get the value of the Warehouse and Forklift domains, we'll use
    # these to segregate the Warehouse routes from the Forklift routes until
    # Forklift is properly split out into it's own project.
    forklift = config.get_settings().get("forklift.domain")

    # Include our legacy action routing
    config.include(".action_routing")

    # Add the routes that we'll be using in Forklift.
    config.add_legacy_action_route(
        "forklift.legacy.file_upload", "file_upload", domain=forklift
    )
    config.add_legacy_action_route("forklift.legacy.submit", "submit", domain=forklift)
    config.add_legacy_action_route(
        "forklift.legacy.submit_pkg_info", "submit_pkg_info", domain=forklift
    )
    config.add_legacy_action_route(
        "forklift.legacy.doc_upload", "doc_upload", domain=forklift
    )

    config.add_route(
        "forklift.legacy.missing_trailing_slash", "/legacy", domain=forklift
    )

    config.add_request_method(_help_url, name="help_url")
    config.add_request_method(_user_docs_url, name="user_docs_url")

    if forklift:
        config.add_template_view(
            "forklift.index",
            "/",
            "upload.html",
            route_kw={"domain": forklift},
            view_kw={"has_translations": True},
        )

        config.add_template_view(
            "forklift.robots.txt",
            "/robots.txt",
            "forklift.robots.txt",
            route_kw={"domain": forklift},
            view_kw={"has_translations": False},
        )

        # Any call to /legacy/ not handled by another route (e.g. no :action
        # URL parameter, or an invalid :action URL parameter) falls through to
        # this catch-all route.
        config.add_template_view(
            "forklift.legacy.invalid_request",
            "/legacy/",
            "upload.html",
            route_kw={"domain": forklift},
            view_kw={"has_translations": True},
        )
