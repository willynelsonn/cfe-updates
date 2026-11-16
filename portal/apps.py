from django.apps import AppConfig


class PortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "portal"
    verbose_name = "Portal do cliente"

    def ready(self):
        from . import avisos  # noqa: F401  (liga os sinais dos avisos por e-mail)
