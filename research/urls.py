from django.urls import path
from . import views

app_name = 'research'
urlpatterns = [
    path('', views.workspace_list, name='list'),
    path('demo/', views.demo_list, name='demo'),
    path('new/', views.workspace_create, name='create'),
    path('<int:pk>/', views.overview, name='overview'),
    path('<int:pk>/edit/', views.workspace_edit, name='edit'),
    path('<int:pk>/members/', views.members, name='members'),
    path('<int:pk>/members/<int:user_id>/', views.member_activity, name='member_activity'),
    path('<int:pk>/activity/', views.activity, name='activity'),
    path('<int:pk>/files/', views.files, name='files'),
    path('<int:pk>/files/upload/', views.file_upload, name='file_upload'),
    path('<int:pk>/files/<int:file_id>/', views.file_detail, name='file_detail'),
    path('<int:pk>/versions/<int:version_id>/download/', views.version_download, name='version_download'),
    path('<int:pk>/tasks/', views.tasks, name='tasks'),
    path('<int:pk>/tasks/new/', views.task_create, name='task_create'),
    path('<int:pk>/tasks/<int:task_id>/', views.task_detail, name='task_detail'),
    path('<int:pk>/progress/', views.history, name='history'),
    path('<int:pk>/progress/new/', views.commit_create, name='commit_create'),
    path('<int:pk>/progress/<int:commit_id>/', views.commit_detail, name='commit_detail'),
    path('<int:pk>/progress/<int:commit_id>/comments/', views.comment_create, name='comment_create'),
]
