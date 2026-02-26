# Em apps/servicos/forms.py

from django import forms
from .models import Servico, AgendamentoServico
from apps.empresas.models import Categoria
from apps.clientes.models import Cliente
from apps.funcionarios.models import Funcionario


# -----------------------------------------------------------------------------
# Classes de Estilo Padrão (Tailwind CSS)
# -----------------------------------------------------------------------------

form_field_classes = 'block w-full rounded-md border-0 py-1.5 text-gray-900 dark:text-white shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6 dark:bg-gray-700'




class ServicoForm(forms.ModelForm):
    class Meta:
        model = Servico
        # --- CORREÇÃO APLICADA AQUI ---
        # A lista de campos agora reflete o modelo de CATÁLOGO de serviços
        fields = [
            'nome',
            'categoria',
            'duracao_padrao_minutos',
            'preco_padrao',
            'desconto_percentual',
            'iva_percentual',
            'instrucoes_padrao',
            'ativo'
        ]
        
        labels = {
            'nome': 'Nome do Serviço (Catálogo)',
            'categoria': 'Categoria do Serviço',
            'duracao_padrao_minutos': 'Duração Padrão (minutos)',
            'preco_padrao': 'Preço Padrão (AKZ)',
            'desconto_percentual': 'Desconto/Promoção',
            'iva_percentual': 'IVA ( 0% )',
            'instrucoes_padrao': 'Instruções / Observações Padrão',
            'ativo': 'Serviço Ativo no Catálogo'
        }
        
        widgets = {
            'instrucoes_padrao': forms.Textarea(attrs={'rows': 3}),
            'foto': forms.FileInput(),
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        form_field_classes = 'block w-full rounded-md border-0 py-1.5 text-gray-900 dark:text-white shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6 dark:bg-gray-700'
        checkbox_classes = 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-600'
        
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = checkbox_classes
            else:
                field.widget.attrs['class'] = form_field_classes
        
        if empresa:
            if 'categoria' in self.fields:
                self.fields['categoria'].queryset = Categoria.objects.filter(empresa=empresa, ativa=True)


class AgendamentoServicoForm(forms.ModelForm):
    class Meta:
        model = AgendamentoServico # Usa o modelo refatorado
        
        # --- CORREÇÃO APLICADA AQUI ---
        # A lista de campos agora reflete o novo modelo 'Agendamento'
        fields = [
            'servico', 
            'cliente', # O nome correto do campo é 'cliente'
            'funcionario', 
            'data_hora', 
            'valor_cobrado',
            'observacoes'
        ]
        
        labels = {
            'servico': 'Tipo de Serviço (do Catálogo)',
            'cliente': 'Cliente',
            'funcionario': 'Funcionário Responsável',
            'data_hora': 'Data e Hora do Agendamento',
            'valor_cobrado': 'Valor a ser Cobrado (AKZ)',
            'observacoes': 'Observações (Opcional)',
        }

        widgets = {
            'data_hora': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        form_field_classes = 'block w-full rounded-md border-0 py-1.5 text-gray-900 dark:text-white shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6 dark:bg-gray-700'

        for field in self.fields.values():
             field.widget.attrs['class'] = form_field_classes

        if empresa:
            self.fields['servico'].queryset = Servico.objects.filter(empresa=empresa, ativo=True)
            self.fields['cliente'].queryset = Cliente.objects.filter(empresa=empresa, ativo=True)
            self.fields['funcionario'].queryset = Funcionario.objects.filter(empresa=empresa, ativo=True)

# -----------------------------------------------------------------------------
# FORMULÁRIO PARA AÇÃO DE FINALIZAR SERVIÇO
# -----------------------------------------------------------------------------
class FinalizarServicoForm(forms.Form):
    resultado_servico = forms.CharField(
        label="Resultado do Serviço",
        required=True,
        widget=forms.Textarea(attrs={'rows': 4, 'class': form_field_classes})
    )
    recomendacoes = forms.CharField(
        label="Recomendações ao Cliente (Opcional)",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': form_field_classes})
    )




form_field_classes = 'block w-full rounded-md border-0 py-1.5 text-gray-900 dark:text-white shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6 dark:bg-gray-700'

class FinalizarServicoForm(forms.Form):
    resultado_servico = forms.CharField(
        label="Resultado do Serviço",
        required=True,
        widget=forms.Textarea(attrs={
            'class': form_field_classes,
            'rows': 4,
            'placeholder': 'Descreva os resultados e medições do serviço realizado...'
        })
    )
    recomendacoes = forms.CharField(
        label="Recomendações ao Cliente (Opcional)",
        required=False,
        widget=forms.Textarea(attrs={
            'class': form_field_classes,
            'rows': 3,
            'placeholder': 'Descreva quaisquer recomendações para o cliente...'
        })
    )



from django import forms
from .models import NotificacaoAgendamento, ConfiguracaoNotificacao

class NotificacaoAgendamentoForm(forms.ModelForm):
    class Meta:
        model = NotificacaoAgendamento
        fields = [
            'agendamento', 'cliente', 'tipo_notificacao', 'dias_antecedencia',
            'titulo', 'mensagem', 'data_agendada_envio', 'status'
        ]
        widgets = {
            'data_agendada_envio': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'mensagem': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'dias_antecedencia': 'Dias de Antecedência',
            'data_agendada_envio': 'Data/Hora Agendada',
        }


class ConfiguracaoNotificacaoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoNotificacao
        fields = [
            'email_ativo', 'sms_ativo', 'whatsapp_ativo',
            'dias_notificacao', 'horario_inicio_envio', 'horario_fim_envio',
            'template_email_titulo', 'template_email_mensagem', 'template_sms_mensagem',
            'max_tentativas_envio', 'intervalo_tentativas_horas'
        ]
        widgets = {
            'dias_notificacao': forms.TextInput(attrs={'placeholder': 'Ex: 15,7,3,1'}),
            'horario_inicio_envio': forms.TimeInput(attrs={'type': 'time'}),
            'horario_fim_envio': forms.TimeInput(attrs={'type': 'time'}),
            'template_email_mensagem': forms.Textarea(attrs={'rows': 6}),
            'template_sms_mensagem': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'email_ativo': 'Email Ativo',
            'sms_ativo': 'SMS Ativo',
            'whatsapp_ativo': 'WhatsApp Ativo',
            'dias_notificacao': 'Dias de Antecedência',
            'horario_inicio_envio': 'Horário Início',
            'horario_fim_envio': 'Horário Fim',
            'max_tentativas_envio': 'Máx. Tentativas',
            'intervalo_tentativas_horas': 'Intervalo entre Tentativas (h)',
        }




