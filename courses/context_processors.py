from courses.models import Course

# 侧边栏最多展示 5 门最近相关的课程，避免课程变多后导航被拉长。
SIDEBAR_COURSE_LIMIT = 5


def courses_processor(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'list_courses': []}
    if user.user_type == 2:
        courses = Course.objects.filter(teacher=user)
    else:
        courses = Course.objects.filter(students=user)
    return {'list_courses': courses.select_related('teacher').order_by('-pk')[:SIDEBAR_COURSE_LIMIT]}
