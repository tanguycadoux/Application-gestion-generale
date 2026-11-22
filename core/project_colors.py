"""Classes Tailwind des couleurs des projets (#162).

Seul fichier où les familles des projets (core.models.PROJECT_COLORS) sont
admises (core/tests/test_colors.py) ; la pastille `{% project_badge %}` et le
filtre `project_dot_class` de `{% load ui %}` (core/templatetags/ui.py) les emploient.
"""

# Point de couleur de chaque famille de projet (core.models.PROJECT_COLORS),
# écrit en entier pour que Tailwind trouve les classes.
PROJECT_DOT_CLASSES = {
    "orange": "bg-orange-500",
    "yellow": "bg-yellow-500",
    "lime": "bg-lime-500",
    "emerald": "bg-emerald-500",
    "teal": "bg-teal-500",
    "cyan": "bg-cyan-500",
    "sky": "bg-sky-500",
    "indigo": "bg-indigo-500",
    "violet": "bg-violet-500",
    "purple": "bg-purple-500",
    "fuchsia": "bg-fuchsia-500",
    "pink": "bg-pink-500",
    "rose": "bg-rose-500",
}


def project_dot_class(project) -> str:
    """Classe du point de couleur d'un projet, pour un affichage compact."""
    return PROJECT_DOT_CLASSES.get(project.color, "") if project else ""
