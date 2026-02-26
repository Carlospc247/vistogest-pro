from django import forms
from .models import Candidatura
from django.core.exceptions import ValidationError

class CandidaturaForm(forms.ModelForm):
    """
    🛡️ RIGOR SOTARQ: Validação de segurança para Recrutamento.
    Garante que apenas documentos legítimos entrem no sistema.
    """
    class Meta:
        model = Candidatura
        fields = ['concurso', 'nome', 'email', 'telefone', 'cv', 'observacoes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # (1) Tornar o CV obrigatório e aplicar classes CSS modernas
        self.fields['cv'].required = True
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})

    def clean_cv(self):
        file = self.cleaned_data.get('cv')
        if file:
            # Validar Extensão
            extension = file.name.split('.')[-1].lower()
            if extension not in ['pdf', 'doc', 'docx']:
                raise ValidationError("Rigor de Segurança: Apenas ficheiros PDF ou Word são permitidos.")
            
            # Validar Tamanho (Máximo 5MB)
            if file.size > 5 * 1024 * 1024:
                raise ValidationError("O ficheiro é demasiado grande. O limite é 5MB.")
        return file