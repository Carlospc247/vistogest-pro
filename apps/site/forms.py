# apps/site/forms.py
from django import forms
from .models import Candidatura
from django.core.exceptions import ValidationError
from pathlib import Path
from django.db.models import Q
from django.utils import timezone
from .models import Candidatura, Concurso




class CandidaturaForm(forms.ModelForm):
    """Formulário público para submeter candidatura e anexar CV."""

    class Meta:
        model = Candidatura
        fields = ['concurso', 'nome', 'email', 'telefone', 'cv', 'observacoes']
        widgets = {
            'concurso': forms.Select(attrs={'class': 'form-control'}),
            'nome': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'tel'}),
            'cv': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,.doc,.docx'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = timezone.localdate()
        self.fields['cv'].required = True
        self.fields['concurso'].queryset = Concurso.objects.filter(ativo=True).filter(
            Q(data_inicio__isnull=True) | Q(data_inicio__lte=hoje),
            Q(data_fim__isnull=True) | Q(data_fim__gte=hoje),
        ).order_by('titulo')

    def clean_cv(self):
        ficheiro = self.cleaned_data.get('cv')
        if not ficheiro:
            raise ValidationError('Anexe o seu CV em PDF ou Word.')
        extensao = Path(ficheiro.name).suffix.lower()
        if extensao not in {'.pdf', '.doc', '.docx'}:
            raise ValidationError('Apenas ficheiros PDF, DOC ou DOCX são permitidos.')
        if ficheiro.size > 5 * 1024 * 1024:
            raise ValidationError('O CV não pode ultrapassar 5 MB.')
        return ficheiro

