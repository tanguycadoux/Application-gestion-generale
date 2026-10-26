from django.conf import settings
from django.core.management.base import BaseCommand

from core.html_validator import install


class Command(BaseCommand):
    help = (
        "Télécharge le validateur HTML du W3C (Nu Html Checker, vnu.jar) dans .vnu/, "
        "pour valider les pages en local. Demande Java pour s'exécuter."
    )

    def handle(self, *args, **options):
        path = install()
        self.stdout.write(
            self.style.SUCCESS(f"Validateur {settings.VNU_VERSION} installé : {path}")
        )
