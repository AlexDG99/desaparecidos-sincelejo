from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from accounts.models import User


def role_required(*roles):
    """Exige sesión iniciada y uno de los roles indicados; de lo contrario responde 403 (HU-13 CA6)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.rol not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


moderator_required = role_required(User.Rol.MODERADOR, User.Rol.ADMINISTRADOR)
admin_required = role_required(User.Rol.ADMINISTRADOR)
