from django.contrib import admin
from resources.models import Resource
# Register your models here.
@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    # Research attachments are managed by the append-only version workflow.
    def get_queryset(self, request):
        return super().get_queryset(request).filter(workspace__isnull=True)
