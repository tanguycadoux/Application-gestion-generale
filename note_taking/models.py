from django.db import models

from core.models import Project, Section, Tag
from images.models import Image

from .signals import NoteFollowUp


class Note(models.Model):
    date = models.DateField(unique=True)
    body = models.TextField(blank=True, default="")

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # Suites proposées par les autres apps au dernier recalcul des passages
    # (#239) : tâches créées, par exemple.
    follow_ups: tuple[NoteFollowUp, ...] = ()
    # Avertissements de l'analyse au dernier recalcul : texte sans projet (#385),
    # titres qui sautent un niveau ou sans projet (#305).
    warnings: tuple[str, ...] = ()

    def __str__(self):
        return f"{self.date}"

    @property
    def projects(self):
        """Projets des passages de la note, par nom ; le texte sans projet n'en a pas.

        Sans requête si les passages ont été préchargés avec leur projet (#188).
        """
        if "passages" in getattr(self, "_prefetched_objects_cache", {}):
            unique = {
                passage.project_id: passage.project
                for passage in self.passages.all()
                if passage.project_id is not None
            }
            return sorted(unique.values(), key=lambda project: project.name)
        return Project.objects.filter(passages__note=self).distinct()

    @property
    def images(self):
        """Images utilisées par les passages de la note."""
        return Image.objects.filter(passages__note=self).distinct()


class Passage(models.Model):
    """Une section d'une note telle qu'écrite (#387) : le texte entre un titre et le
    suivant, ou depuis le début de la note, à sa place.

    C'est un **index dérivé** de `Note.body`, recalculé à chaque enregistrement
    (`services.process_passages`) et par `reprocess_notes` : la recherche, les
    compteurs et les tâches issues des notes s'en servent ; la page de la note
    affiche le texte lui-même.
    """

    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name="passages")
    # Rang dans la note, à partir de 0 : l'ordre où les passages sont écrits.
    position = models.PositiveIntegerField(default=0)
    # Lignes de `Note.body`, à partir de 1 : du titre du passage (ou de la première
    # ligne de la note) à la ligne qui précède le passage suivant.
    start_line = models.PositiveIntegerField(default=1)
    end_line = models.PositiveIntegerField(default=1)
    # Sans projet : le texte avant le premier `#` (#385).
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="passages",
    )
    section = models.ForeignKey(
        Section,
        verbose_name="chemin",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="passages",
    )
    tags = models.ManyToManyField(Tag, related_name="passages", blank=True)
    # Images référencées dans le contenu (image:<pk>), recalculées à l'analyse.
    images = models.ManyToManyField(
        Image, through="PassageImageLink", related_name="passages", blank=True
    )
    content = models.TextField(blank=True, default="")
    # Titres de la section, du projet au plus profond, séparés par « › » : les
    # tâches issues des notes s'y repèrent (#240).
    heading_path = models.TextField(blank=True, default="")
    # Identifiant du titre du passage dans la page de la note (`add_heading_ids`,
    # titres répétés numérotés `-1`, `-2`…) ; vide sans titre.
    heading_id = models.CharField(max_length=255, blank=True, default="")
    # Identifiants de chacun des titres de `heading_path`, séparés par des espaces.
    anchor_path = models.TextField(blank=True, default="")

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        string_repr = str(self.project) if self.project else "Sans projet"
        if self.section:
            string_repr = f"{string_repr}, {self.section}"
        return string_repr

    def rendered_content(self):
        # Import local : rendering importe les modèles.
        from .rendering import render_passage

        return render_passage(self.content)


class PassageImageLink(models.Model):
    """Utilisation d'une image par un passage.

    Le lien vers l'image est protégé : une image utilisée ne peut pas être
    supprimée.
    """

    passage = models.ForeignKey(
        Passage, on_delete=models.CASCADE, related_name="image_links"
    )
    image = models.ForeignKey(
        Image, on_delete=models.PROTECT, related_name="passage_links"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["passage", "image"], name="unique_passage_image"
            )
        ]

    def __str__(self):
        return f"{self.passage} → {self.image}"


class SavedSearch(models.Model):
    """Une requête de recherche gardée sous un nom (#203).

    On garde le texte de la zone de recherche (`q`), tel qu'écrit, et les cases
    cochées de l'arbre « Projets et chemins » (#380). Un projet ou un niveau supprimé
    quitte la recherche, sans laisser d'adresse invalide.
    """

    name = models.CharField("nom", max_length=100, unique=True)
    q = models.TextField("requête", blank=True)
    projects = models.ManyToManyField(
        "core.Project", verbose_name="projets cochés", blank=True, related_name="+"
    )
    sections = models.ManyToManyField(
        "core.Section", verbose_name="niveaux cochés", blank=True, related_name="+"
    )
    # La case « Sans projet » de l'arbre (#385).
    no_project = models.BooleanField("sans projet coché", default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "recherche enregistrée"
        verbose_name_plural = "recherches enregistrées"

    def __str__(self):
        return self.name
