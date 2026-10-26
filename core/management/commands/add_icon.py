from django.core.management.base import BaseCommand, CommandError

from core.icons import UnknownIconError, download_icon


class Command(BaseCommand):
    help = (
        "Télécharge des icônes Material Symbols (Rounded, 24 px) dans static/icons/, "
        "pour la balise {% icon %}. Les noms sont ceux de https://fonts.google.com/icons."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "names", nargs="+", help="noms des icônes, par exemple delete edit"
        )

    def handle(self, *args, **options):
        for name in options["names"]:
            try:
                path = download_icon(name)
            except UnknownIconError as error:
                raise CommandError(str(error)) from error
            self.stdout.write(self.style.SUCCESS(f"Icône ajoutée : {path.name}"))
