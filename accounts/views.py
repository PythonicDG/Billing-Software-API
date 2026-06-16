from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token

from .models import User
from .permissions import IsOwner
from .serializers import LoginSerializer, CreateStaffSerializer, StaffListSerializer, ChangePasswordSerializer


class LoginView(APIView):
    """
    POST /api/login/
    Accepts username & password, returns a DRF auth token + basic user info.
    Works for all roles (Owner, Staff, Viewer).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            'success': True,
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
        }, status=status.HTTP_200_OK)


class CreateStaffView(APIView):
    """
    POST /api/staff/create/
    Owner creates a new Staff or Viewer account.
    Body: { username, email, password, role (optional, default STAFF) }
    """
    permission_classes = [IsOwner]

    def post(self, request):
        serializer = CreateStaffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response({
            'success': True,
            'message': f'Account for "{user.username}" created successfully.',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
            }
        }, status=status.HTTP_201_CREATED)


class ListStaffView(APIView):
    """
    GET /api/staff/list/
    Owner can see all non-owner accounts (Staff + Viewer).
    """
    permission_classes = [IsOwner]

    def get(self, request):
        staff_users = User.objects.exclude(role=User.OWNER).order_by('username')
        serializer = StaffListSerializer(staff_users, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)


class DeactivateStaffView(APIView):
    """
    PATCH /api/staff/<id>/deactivate/
    Owner sets is_active = False on a staff account. Does not delete.
    """
    permission_classes = [IsOwner]

    def patch(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'success': False, 'error': 'User not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.role == User.OWNER:
            return Response(
                {'success': False, 'error': 'Cannot deactivate an Owner account.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        user.is_active = False
        user.save(update_fields=['is_active'])

        return Response({
            'success': True,
            'message': f'User "{user.username}" has been deactivated.',
            'user': {
                'id': user.id,
                'username': user.username,
                'is_active': user.is_active,
            }
        }, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """
    POST /api/change-password/
    Current user updates their own password.
    Body: { old_password, new_password }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()

        return Response({
            'success': True,
            'message': 'Password updated successfully.'
        }, status=status.HTTP_200_OK)
