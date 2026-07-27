"""
Contrôle d'accès par rôle.

**Doctrine de partage entre secrétariat et direction.** L'ITEAG compte quatre
personnes hors enseignants : le secrétariat *est* le back-office, et le traiter
comme un rôle diminué crée des impasses quotidiennes — quelqu'un doit
interrompre la direction pour un acte courant.

La ligne de partage ne porte donc pas sur l'importance de l'écran mais sur la
nature du pouvoir qu'il confère :

* `StaffRoleRequiredMixin` — **l'opérationnel** : tout ce qui fait tourner
  l'institut au jour le jour. Dossiers, étudiants, professeurs, cours,
  sessions, inscriptions, encaissements, stages, VAE, bibliothèque, boutique.
* `AdminRoleRequiredMixin` — **le régalien**, trois cas et trois seulement :
  ce qui donne des droits (comptes utilisateurs), ce qui engage
  financièrement l'institut (grille tarifaire), et ce qui détruit
  (suppressions). Une erreur y est coûteuse ou irréversible.

Ajouter un écran au régalien se justifie contre ces trois critères ; à défaut,
il relève de l'opérationnel.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = ()
    required_profile_attr = None

    def test_func(self):
        user = self.request.user
        role_ok = user.is_authenticated and (user.role in self.allowed_roles or user.is_superuser)
        if not role_ok:
            return False
        if self.required_profile_attr:
            return hasattr(user, self.required_profile_attr)
        return True


class StudentRoleRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("etudiant",)
    required_profile_attr = "profil_etudiant"


class TeacherRoleRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("enseignant",)


class StaffRoleRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("admin", "secretariat")


class AdminRoleRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("admin",)


class SecretariatRoleRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("secretariat",)
