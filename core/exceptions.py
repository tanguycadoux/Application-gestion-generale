"""Exception de base des erreurs métier de l'application."""


class AppError(Exception):
    """Erreur métier : son message est destiné à l'utilisateur.

    Les vues attrapent ces erreurs et affichent leur message. Toute autre
    exception est un bug et n'est pas attrapée.
    """
