from rest_framework import serializers

from .models import Project, Task


class TaskFilterSerializer(serializers.Serializer):
    project = serializers.IntegerField(required=False, min_value=1, max_value=9223372036854775807)
    status = serializers.ChoiceField(required=False, choices=Task.Status.choices)
    priority = serializers.ChoiceField(required=False, choices=Task.Priority.choices)


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class TaskSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.none(), pk_field=serializers.IntegerField()
    )

    class Meta:
        model = Task
        fields = ['id', 'project', 'title', 'description', 'status', 'priority',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request is not None and request.user.is_authenticated:
            self.fields['project'].queryset = Project.objects.filter(owner=request.user)
