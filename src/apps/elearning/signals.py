"""
Propagation du statut de l'étudiant vers ses accès vidéo.

C'est le seul signal du domaine : il rend la coupure d'accès immédiate quel que
soit l'endroit où la suspension est décidée (administration, import, script).
Le reste des règles vit dans les services, où il se lit et se teste.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="academics.ProfilEtudiant", dispatch_uid="elearning_propager_statut")
def propager_statut_vers_les_acces(sender, instance, created, **kwargs):
    if created:
        return
    from apps.elearning.services.octroi import propager_statut_etudiant

    propager_statut_etudiant(instance)
