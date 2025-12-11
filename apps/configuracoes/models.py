import os
from django.db import models
from django.core.validators import RegexValidator
from apps.core.models import TimeStampedModel
from datetime import date
from cloudinary.models import CloudinaryField


# ==============================================================================
# MODELOS ESSENCIAIS PARA A OPERAÇÃO
# ==============================================================================

class ConfiguracaoFiscal(TimeStampedModel):
    
    empresa = models.OneToOneField('core.Empresa', on_delete=models.CASCADE, related_name='config_fiscal', help_text="Ex: Farmácia Neway LDA")
    
    # Dados da empresa para documentos fiscais
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255, blank=True, help_text="Ex: Neway Farmácia")
    nif = models.CharField("NIF", max_length=14, help_text="Número de Identificação Fiscal da empresa.")
    email = models.CharField(max_length=200, blank=True, help_text="Ex: empresa@gmail.com")
    site = models.CharField(max_length=200, blank=True, help_text="Ex: empresa.com")
    telefone = models.CharField(max_length=200, blank=True, help_text="Ex: contacto da empresa")
    
    # Endereço fiscal
    endereco = models.CharField(max_length=255)
    cidade = models.CharField(max_length=100)
    provincia = models.CharField(max_length=50)
    postal = models.CharField(max_length=4)
    
    # Regime tributário simplificado para o contexto angolano
    REGIME_CHOICES = [
        ('geral', 'Regime Geral'),
        ('simplificado', 'Regime Simplificado (IVA)'),
        ('exclusao', 'Regime de Não Sujeição (Exclusão)'),
        ('outros', 'Outros (Regimes especiais e outros)'),
    ]
    regime_tributario = models.CharField(max_length=20, choices=REGIME_CHOICES, default='geral')
    
    # Configurações básicas de impressão
    impressora_cupom = models.CharField("Impressora de Talões", max_length=200, blank=True, help_text="Nome da impressora para talões e recibos (ex: POS-80).")
    

    class Meta:
        verbose_name = "Configuração Fiscal"
        verbose_name_plural = "Configurações Fiscais"
    
    def __str__(self):
        return f"Configuração Fiscal - {self.empresa.nome}"



# NOVO MODELO para Dados Bancários
class DadosBancarios(TimeStampedModel):
    configuracao_fiscal = models.ForeignKey(
        'ConfiguracaoFiscal', 
        on_delete=models.CASCADE, 
        related_name='dados_bancarios'
    )
    nome_banco = models.CharField("Nome do Banco", max_length=150)
    numero_conta = models.CharField("Número da Conta", max_length=50)
    iban = models.CharField("IBAN", max_length=34)
    swift = models.CharField("SWIFT/BIC", max_length=11, blank=True, null=True)

    class Meta:
        verbose_name = "Dado Bancário"
        verbose_name_plural = "Dados Bancários"
    
    def __str__(self):
        return f"{self.nome_banco} - {self.numero_conta}"
    

class BackupConfiguracao(TimeStampedModel):
    """
    Configurações de backup do sistema para cada empresa. Essencial para a segurança dos dados.
    """
    empresa = models.OneToOneField('core.Empresa', on_delete=models.CASCADE, related_name='config_backup')
    
    # Configurações de backup
    backup_automatico = models.BooleanField("Ativar Backup Automático", default=True)
    frequencia_backup = models.CharField(
        "Frequência",
        max_length=15, 
        choices=[('diario', 'Diário'), ('semanal', 'Semanal')], 
        default='diario'
    )
    horario_backup = models.TimeField("Horário do Backup", default='02:00')
    
    # Retenção
    dias_retencao_backup = models.IntegerField(
        "Reter Backups por (dias)",
        default=30,
        help_text="Número de dias que os ficheiros de backup devem ser mantidos."
    )
    
    # Notificações
    notificar_erro = models.BooleanField("Notificar em Caso de Erro", default=True)
    email_notificacao = models.EmailField("Email para Notificações", blank=True, help_text="Endereço de email para receber alertas de falha no backup.")
    
    # Status (gerido pelo sistema)
    ultimo_backup = models.DateTimeField(null=True, blank=True)
    status_ultimo_backup = models.CharField(max_length=20, choices=[
        ('sucesso', 'Sucesso'),
        ('erro', 'Erro'),
        ('em_andamento', 'Em Andamento'),
    ], blank=True)
    
    class Meta:
        verbose_name = "Configuração de Backup"
        verbose_name_plural = "Configurações de Backup"
    
    def __str__(self):
        return f"Configuração de Backup - {self.empresa.nome}"

class PersonalizacaoInterface(TimeStampedModel):
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, null=True, blank=True)
    usuario = models.ForeignKey('core.Usuario', on_delete=models.CASCADE, null=True, blank=True)
    
    # Tema e cores
    tema = models.CharField(max_length=20, choices=[
        ('claro', 'Claro'),
        ('escuro', 'Escuro'),
        ('auto', 'Automático (Sistema)'),
    ], default='auto')
    
    cor_primaria = models.CharField(
        max_length=7,
        default='#5D5CDE', # Um azul/púrpura como padrão
        help_text="Cor principal da interface (hexadecimal, ex: #5D5CDE)"
    )
    
    # Logo
    logo_principal = CloudinaryField('foto', blank=True, null=True)


    class Meta:
        verbose_name = "Personalização de Interface"
        verbose_name_plural = "Personalizações de Interface"
        unique_together = [['empresa', 'usuario']]
    
    def __str__(self):
        if self.usuario:
            return f"Personalização de {self.usuario.username}"
        elif self.empresa:
            return f"Personalização da Empresa {self.empresa.nome}"
        return "Personalização Global"


class HistoricoBackup(TimeStampedModel):
    """
    Regista cada execução de backup, seja manual ou automática.
    """
    TIPO_CHOICES = [
        ('manual', 'Manual'),
        ('automatico', 'Automático'),
    ]
    STATUS_CHOICES = [
        ('processando', 'Processando'),
        ('sucesso', 'Sucesso'),
        ('erro', 'Erro'),
    ]

    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='historico_backups')
    
    tipo = models.CharField("Tipo de Backup", max_length=15, choices=TIPO_CHOICES)
    status = models.CharField("Status", max_length=15, choices=STATUS_CHOICES, default='processando')
    
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_conclusao = models.DateTimeField(null=True, blank=True)
    
    ficheiro_backup = models.FileField("Ficheiro do Backup", upload_to='backups/%Y/%m/', null=True, blank=True)
    tamanho_ficheiro = models.BigIntegerField("Tamanho (bytes)", default=0)
    
    solicitado_por = models.ForeignKey(
        'core.Usuario', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Utilizador que iniciou o backup manual."
    )
    
    detalhes_erro = models.TextField("Detalhes do Erro", blank=True)

    class Meta:
        verbose_name = "Histórico de Backup"
        verbose_name_plural = "Históricos de Backup"
        ordering = ['-data_criacao']

    @property
    def nome_ficheiro(self):
        if self.ficheiro_backup:
            return os.path.basename(self.ficheiro_backup.name)
        return "N/A"
