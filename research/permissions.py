from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from functools import wraps


def workspace_reader(view):
    """Public access is limited to explicitly seeded demo workspaces."""
    protected = login_required(view)

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from .models import ResearchWorkspace
            if not ResearchWorkspace.objects.filter(pk=kwargs.get('pk'), demo_key__isnull=False).exclude(demo_key='').exists():
                return protected(request, *args, **kwargs)
        return view(request, *args, **kwargs)
    return wrapped


def workspace_role(user, workspace):
    if workspace.is_demo:
        return 'guest'
    if not user.is_authenticated:
        return None
    if user.pk == workspace.owner_id:
        return 'owner'
    return workspace.memberships.filter(user=user).values_list('role', flat=True).first()


def require_workspace(user, workspace, write=False, owner=False):
    role = workspace_role(user, workspace)
    if workspace.is_demo and (write or owner):
        raise PermissionDenied('访客演示项目仅供查看；请登录后在自己的项目中操作。')
    if role is None or (owner and role != 'owner') or (write and role == 'viewer'):
        raise PermissionDenied('您没有此项目的操作权限。')
    if write and workspace.status == 'archived':
        raise PermissionDenied('项目已归档，历史内容仍可查看。')
    return role
