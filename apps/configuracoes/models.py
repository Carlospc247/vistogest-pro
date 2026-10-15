import os
from datetime import time
from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from apps.core.models import TimeStampedModel
from cloudinary.models import CloudinaryField

HEX_COLOR_VALIDATOR = RegexValidator(regex=r"^#[0-9A-Fa-f]{6}$", message="Indique uma cor hexadecimal válida, por exemplo #3157A4.")

class ConfiguracaoFiscal(TimeStampedModel):
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255, blank=True, help_text="Nome comercial da empresa.")
    nif = models.CharField("NIF", max_length=14, help_text="Número de Identificação Fiscal.")
    email = models.EmailField(max_length=200, blank=True)
    site = models.CharField(max_length=200, blank=True)
    telefone = models.CharField(max_length=200, blank=True)
    endereco = models.CharField(max_length=255)
    cidade = models.CharField(max_length=100)
    provincia = models.CharField(max_length=50)
    postal = models.CharField(max_length=4)
    REGIME_CHOICES = [("geral", "Regime Geral"), ("simplificado", "Regime Simplificado (IVA)"), ("exclusao", "Regime de Não Sujeição (Exclusão)"), ("outros", "Outros (regimes especiais)")]
    regime_tributario = models.CharField(max_length=20, choices=REGIME_CHOICES, default="geral")
    impressora_cupom = models.CharField("Impressora de Talões", max_length=200, blank=True)
    class Meta:
        verbose_name = "Configuração Fiscal"
        verbose_name_plural = "Configurações Fiscais"
        permissions = [
            ("acessar_configuracoes", "Pode aceder às configurações da empresa"),
            ("alterar_dados_fiscais", "Pode alterar dados fiscais"),
            ("acessar_detalhes_fiscal", "Pode consultar dados fiscais"),
            ("eliminar_detalhes_fiscal", "Pode eliminar dados fiscais"),
            ("alterar_interface", "Pode personalizar a interface"),
            ("atualizar_backups", "Pode alterar a política de backups"),
            ("ver_configuracoes", "Pode consultar o histórico de backups"),
            ("fazer_backup_manual", "Pode executar backups manuais"),
            ("descarregar_backup", "Pode descarregar backups"),
            ("restaurar_backup", "Pode restaurar backups"),
            ("criar_dados_bancarios", "Pode criar dados bancários"),
            ("atualizar_dados_bancarios", "Pode editar dados bancários"),
            ("apagar_dados_bancarios", "Pode apagar dados bancários"),
        ]
    def __str__(self):
        return f"Configuração Fiscal - {self.nome_fantasia or self.razao_social or 'Por configurar'}"

class DadosBancarios(TimeStampedModel):
    configuracao_fiscal = models.ForeignKey(ConfiguracaoFiscal, on_delete=models.CASCADE, related_name="dados_bancarios")
    nome_banco = models.CharField("Nome do Banco", max_length=150)
    numero_conta = models.CharField("Número da Conta", max_length=50)
    iban = models.CharField("IBAN", max_length=34)
    swift = models.CharField("SWIFT/BIC", max_length=11, blank=True, null=True)
    class Meta:
        verbose_name = "Dado Bancário"
        verbose_name_plural = "Dados Bancários"
    def __str__(self): return f"{self.nome_banco} - {self.numero_conta}"

class BackupConfiguracao(TimeStampedModel):
    backup_automatico = models.BooleanField("Ativar Backup Automático", default=True)
    frequencia_backup = models.CharField("Frequência", max_length=15, choices=[("diario", "Diário"), ("semanal", "Semanal")], default="diario")
    horario_backup = models.TimeField("Horário do Backup", default=time(2, 0))
    dias_retencao_backup = models.IntegerField("Reter Backups por (dias)", default=30, validators=[MinValueValidator(1), MaxValueValidator(3650)], help_text="Número de dias durante os quais os backups são retidos.")
    notificar_erro = models.BooleanField("Notificar em Caso de Erro", default=True)
    email_notificacao = models.EmailField("Email para Notificações", blank=True)
    ultimo_backup = models.DateTimeField(null=True, blank=True)
    status_ultimo_backup = models.CharField(max_length=20, choices=[("sucesso", "Sucesso"), ("erro", "Erro"), ("em_andamento", "Em andamento")], blank=True)
    class Meta:
        verbose_name = "Configuração de Backup"
        verbose_name_plural = "Configurações de Backup"
    def __str__(self): return f"Configuração de Backup ({self.get_frequencia_backup_display()})"

class PersonalizacaoInterface(TimeStampedModel):
    tema = models.CharField(max_length=20, choices=[("claro", "Claro"), ("escuro", "Escuro"), ("auto", "Automático (Sistema)")], default="auto")
    cor_primaria = models.CharField(max_length=7, default="#5D5CDE", validators=[HEX_COLOR_VALIDATOR], help_text="Cor hexadecimal, por exemplo #5D5CDE.")
    logo_principal = CloudinaryField("Logótipo Principal", blank=True, null=True)
    class Meta:
        verbose_name = "Personalização de Interface"
        verbose_name_plural = "Personalizações de Interface"
        #unique_together = [["usuario"]]
    def __str__(self): return f"Personalização de"

class HistoricoBackup(TimeStampedModel):
    TIPO_CHOICES = [("manual", "Manual"), ("automatico", "Automático")]
    STATUS_CHOICES = [("processando", "Processando"), ("sucesso", "Sucesso"), ("erro", "Erro")]
    tipo = models.CharField("Tipo de Backup", max_length=15, choices=TIPO_CHOICES)
    status = models.CharField("Status", max_length=15, choices=STATUS_CHOICES, default="processando")
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_conclusao = models.DateTimeField(null=True, blank=True)
    ficheiro_backup = models.FileField("Ficheiro do Backup", upload_to="backups/%Y/%m/", null=True, blank=True)
    tamanho_ficheiro = models.BigIntegerField("Tamanho (bytes)", default=0)
    solicitado_por = models.ForeignKey("core.Usuario", on_delete=models.SET_NULL, null=True, blank=True)
    detalhes_erro = models.TextField("Detalhes do Erro", blank=True)
    class Meta:
        verbose_name = "Histórico de Backup"
        verbose_name_plural = "Históricos de Backup"
        ordering = ["-data_criacao"]
    @property
    def nome_ficheiro(self): return os.path.basename(self.ficheiro_backup.name) if self.ficheiro_backup else "N/A"
