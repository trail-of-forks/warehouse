# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPNotFound
from pyramid.request import Request
from pyramid.view import view_config

from warehouse.cache.http import add_vary, cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import File
from warehouse.utils.cors import _CORS_HEADERS


@view_config(
    route_name="transparency.info",
    context=File,
    require_methods=["GET"],
    renderer="json",
    require_csrf=False,
    has_translations=False,
    decorator=[
        add_vary("Accept"),
        cache_control(10 * 60),  # 10 minutes
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=5 * 60,  # 5 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def transparency_info(file: File, request: Request):
    """Return the transparency log entry for a file."""
    request.response.content_type = "application/json"

    if not file.transparency_log:
        return HTTPNotFound(
            json={"message": f"No transparency log entry for {file.filename}"}
        )

    # Apply CORS headers.
    request.response.headers.update(_CORS_HEADERS)

    return file.transparency_log.log_entry
