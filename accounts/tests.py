from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase
from rest_framework.settings import api_settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


User = get_user_model()


class RegistrationTests(APITestCase):
    def setUp(self):
        self.url = reverse('accounts:register')
        self.data = {
            'username': 'newmember',
            'email': 'member@example.com',
            'password': 'Cedar!River82Sky',
            'password_confirm': 'Cedar!River82Sky',
        }

    def test_successful_registration(self):
        self.assertEqual(self.url, '/api/auth/register/')
        response = self.client.post(self.url, self.data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        user = User.objects.get(username=self.data['username'])
        self.assertEqual(user.email, self.data['email'])
        self.assertNotEqual(user.password, self.data['password'])
        self.assertTrue(user.check_password(self.data['password']))
        self.assertNotIn('password', response.data)
        self.assertNotIn('password_confirm', response.data)
        self.assertEqual(response.data, {
            'id': user.pk,
            'username': user.username,
            'email': user.email,
        })

    def test_duplicate_username_is_rejected(self):
        User.objects.create_user(username=self.data['username'], email='other@example.com')

        response = self.client.post(self.url, self.data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        User.objects.create_user(username='existing', email=self.data['email'])

        for email in ['member@example.com', 'MEMBER@EXAMPLE.COM']:
            with self.subTest(email=email):
                data = {**self.data, 'email': email}
                response = self.client.post(self.url, data, format='json')

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('email', response.data)
                self.assertEqual(User.objects.count(), 1)

    def test_invalid_email_is_rejected(self):
        self.data['email'] = 'invalid-email'
        response = self.client.post(self.url, self.data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.assertFalse(User.objects.exists())

    def test_email_cannot_exceed_model_length(self):
        email = 'a' * 64 + '@' + '.'.join(['b' * 63] * 3) + '.com'
        self.assertGreater(len(email), 254)
        response = self.client.post(self.url, {**self.data, 'email': email}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)

    def test_mismatched_passwords_are_rejected(self):
        self.data['password_confirm'] = 'Different!Password82'
        response = self.client.post(self.url, self.data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirm', response.data)
        self.assertFalse(User.objects.exists())

    def test_invalid_passwords_are_rejected(self):
        for password in ['Ab!2', 'password', '729483610582', 'newmember']:
            with self.subTest(password=password):
                data = {**self.data, 'password': password, 'password_confirm': password}
                response = self.client.post(self.url, data, format='json')

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('password', response.data)
                self.assertFalse(User.objects.exists())

    def test_missing_required_fields_are_rejected(self):
        for field in self.data:
            with self.subTest(field=field):
                data = self.data.copy()
                del data[field]
                response = self.client.post(self.url, data, format='json')

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)
                self.assertFalse(User.objects.exists())

    def test_blank_required_fields_are_rejected(self):
        for field in self.data:
            with self.subTest(field=field):
                data = {**self.data, field: ''}
                response = self.client.post(self.url, data, format='json')

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)
                self.assertFalse(User.objects.exists())

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class JWTAuthenticationTests(APITestCase):
    def setUp(self):
        self.token_url = reverse('accounts:token_obtain_pair')
        self.refresh_url = reverse('accounts:token_refresh')
        self.credentials = {
            'username': 'jwt_test_member',
            'password': 'FakeTest!Cedar82River',
        }
        self.user = User.objects.create_user(**self.credentials)

    def test_valid_credentials_return_token_pair(self):
        self.assertEqual(self.token_url, '/api/auth/token/')
        response = self.client.post(self.token_url, self.credentials, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'access', 'refresh'})
        self.assertTrue(response.data['refresh'])
        access_token = AccessToken(response.data['access'])
        self.assertEqual(str(access_token['user_id']), str(self.user.pk))

        # Verify the configured authentication class accepts the Bearer token.
        self.assertIn(JWTAuthentication, api_settings.DEFAULT_AUTHENTICATION_CLASSES)
        request = APIRequestFactory().get(
            '/', HTTP_AUTHORIZATION=f"Bearer {response.data['access']}"
        )
        authenticated_user, _ = JWTAuthentication().authenticate(request)
        self.assertEqual(authenticated_user, self.user)

    def test_wrong_password_is_rejected(self):
        data = {**self.credentials, 'password': 'WrongFakePassword!'}
        response = self.client.post(self.token_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_username_is_rejected(self):
        data = {**self.credentials, 'username': 'unknown_test_member'}
        response = self.client.post(self.token_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_credentials_are_rejected(self):
        for data in [{}, {'username': self.credentials['username']},
                     {'password': self.credentials['password']}]:
            with self.subTest(fields=list(data)):
                response = self.client.post(self.token_url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_refresh_returns_new_access_token(self):
        self.assertEqual(self.refresh_url, '/api/auth/token/refresh/')
        login_response = self.client.post(
            self.token_url, self.credentials, format='json'
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        response = self.client.post(
            self.refresh_url, {'refresh': login_response.data['refresh']}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'access'})
        self.assertNotEqual(response.data['access'], login_response.data['access'])
        access_token = AccessToken(response.data['access'])
        self.assertEqual(str(access_token['user_id']), str(self.user.pk))

    def test_invalid_refresh_token_is_rejected(self):
        response = self.client.post(
            self.refresh_url, {'refresh': 'invalid-test-token'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_refresh_token_is_rejected(self):
        response = self.client.post(self.refresh_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_is_not_allowed(self):
        for url in [self.token_url, self.refresh_url]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_expired_access_and_refresh_tokens_are_rejected(self):
        access = AccessToken.for_user(self.user)
        refresh = RefreshToken.for_user(self.user)
        for token in [access, refresh]:
            token.set_exp(lifetime=timedelta(seconds=-1))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(self.client.get(reverse('profile')).status_code, 401)
        self.client.credentials()
        response = self.client.post(self.refresh_url, {'refresh': str(refresh)}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_types_are_rejected(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh}')
        self.assertEqual(self.client.get(reverse('profile')).status_code, 401)
        self.client.credentials()
        response = self.client.post(self.refresh_url, {'refresh': str(refresh.access_token)}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_deleted_user_tokens_return_401_instead_of_server_error(self):
        refresh = RefreshToken.for_user(self.user)
        access = refresh.access_token
        self.user.delete()
        response = self.client.post(self.refresh_url, {'refresh': str(refresh)}, format='json')
        self.assertEqual(response.status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(self.client.get(reverse('profile')).status_code, 401)

    def test_inactive_user_cannot_refresh(self):
        refresh = RefreshToken.for_user(self.user)
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self.client.post(self.refresh_url, {'refresh': str(refresh)}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_inactive_user_cannot_login_or_use_existing_access(self):
        access = AccessToken.for_user(self.user)
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self.client.post(self.token_url, self.credentials, format='json')
        self.assertEqual(response.status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(self.client.get(reverse('profile')).status_code, 401)

    def test_malformed_bearer_tokens_fail_on_all_protected_resources(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid-test-token')
        for url in [reverse('profile'), reverse('tasks:project-list'), reverse('tasks:task-list')]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 401)


class ProfileTests(APITestCase):
    def setUp(self):
        self.url = reverse('profile')
        self.user = User.objects.create_user(
            username='profile_member', email='member@example.com',
            password='FakeProfile!Cedar82', first_name='Test', last_name='Member',
        )
        self.other_user = User.objects.create_user(
            username='other_member', email='other@example.com',
            password='FakeOther!River82', first_name='Other', last_name='Member',
        )
        token = AccessToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_get_returns_current_user_profile(self):
        self.assertEqual(self.url, '/api/profile/')
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {
            'id': self.user.pk,
            'username': 'profile_member',
            'email': 'member@example.com',
            'first_name': 'Test',
            'last_name': 'Member',
        })

    def test_unauthenticated_requests_are_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.patch(self.url, {'first_name': 'Changed'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Test')

    def test_patch_updates_editable_fields(self):
        data = {'email': 'updated@example.com', 'first_name': 'New', 'last_name': 'Name'}
        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        for field, value in data.items():
            self.assertEqual(getattr(self.user, field), value)
            self.assertEqual(response.data[field], value)
        self.assertEqual(set(response.data), {'id', 'username', 'email', 'first_name', 'last_name'})

    def test_patch_updates_only_supplied_fields(self):
        response = self.client.patch(self.url, {'first_name': 'Updated'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.last_name, 'Member')
        self.assertEqual(self.user.email, 'member@example.com')

    def test_read_only_and_password_fields_are_ignored(self):
        original_id = self.user.pk
        original_password = self.user.password
        response = self.client.patch(self.url, {
            'id': self.other_user.pk,
            'username': 'changed_username',
            'password': 'FakeReplacement!Password82',
            'password_confirm': 'FakeReplacement!Password82',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.pk, original_id)
        self.assertEqual(self.user.username, 'profile_member')
        self.assertEqual(self.user.password, original_password)
        self.assertTrue(self.user.check_password('FakeProfile!Cedar82'))
        self.assertNotIn('password', response.data)
        self.assertNotIn('password_confirm', response.data)
        self.assertEqual(response.data['id'], original_id)

    def test_another_users_email_is_rejected_case_insensitively(self):
        for email in ['other@example.com', 'OTHER@EXAMPLE.COM']:
            with self.subTest(email=email):
                response = self.client.patch(self.url, {'email': email}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('email', response.data)
                self.user.refresh_from_db()
                self.assertEqual(self.user.email, 'member@example.com')

    def test_current_email_is_allowed(self):
        for email in ['member@example.com', 'MEMBER@EXAMPLE.COM']:
            with self.subTest(email=email):
                response = self.client.patch(self.url, {'email': email}, format='json')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.user.refresh_from_db()
                self.assertEqual(self.user.email, email)

    def test_profile_email_cannot_exceed_model_length(self):
        email = 'a' * 64 + '@' + '.'.join(['b' * 63] * 3) + '.com'
        response = self.client.patch(self.url, {'email': email}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'member@example.com')

    def test_invalid_email_is_rejected(self):
        for email in ['invalid-email', '', None]:
            with self.subTest(email=email):
                response = self.client.patch(self.url, {'email': email}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('email', response.data)
                self.user.refresh_from_db()
                self.assertEqual(self.user.email, 'member@example.com')

    def test_client_cannot_select_another_users_profile(self):
        url = f'{self.url}?id={self.other_user.pk}&user_id={self.other_user.pk}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.user.pk)

        other_before = User.objects.filter(pk=self.other_user.pk).values().get()
        response = self.client.patch(url, {
            'id': self.other_user.pk,
            'user_id': self.other_user.pk,
            'first_name': 'Changed',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.user.pk)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Changed')
        self.assertEqual(User.objects.filter(pk=self.other_user.pk).values().get(), other_before)
        self.assertEqual(
            self.client.get(f'{self.url}{self.other_user.pk}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_unsupported_methods_are_rejected(self):
        for method in ['post', 'put', 'delete']:
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url, {}, format='json')
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(User.objects.count(), 2)
