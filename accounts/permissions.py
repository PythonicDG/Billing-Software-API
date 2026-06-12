from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOwner(BasePermission):
    """
    Allows access only to users with the 'OWNER' role.
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'OWNER'
        )


class IsStaff(BasePermission):
    """
    Allows access to users with 'STAFF' or 'OWNER' roles.
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['OWNER', 'STAFF']
        )


class IsOwnerOrReadOnly(BasePermission):
    """
    Allows write access only to owners, but read access to any authenticated user.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'OWNER'
        )
