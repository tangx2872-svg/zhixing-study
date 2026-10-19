from django.contrib import admin
from assignments.models import Assignment, SubmitAssignment

# Register your models here.
@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return ('course', 'submission_mode', 'required_materials', 'rubric') if obj and obj.question.exists() else ()
@admin.register(SubmitAssignment)
class SubmissionAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
