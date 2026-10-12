from django.urls import path

from .views import (
    ProjectDetailView, ProjectListCreateView, TaskDetailView, TaskListCreateView,
)


app_name = 'tasks'

urlpatterns = [
    path('projects/', ProjectListCreateView.as_view(), name='project-list'),
    path('projects/<int:pk>/', ProjectDetailView.as_view(), name='project-detail'),
    path('tasks/', TaskListCreateView.as_view(), name='task-list'),
    path('tasks/<int:pk>/', TaskDetailView.as_view(), name='task-detail'),
]
