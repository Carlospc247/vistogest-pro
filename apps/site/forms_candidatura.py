# apps/site/forms_candidatura.py
"""Formulário público para candidaturas a concursos do site."""
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import Candidatura, Concurso


MAX_CV_SIZE = 5 * 1024 * 1024
MAX_DOCX_EXPANDED_SIZE = 25 * 1024 * 1024
MAX_DOCX_MEMBERS = 1000


class CandidaturaForm(forms.ModelForm):
    """Valida os dados da candidatura e o conteúdo básico do CV carregado."""

    class Meta:
        model = Candidatura
        fields = ["concurso", "nome", "email", "telefone", "cv", "observacoes"]
        widgets = {
            "concurso": forms.Select(attrs={"class": "form-select"}),
            "nome": forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
            "telefone": forms.TextInput(attrs={"class": "form-control", "autocomplete": "tel"}),
            "cv": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.doc,.docx"}),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }
        labels = {
            "concurso": "Vaga / concurso",
            "nome": "Nome completo",
            "email": "E-mail",
            "telefone": "Telefone",
            "cv": "Currículo (PDF ou Word, máximo 5 MB)",
            "observacoes": "Observações adicionais",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = timezone.localdate()
        concursos_abertos = (
            Concurso.objects.filter(ativo=True)
            .filter(Q(data_inicio__isnull=True) | Q(data_inicio__lte=hoje))
            .filter(Q(data_fim__isnull=True) | Q(data_fim__gte=hoje))
            .order_by("titulo")
        )
        # Ao editar uma candidatura existente, conserva a opção actual para que
        # uma vaga que entretanto fechou não torne o registo impossível de editar.
        if self.instance.pk and self.instance.concurso_id:
            concursos_abertos = (concursos_abertos | Concurso.objects.filter(pk=self.instance.concurso_id)).distinct()
        self.fields["concurso"].queryset = concursos_abertos
        self.fields["cv"].required = not bool(self.instance.pk and self.instance.cv)

    def clean_nome(self):
        nome = self.cleaned_data["nome"].strip()
        if len(nome) < 2:
            raise ValidationError("Introduza o nome completo do candidato.")
        return nome

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_cv(self):
        ficheiro = self.cleaned_data.get("cv")
        if not ficheiro:
            return ficheiro

        # Não revalida nem abre ficheiros já guardados quando o formulário é editado.
        if getattr(ficheiro, "_committed", False):
            return ficheiro

        if ficheiro.size > MAX_CV_SIZE:
            raise ValidationError("O currículo não pode exceder 5 MB.")

        extensao = Path(ficheiro.name).suffix.lower()
        if extensao not in {".pdf", ".doc", ".docx"}:
            raise ValidationError("Apenas são permitidos ficheiros PDF, DOC ou DOCX.")

        try:
            ficheiro.seek(0)
            assinatura = ficheiro.read(8)

            if extensao == ".pdf":
                if not assinatura.startswith(b"%PDF-"):
                    raise ValidationError("O conteúdo do ficheiro não corresponde a um PDF válido.")

            elif extensao == ".doc":
                # Assinatura OLE Compound File usada pelos documentos .doc antigos.
                if assinatura != bytes.fromhex("D0CF11E0A1B11AE1"):
                    raise ValidationError("O conteúdo do ficheiro não corresponde a um documento DOC válido.")

            else:  # .docx é um ZIP Open XML; valida a estrutura sem descomprimir tudo.
                ficheiro.seek(0)
                with ZipFile(ficheiro) as arquivo:
                    membros = arquivo.infolist()
                    nomes = {membro.filename for membro in membros}
                    tamanho_expandido = sum(membro.file_size for membro in membros)
                    if (
                        "[Content_Types].xml" not in nomes
                        or "word/document.xml" not in nomes
                        or len(membros) > MAX_DOCX_MEMBERS
                        or tamanho_expandido > MAX_DOCX_EXPANDED_SIZE
                    ):
                        raise ValidationError("O ficheiro não tem uma estrutura DOCX válida ou é demasiado complexo.")

        except BadZipFile:
            raise ValidationError("O ficheiro DOCX está danificado ou não é um documento Word válido.")
        except (OSError, RuntimeError):
            raise ValidationError("Não foi possível ler o currículo enviado.")
        finally:
            try:
                ficheiro.seek(0)
            except (AttributeError, OSError):
                pass

        return ficheiro
