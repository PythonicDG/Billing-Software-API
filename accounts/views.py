from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token

from .models import User
from .serializers import LoginSerializer, ChangePasswordSerializer


class LoginView(APIView):
    """
    POST /api/login/
    Accepts username & password, returns a DRF auth token + basic user info.
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
