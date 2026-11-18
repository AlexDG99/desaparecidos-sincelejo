from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserCreationForm

from .models import ConsentRecord, DataRequest, User


class StaffCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('email', 'nombre', 'rol')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = user.rol == User.Rol.ADMINISTRADOR
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Gestión de usuarios. Aquí el administrador crea las cuentas de moderador y administrador (HU-13)."""
    add_form = StaffCreationForm
    ordering = ('email',)
    list_display = ('email', 'nombre', 'rol', 'verificacion', 'is_active')
    list_filter = ('rol', 'verificacion', 'is_active')
    search_fields = ('email', 'nombre', 'cedula')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Datos', {'fields': ('nombre', 'rol', 'cedula', 'telefono', 'parentesco', 'verificacion', 'verificacion_motivo')}),
        ('Estado', {'fields': ('is_active', 'is_staff', 'is_superuser', 'bloqueado_hasta', 'intentos_fallidos')}),
    )
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': ('email', 'nombre', 'rol', 'password1', 'password2')}),)


admin.site.register(ConsentRecord)
admin.site.register(DataRequest)
