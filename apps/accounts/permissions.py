from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsBackOffice(BasePermission):
    """Admin, décanat, scolarité."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_back_office)


class IsDeanStaff(BasePermission):
    """Admin général et décanat."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_dean_staff)


class IsTeacherOrBackOffice(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_back_office or u.role == "ENSEIGNANT"))


class ReadOnlyOrBackOffice(BasePermission):
    """Lecture pour tout utilisateur connecté, écriture pour le back-office."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return request.method in SAFE_METHODS or u.is_back_office
