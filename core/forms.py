from django import forms


class BootstrapFormMixin:
    """Aplica clases de Bootstrap y atributos de accesibilidad a todos los campos."""

    def _style_fields(self):
        for name, field in self.fields.items():
            widget = field.widget
            css = widget.attrs.get('class', '')
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = (css + ' form-check-input').strip()
            elif isinstance(widget, forms.Select):
                widget.attrs['class'] = (css + ' form-select').strip()
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs['class'] = (css + ' form-control').strip()
            else:
                widget.attrs['class'] = (css + ' form-control').strip()
            if field.required and not isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('aria-required', 'true')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()

    def is_valid(self):
        valid = super().is_valid()
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs['class'] = (
                    self.fields[name].widget.attrs.get('class', '') + ' is-invalid').strip()
                self.fields[name].widget.attrs['aria-invalid'] = 'true'
        return valid
