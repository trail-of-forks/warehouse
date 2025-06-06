# SPDX-License-Identifier: Apache-2.0

from .interfaces import ICaptchaService
from .recaptcha import Service


def includeme(config):
    # Register our Captcha service
    captcha_class = config.maybe_dotted(
        config.registry.settings.get("captcha.backend", Service)
    )
    config.register_service_factory(
        captcha_class.create_service,
        ICaptchaService,
        # Service requires a name for lookup in Jinja2 template,
        # where the Interface object is not available.
        name="captcha",
    )
