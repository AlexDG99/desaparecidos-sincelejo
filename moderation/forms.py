from django import forms

from core.forms import BootstrapFormMixin

from .models import ContentReport


class ReportForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ContentReport
        fields = ['motivo', 'comentario']
        labels = {'motivo': 'Motivo', 'comentario': 'Comentario (opcional)'}
        widgets = {'comentario': forms.Textarea(attrs={'rows': 3})}


class ResolveReportForm(BootstrapFormMixin, forms.Form):
    accion = forms.ChoiceField(choices=[('mantener', 'Mantener el contenido'), ('editar', 'Editar el contenido'),
                                        ('retirar', 'Retirar el contenido')], label='Decisión')
    motivo = forms.CharField(label='Motivo del retiro (obligatorio al retirar)', required=False,
                             widget=forms.Textarea(attrs={'rows': 2}))
    texto = forms.CharField(label='Nuevo texto (señas particulares o descripción; obligatorio al editar)', required=False,
                            widget=forms.Textarea(attrs={'rows': 3}))
