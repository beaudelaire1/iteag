"""Chargement de l'application Celery au démarrage de Django.

Sans cet import, `shared_task(...).delay()` se rattache à une application Celery
par défaut, non configurée : le processus web publierait vers un courtier
inexistant et les tâches ne partiraient jamais, sans erreur visible.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
