"""
Contrôle d'accès par rôle.

**Doctrine de partage entre secrétariat et direction.** L'ITEAG compte quatre
personnes hors enseignants. La maîtrise d'ouvrage a tranché : le secrétariat
*est* le back-office et tient l'ensemble des écrans de gestion. Une séparation
plus fine y produisait surtout des impasses — quelqu'un devait interrompre la
direction pour un acte courant.

* `StaffRoleRequiredMixin` — **toute la gestion** : dossiers, étudiants,
  professeurs, cours, sessions, inscriptions, encaissements, tarifs, stages,
  VAE, comptes utilisateurs, suppressions, bibliothèque, boutique.
* `AdminRoleRequiredMixin` — **le pilotage** : les tableaux de bord et
  indicateurs de direction, ainsi que l'administration Django avancée.

Deux garde-fous subsistent, portés par les formulaires et non par les rôles :
le secrétariat ne peut ni attribuer le rôle « admin », ni modifier ou
supprimer un compte de direction. Sans cela, un rôle pourrait s'élever
lui-même et la distinction ci-dessus ne vaudrait plus rien.
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


class StaffOrTeacherRoleRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("admin", "secretariat", "enseignant")
