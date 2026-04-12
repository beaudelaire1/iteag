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