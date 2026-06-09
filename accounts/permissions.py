from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """
    Allows access only to authenticated users.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsStaff(BasePermission):
    """
    Allows access only to authenticated users.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsOwnerOrReadOnly(BasePermission):
    """
    Allows access to all authenticated users for any HTTP method.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
