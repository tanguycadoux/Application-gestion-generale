from django.core.management.base import BaseCommand, CommandError

from core import codemirror


class Command(BaseCommand):
    help = (
        "Télécharge les modules CodeMirror listés dans "
        "static/vendor/codemirror/packages.json, vérifie leur empreinte npm et "
        "les range dans static/vendor/codemirror/. Étape d'installation : "
        "l'application elle-même ne contacte jamais Internet."
    )

    def handle(self, *args, **options):
        packages = []
        for package in codemirror.load_packages():
            try:
                packages.append(codemirror.vendor(package))
            except codemirror.IntegrityError as error:
                raise CommandError(str(error)) from error
            self.stdout.write(f"{package.name} {package.version}")
        codemirror.save_packages(packages)
        (codemirror.VENDOR_DIR / "README.md").write_text(
            codemirror.readme(packages), encoding="utf-8"
        )
        self.stdout.write(self.style.SUCCESS(f"{len(packages)} modules à jour."))
