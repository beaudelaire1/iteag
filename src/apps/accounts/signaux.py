"""Les droits éditoriaux suivent le rôle, sans qu'on ait à y penser.

Une migration règle le sort des comptes existants ; sans ce signal, elle ne
vaudrait que pour eux. Le premier secrétariat recruté après la mise en service
aurait vu un bouton d'insertion d'image ouvrant une fenêtre vide — et la cause
aurait été introuvable, puisque tous ses collègues l'auraient eu fonctionnel.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import User
from apps.accounts.services.droits_editoriaux import synchroniser


@receiver(post_save, sender=User, dispatch_uid="accounts.droits_editoriaux")
def accorder_les_droits_editoriaux(sender, instance, **kwargs):
    """Rattache ou détache selon le rôle, à chaque enregistrement.

    À chaque enregistrement et non à la seule création : un compte qui change
    de rôle doit perdre l'accès que l'ancien justifiait.
    """
    synchroniser(instance)
