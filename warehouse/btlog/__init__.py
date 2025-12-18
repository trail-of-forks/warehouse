# SPDX-License-Identifier: Apache-2.0

from warehouse.btlog.interfaces import IBinaryTransparencyLogService
from warehouse.btlog.services import BinaryTransparencyLogService


def includeme(config):
    # btlog is optional - only register if endpoint is configured
    if config.registry.settings.get("btlog.endpoint"):
        config.register_service_factory(
            BinaryTransparencyLogService.create_service,
            IBinaryTransparencyLogService,
        )
