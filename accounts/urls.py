from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView

from .views import RegistrationView, SafeTokenRefreshView


app_name = 'accounts'

urlpatterns = [
    path('register/', RegistrationView.as_view(), name='register'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', SafeTokenRefreshView.as_view(), name='token_refresh'),
]
