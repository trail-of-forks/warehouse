# SPDX-License-Identifier: Apache-2.0

from warehouse.btlog.interfaces import IBinaryTransparencyLogService


def includeme(config):
    btlog_class = config.maybe_dotted(
        config.registry.settings.get(
            "btlog.backend",
            "warehouse.btlog.services.BinaryTransparencyLogService",
        )
    )
    config.register_service_factory(
        btlog_class.create_service,
        IBinaryTransparencyLogService,
    )
