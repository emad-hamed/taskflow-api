from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .models import Project, Task


User = get_user_model()


class ProjectTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='project_member')
        self.other_user = User.objects.create_user(username='other_project_member')
        self.project = Project.objects.create(owner=self.user, name='My project')
        self.other_project = Project.objects.create(owner=self.other_user, name='Other project')
        self.list_url = reverse('tasks:project-list')
        self.detail_url = reverse('tasks:project-detail', args=[self.project.pk])
        self.other_url = reverse('tasks:project-detail', args=[self.other_project.pk])
        token = AccessToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.public_fields = {'id', 'name', 'description', 'created_at', 'updated_at'}

    def test_unauthenticated_requests_are_rejected(self):
        self.client.credentials()
        requests = [
            ('get', self.list_url), ('post', self.list_url),
            ('get', self.detail_url), ('patch', self.detail_url),
            ('delete', self.detail_url),
        ]
        for method, url in requests:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, format='json')
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Project.objects.count(), 2)

    def test_create_assigns_current_user_and_ignores_client_owner(self):
        self.assertEqual(self.list_url, '/api/projects/')
        response = self.client.post(self.list_url, {
            'name': 'New project', 'description': 'A description',
            'owner': self.other_user.pk, 'owner_id': self.other_user.pk,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(pk=response.data['id'])
        self.assertEqual(project.owner, self.user)
        self.assertEqual(project.name, 'New project')
        self.assertEqual(project.description, 'A description')
        self.assertEqual(set(response.data), self.public_fields)

    def test_list_contains_only_owned_projects(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [self.project.pk])
        self.assertEqual(set(response.data[0]), self.public_fields)

    def test_retrieve_own_project(self):
        self.assertEqual(self.detail_url, f'/api/projects/{self.project.pk}/')
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.project.pk)
        self.assertEqual(set(response.data), self.public_fields)

    def test_other_users_project_returns_404_for_get_patch_and_delete(self):
        original = Project.objects.filter(pk=self.other_project.pk).values().get()
        for method in ['get', 'patch', 'delete']:
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    self.other_url, {'name': 'Unauthorized change'}, format='json'
                )
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(
                    Project.objects.filter(pk=self.other_project.pk).values().get(), original
                )

    def test_patch_own_project(self):
        response = self.client.patch(
            self.detail_url, {'name': 'Updated', 'description': 'Updated description'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, 'Updated')
        self.assertEqual(self.project.description, 'Updated description')
        self.assertEqual(set(response.data), self.public_fields)

    def test_patch_subset_and_blank_description(self):
        response = self.client.patch(self.detail_url, {'description': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.description, '')
        self.assertEqual(self.project.name, 'My project')

    def test_owner_and_read_only_fields_cannot_be_changed(self):
        original_id = self.project.pk
        original_created_at = self.project.created_at
        response = self.client.patch(self.detail_url, {
            'owner': self.other_user.pk, 'owner_id': self.other_user.pk,
            'id': self.other_project.pk,
            'created_at': '2000-01-01T00:00:00Z',
            'updated_at': '2000-01-01T00:00:00Z',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.owner, self.user)
        self.assertEqual(self.project.pk, original_id)
        self.assertEqual(self.project.created_at, original_created_at)
        self.assertNotEqual(self.project.updated_at.year, 2000)
        self.assertEqual(set(response.data), self.public_fields)

    def test_delete_own_project(self):
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.other_project.pk).exists())

    def test_create_requires_nonblank_name(self):
        for data in [{}, {'name': ''}, {'name': '   '}, {'name': 'x' * 201}]:
            with self.subTest(data=data):
                response = self.client.post(self.list_url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('name', response.data)
        self.assertEqual(Project.objects.count(), 2)

    def test_patch_rejects_blank_name(self):
        response = self.client.patch(self.detail_url, {'name': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, 'My project')

    def test_description_is_optional_and_may_be_blank(self):
        for data in [{'name': 'Without description'}, {'name': 'Blank', 'description': ''}]:
            with self.subTest(data=data):
                response = self.client.post(self.list_url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                self.assertEqual(response.data['description'], '')

    def test_duplicate_names_are_allowed(self):
        response = self.client.post(self.list_url, {'name': self.project.name}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Project.objects.filter(owner=self.user, name=self.project.name).count(), 2)

    def test_unsupported_methods(self):
        for method, url in [
            ('post', self.detail_url), ('put', self.detail_url), ('put', self.list_url),
        ]:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, {'name': 'Test'}, format='json')
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Project.objects.count(), 2)


class TaskFilterTests(APITestCase):
    def setUp(self):
        user = User.objects.create_user(username='filter_member')
        other_user = User.objects.create_user(username='filter_other')
        self.project = Project.objects.create(owner=user, name='First')
        self.second_project = Project.objects.create(owner=user, name='Second')
        self.other_project = Project.objects.create(owner=other_user, name='Private')
        self.todo = Task.objects.create(project=self.project, title='Build Backend API', priority='high')
        self.done = Task.objects.create(project=self.second_project, title='Review backend', status='done')
        self.progress = Task.objects.create(project=self.project, title='Write docs', status='in_progress', priority='low')
        Task.objects.create(project=self.other_project, title='Build Backend API', priority='high')
        self.url = reverse('tasks:task-list')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(user)}')

    def test_individual_filters(self):
        cases = [
            ({'project': self.project.pk}, [self.todo.pk, self.progress.pk]),
            ({'status': 'done'}, [self.done.pk]),
            ({'status': 'in_progress'}, [self.progress.pk]),
            ({'priority': 'high'}, [self.todo.pk]),
            ({'priority': 'low'}, [self.progress.pk]),
            ({'priority': 'medium'}, [self.done.pk]),
        ]
        for params, expected in cases:
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([task['id'] for task in response.data], expected)

    def test_title_search_is_case_insensitive_and_scoped(self):
        response = self.client.get(self.url, {'search': 'BACKEND'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([task['id'] for task in response.data], [self.todo.pk, self.done.pk])

    def test_search_only_matches_title(self):
        self.progress.description = 'backend'
        self.progress.save()
        response = self.client.get(self.url, {'search': 'backend'})
        self.assertNotIn(self.progress.pk, [task['id'] for task in response.data])

    def test_combined_filters_and_search(self):
        response = self.client.get(self.url, {
            'project': self.project.pk, 'status': 'todo', 'priority': 'high', 'search': 'backend API',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual([task['id'] for task in response.data], [self.todo.pk])

    def test_inaccessible_missing_and_nonmatching_filters_return_empty_list(self):
        for params in [
            {'project': self.other_project.pk}, {'project': 999999},
            {'status': 'done', 'priority': 'high'}, {'search': 'no matching title'},
        ]:
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, [])

    def test_invalid_filter_values_return_field_errors(self):
        for field, values in {
            'project': ['', 'abc', '1.5', '0', '-1', '9223372036854775808'],
            'status': ['', 'DONE', 'invalid'],
            'priority': ['', 'HIGH', 'invalid'],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.client.get(self.url, {field: value})
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.data)

    def test_empty_search_and_unknown_parameters_are_ignored(self):
        response = self.client.get(self.url, {'search': '', 'owner': self.other_project.owner_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([task['id'] for task in response.data], [self.todo.pk, self.done.pk, self.progress.pk])

    def test_filters_require_authentication(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url, {'priority': 'high'}).status_code, 401)


class TaskTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='task_member')
        self.other_user = User.objects.create_user(username='other_task_member')
        self.project = Project.objects.create(owner=self.user, name='First')
        self.second_project = Project.objects.create(owner=self.user, name='Second')
        self.other_project = Project.objects.create(owner=self.other_user, name='Other')
        self.task = Task.objects.create(project=self.project, title='My task')
        self.other_task = Task.objects.create(project=self.other_project, title='Other task')
        self.list_url = reverse('tasks:task-list')
        self.detail_url = reverse('tasks:task-detail', args=[self.task.pk])
        self.other_url = reverse('tasks:task-detail', args=[self.other_task.pk])
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}')
        self.public_fields = {
            'id', 'project', 'title', 'description', 'status', 'priority',
            'created_at', 'updated_at',
        }

    def test_unauthenticated_requests_are_rejected(self):
        self.client.credentials()
        for method, url in [
            ('get', self.list_url), ('post', self.list_url), ('get', self.detail_url),
            ('patch', self.detail_url), ('delete', self.detail_url),
        ]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, format='json')
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Task.objects.count(), 2)

    def test_create_in_own_project_with_defaults(self):
        self.assertEqual(self.list_url, '/api/tasks/')
        response = self.client.post(self.list_url, {
            'project': self.project.pk, 'title': 'New task',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        task = Task.objects.get(pk=response.data['id'])
        self.assertEqual(task.project, self.project)
        self.assertEqual(task.project.owner, self.user)
        self.assertEqual(task.status, 'todo')
        self.assertEqual(task.priority, 'medium')
        self.assertEqual(task.description, '')
        self.assertEqual(set(response.data), self.public_fields)
        self.assertEqual(response.data['status'], 'todo')
        self.assertEqual(response.data['priority'], 'medium')

    def test_unavailable_project_assignment_is_rejected_on_create_and_patch(self):
        missing_id = self.other_project.pk + 1000
        for method, url in [('post', self.list_url), ('patch', self.detail_url)]:
            errors = []
            for project_id in [self.other_project.pk, missing_id]:
                with self.subTest(method=method, project_id=project_id):
                    response = getattr(self.client, method)(url, {
                        'project': project_id, 'title': 'Forbidden change',
                    }, format='json')
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn('project', response.data)
                    errors.append(response.data['project'][0].code)
            self.assertEqual(errors, ['does_not_exist', 'does_not_exist'])
        self.task.refresh_from_db()
        self.assertEqual(self.task.project, self.project)
        self.assertEqual(self.task.title, 'My task')
        self.assertEqual(Task.objects.count(), 2)

    def test_missing_and_invalid_project_are_rejected(self):
        for data in [
            {}, {'project': None}, {'project': 'invalid'}, {'project': True},
            {'project': self.project.pk + 0.5}, {'project': []}, {'project': {}},
            {'project': 9223372036854775808},
        ]:
            with self.subTest(data=data):
                response = self.client.post(
                    self.list_url, {'title': 'Test', **data}, format='json'
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('project', response.data)
        response = self.client.patch(
            self.detail_url, {'project': self.project.pk + 0.5}, format='json'
        )
        self.assertEqual(response.status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.project, self.project)

    def test_list_only_contains_tasks_from_owned_projects(self):
        second_task = Task.objects.create(project=self.second_project, title='Second task')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({item['id'] for item in response.data}, {self.task.pk, second_task.pk})
        for item in response.data:
            self.assertEqual(set(item), self.public_fields)

    def test_retrieve_own_task(self):
        self.assertEqual(self.detail_url, f'/api/tasks/{self.task.pk}/')
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.task.pk)
        self.assertEqual(response.data['project'], self.project.pk)
        self.assertEqual(set(response.data), self.public_fields)

    def test_other_users_task_returns_404(self):
        original = Task.objects.filter(pk=self.other_task.pk).values().get()
        for method in ['get', 'patch', 'delete']:
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.other_url, {
                    'title': 'Forbidden', 'project': self.project.pk,
                }, format='json')
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(Task.objects.filter(pk=self.other_task.pk).values().get(), original)

    def test_patch_editable_fields(self):
        data = {'title': 'Updated', 'description': 'Details', 'status': 'in_progress', 'priority': 'high'}
        response = self.client.patch(self.detail_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        for field, value in data.items():
            self.assertEqual(getattr(self.task, field), value)
        self.assertEqual(set(response.data), self.public_fields)
        response = self.client.patch(self.detail_url, {'status': 'done', 'priority': 'low'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_move_between_owned_projects(self):
        response = self.client.patch(
            self.detail_url, {'project': self.second_project.pk}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertEqual(self.task.project, self.second_project)
        self.assertEqual(self.task.title, 'My task')

    def test_invalid_choices_are_rejected(self):
        for field in ['status', 'priority']:
            for method, url in [('post', self.list_url), ('patch', self.detail_url)]:
                with self.subTest(field=field, method=method):
                    response = getattr(self.client, method)(url, {
                        'project': self.project.pk, 'title': 'Test', field: 'invalid',
                    }, format='json')
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn(field, response.data)

    def test_title_validation(self):
        for data in [{}, {'title': ''}, {'title': '   '}, {'title': 'x' * 201}]:
            with self.subTest(data=data):
                response = self.client.post(
                    self.list_url, {'project': self.project.pk, **data}, format='json'
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('title', response.data)
        response = self.client.patch(self.detail_url, {'title': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_blank_description_and_duplicate_titles_are_allowed(self):
        response = self.client.post(self.list_url, {
            'project': self.project.pk, 'title': self.task.title, 'description': '',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['description'], '')
        self.assertEqual(Task.objects.filter(project=self.project, title=self.task.title).count(), 2)

    def test_read_only_fields_are_ignored(self):
        original_id = self.task.pk
        original_created_at = self.task.created_at
        response = self.client.patch(self.detail_url, {
            'id': self.other_task.pk, 'created_at': '2000-01-01T00:00:00Z',
            'updated_at': '2000-01-01T00:00:00Z',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertEqual(self.task.pk, original_id)
        self.assertEqual(self.task.created_at, original_created_at)
        self.assertNotEqual(self.task.updated_at.year, 2000)

    def test_delete_own_task(self):
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertTrue(Task.objects.filter(pk=self.other_task.pk).exists())

    def test_project_deletion_cascades_to_tasks(self):
        Task.objects.create(project=self.project, title='Another task')
        response = self.client.delete(reverse('tasks:project-detail', args=[self.project.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.filter(project_id=self.project.pk).exists())
        self.assertTrue(Task.objects.filter(pk=self.other_task.pk).exists())

    def test_unsupported_methods(self):
        for method, url in [
            ('put', self.list_url), ('put', self.detail_url), ('post', self.detail_url),
        ]:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, {}, format='json')
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
