from django.urls import path
from courses import views

app_name = 'courses'
urlpatterns = [
    path('new/', views.CreateCourse.as_view(), name='create'),
    path('detail/<int:pk>/', views.CourseDetail.as_view(), name='detail'),
    path('edit/<int:pk>/', views.UpdateCourse.as_view(), name='update'),
    path('archive/<int:pk>/', views.archive_course, name='archive'),
    path('all/', views.ListCourse.as_view(), name='list'),
    path('enroll/<int:pk>/', views.enroll_course, name='enroll'),
    path('unenroll/<int:pk>/', views.unenroll_course, name='unenroll'),
]
