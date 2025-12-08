# apps/funcionarios/models.py
from email.policy import default
from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel, Empresa, Loja
from decimal import Decimal
from datetime import date, datetime, timedelta
from django.utils import timezone
import uuid
from pharmassys import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Permission
from apps.core.models import TimeStampedModel
from cloudinary.models import CloudinaryField



class Cargo(TimeStampedModel):
    """Cargos dos funcionários — com permissões integradas ao sistema Django"""
    nome = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20)
    descricao = models.TextField(blank=True)

    empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="cargos",
        null=True,
        blank=True,
        help_text="Se vazio, é um cargo global do sistema (modelo base)."
    )

    # Hierarquia
    cargo_superior = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cargos_subordinados'
    )
    nivel_hierarquico = models.IntegerField(default=1, help_text="1 = Nível mais alto na hierarquia")

    # ⚙️ Permissões Django (para sincronizar com o Group e usuários)
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        verbose_name="Permissões do Django",
        help_text="Permissões aplicáveis a este cargo (vinculadas ao grupo automaticamente)."
    )

    # Características
    CATEGORIA_CHOICES = [
        ('diretoria', 'Diretoria'),
        ('gerencia', 'Gerência'),
        ('coordenacao', 'Coordenação'),
        ('supervisao', 'Supervisão'),
        ('operacional', 'Operacional'),
        ('tecnico', 'Técnico'),
        ('administrativo', 'Administrativo'),
        ('vendas', 'Vendas'),
        ('direcao_tecnica', 'Direção Técnica'),
        ('estagiario', 'Estagiário'),
        ('terceirizado', 'Terceirizado'),
        ('rh', 'Recursos Humanos'),
        ('financeiro', 'Contabilidade'),
        ('outros', 'Outros')
    ]
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='operacional')

    # 💰 Remuneração
    salario_base = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    vale_alimentacao = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    vale_transporte = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    # 💼 Permissões de negócios
    selecionar_todos = models.BooleanField(default=False, verbose_name="Selecionar todas as permissões")

    pode_estornar_pagamento = models.BooleanField(default=False)
    pode_pagar_salario = models.BooleanField(default=True)

    # Vendas
    pode_vender = models.BooleanField(default=True)
    pode_ver_vendas = models.BooleanField(default=False)
    pode_fazer_desconto = models.BooleanField(default=False)
    limite_desconto_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pode_cancelar_venda = models.BooleanField(default=False)
    pode_fazer_devolucao = models.BooleanField(default=False)
    pode_alterar_preco = models.BooleanField(default=False)
    pode_emitir_notacredito = models.BooleanField(default=False)
    pode_aplicar_notacredito = models.BooleanField(default=False)
    pode_aprovar_notacredito = models.BooleanField(default=False)
    pode_emitir_notadebito = models.BooleanField(default=False)
    pode_aplicar_notadebito = models.BooleanField(default=False)
    pode_aprovar_notadebito = models.BooleanField(default=False)
    pode_emitir_documentotransporte = models.BooleanField(default=False)
    pode_confirmar_entrega = models.BooleanField(default=False)

    # Gestão
    pode_gerenciar_estoque = models.BooleanField(default=False)
    pode_fazer_compras = models.BooleanField(default=False)
    pode_aprovar_pedidos = models.BooleanField(default=False)
    pode_gerenciar_funcionarios = models.BooleanField(default=False)
    pode_editar_produtos = models.BooleanField(default=False)

    # Faturas
    pode_emitir_faturacredito = models.BooleanField(default=False)
    pode_liquidar_faturacredito = models.BooleanField(default=False)
    pode_emitir_proforma = models.BooleanField(default=False)
    pode_aprovar_proforma = models.BooleanField(default=False)
    pode_emitir_recibo = models.BooleanField(default=False)
    pode_acessar_documentos = models.BooleanField(default=False)

    pode_acessar_rh = models.BooleanField(default=False)
    pode_acessar_financeiro = models.BooleanField(default=False)
    pode_acessar_fornecedores = models.BooleanField(default=False)
    pode_alterar_dados_fiscais = models.BooleanField(default=False)
    pode_eliminar_detalhes_fiscal = models.BooleanField(default=False)
    
    pode_acessar_detalhes_fiscal = models.BooleanField(default=False)
    pode_fazer_backup_manual = models.BooleanField(default=False)
    pode_ver_configuracoes = models.BooleanField(default=False)
    pode_atualizar_backups = models.BooleanField(default=False)
    pode_alterar_interface = models.BooleanField(default=False)
    pode_acessar_configuracoes = models.BooleanField(default=False)

    pode_exportar_saft = models.BooleanField(default=False)
    pode_ver_historico_saft = models.BooleanField(default=False)
    pode_baixar_saft = models.BooleanField(default=False)
    pode_validar_saft = models.BooleanField(default=False)
    pode_visualizar_saft = models.BooleanField(default=False)
    pode_ver_status_saft = models.BooleanField(default=False)
    pode_criar_dados_bancarios = models.BooleanField(default=False)
    pode_apagar_dados_bancarios = models.BooleanField(default=False)
    pode_atualizar_dados_bancarios = models.BooleanField(default=False)

    pode_ver_taxaiva_agt = models.BooleanField(default=False)
    pode_gerir_assinatura_digital = models.BooleanField(default=False)
    pode_gerir_retencoes_na_fonte = models.BooleanField(default=False)
    pode_criar_retencoes_na_fonte = models.BooleanField(default=False)
    pode_apagar_retencoes_na_fonte = models.BooleanField(default=False)
    pode_acessar_dashboard_fiscal = models.BooleanField(default=False)
    pode_validar_documentos_fiscais = models.BooleanField(default=False)
    pode_verificar_integridade_hash = models.BooleanField(default=False)
    pode_acessar_painel_principal_fiscal = models.BooleanField(default=False)
    pode_ver_taxas_iva = models.BooleanField(default=False)
    pode_criar_taxas_iva = models.BooleanField(default=False)
    pode_apagar_taxas_iva = models.BooleanField(default=False)
    pode_ver_status_atual_assinatura_digital = models.BooleanField(default=False)
    pode_configurar_assinatura_digital = models.BooleanField(default=False)
    pode_gerar_par_chave_publica_ou_privada = models.BooleanField(default=False)

    pode_ver_relatorio_fiscal = models.BooleanField(default=False)
    pode_ver_relatorio_retencoes = models.BooleanField(default=False)
    pode_ver_relatorio_taxas_iva = models.BooleanField(default=False)
    pode_acessar_dashboard_saft = models.BooleanField(default=False)
    pode_baixar_chave_publica = models.BooleanField(default=False)
    pode_baixar_retencoes = models.BooleanField(default=False)

    pode_baixar_saft_backup_fiscal = models.BooleanField(default=False)
    pode_baixar_relatorio_retencoes = models.BooleanField(default=False)
    pode_acessar_configuracao_fiscal = models.BooleanField(default=False)
    pode_verificar_integridade_cadeia_hash_fiscal = models.BooleanField(default=False)
    




    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"
        ordering = ['nivel_hierarquico', 'nome']

    def __str__(self):
        return self.nome

    def delete(self, *args, **kwargs):
        """Impede exclusão de cargos globais."""
        if self.empresa is None:
            raise ValidationError("Cargos globais do sistema não podem ser excluídos.")
        super().delete(*args, **kwargs)

    @property
    def funcionarios_ativos(self):
        """Quantidade de funcionários ativos neste cargo."""
        return self.funcionarios.filter(ativo=True).count()





class Departamento(TimeStampedModel):
    """Departamentos globais e personalizados por empresa."""
    nome = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, unique=True)
    descricao = models.TextField(blank=True)

    responsavel = models.ForeignKey(
        'funcionarios.Funcionario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='departamentos_responsavel',
        help_text="Responsável dentro da empresa. Global não possui responsável."
    )

    loja = models.ForeignKey(
        Loja,
        on_delete=models.CASCADE,
        related_name='departamentos',
        null=True,
        blank=True,
        help_text="Se vazio, é um departamento global (modelo padrão do sistema)."
    )

    centro_custo = models.CharField(max_length=20, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"
        unique_together = ['nome', 'loja']
        ordering = ['loja', 'nome']

    def __str__(self):
        return f"{self.nome} - {self.loja.nome if self.loja else 'Global'}"



class Funcionario(TimeStampedModel):
    """Funcionários da empresa"""

    TIPO_CONTRATO_CHOICES = [
        ('pf', 'Pessoa Física'),
        ('pj', 'Pessoa Jurídica'),
        ('estagiario', 'Estagiário'),
        ('terceirizado', 'Terceirizado'),
        ('freelancer', 'Freelancer'),
        ('voluntario', 'Voluntário'),
    ]

    ESCOLARIDADE_CHOICES = [
        ('fundamental_incompleto', 'Fundamental Incompleto'),
        ('fundamental_completo', 'Fundamental Completo'),
        ('medio_incompleto', 'Médio Incompleto'),
        ('medio_completo', 'Médio Completo'),
        ('tecnico', 'Técnico'),
        ('superior_incompleto', 'Superior Incompleto'),
        ('superior_completo', 'Superior Completo'),
        ('pos_graduacao', 'Pós-graduação'),
        ('mestrado', 'Mestrado'),
        ('doutorado', 'Doutorado'),
    ]

    ESTADO_CIVIL_CHOICES = [
        ('solteiro', 'Solteiro(a)'),
        ('casado', 'Casado(a)'),
        ('divorciado', 'Divorciado(a)'),
        ('viuvo', 'Viúvo(a)'),
        ('uniao_estavel', 'União Estável'),
        ('separado', 'Separado(a)'),
    ]

    # Identificação
    matricula = models.CharField(
        max_length=20,
        editable=False,
        help_text="Gerada automaticamente no formato FUNC-00001"
    )
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Usuário do sistema (se tiver acesso)"
    )

    # Dados pessoais
    nome_completo = models.CharField(max_length=255)
    bi = models.CharField(max_length=14, unique=True)
    data_nascimento = models.DateField()
    sexo = models.CharField(max_length=1, choices=[
        ('M', 'Masculino'),
        ('F', 'Feminino'),
        ('O', 'Outro'),
    ])
    estado_civil = models.CharField(max_length=15, choices=ESTADO_CIVIL_CHOICES, blank=True)
    nacionalidade = models.CharField(max_length=50, default='Angolana')
    naturalidade = models.CharField(max_length=100, blank=True)

    # Endereço
    endereco = models.CharField(max_length=255)
    numero = models.CharField(max_length=10)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    provincia = models.CharField(max_length=50, default='Luanda')
    postal = models.CharField(max_length=9)

    # Contato
    telefone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    email_pessoal = models.EmailField(blank=True)
    email_corporativo = models.EmailField(blank=True)

    # Dados profissionais
    cargo = models.ForeignKey(Cargo, null=True, blank=True, on_delete=models.PROTECT, related_name='funcionarios')
    departamento = models.ForeignKey(Departamento, on_delete=models.PROTECT, related_name='funcionarios')
    loja_principal = models.ForeignKey(Loja, on_delete=models.PROTECT, related_name='funcionarios')
    lojas_acesso = models.ManyToManyField(
        Loja,
        related_name='funcionarios_com_acesso',
        help_text="Lojas que o funcionário tem acesso"
    )

    # Hierarquia
    supervisor = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinados'
    )

    # Contrato
    tipo_contrato = models.CharField(max_length=15, choices=TIPO_CONTRATO_CHOICES, default='pf')
    data_admissao = models.DateField()
    data_demissao = models.DateField(null=True, blank=True)
    periodo_experiencia_dias = models.IntegerField(default=90)
    data_fim_experiencia = models.DateField(null=True, blank=True)

    # Remuneração
    salario_atual = models.DecimalField(max_digits=10, decimal_places=2)
    vale_alimentacao = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    vale_transporte = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    outros_beneficios = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    comissao_percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentual de comissão sobre vendas"
    )

    # Formação
    escolaridade = models.CharField(max_length=25, choices=ESCOLARIDADE_CHOICES, blank=True)
    curso_formacao = models.CharField(max_length=200, blank=True)
    instituicao_ensino = models.CharField(max_length=200, blank=True)
    ano_conclusao = models.IntegerField(null=True, blank=True)

    
    outros_registros = models.TextField(blank=True, help_text="Outros registros profissionais")

    # Dados bancários
    banco = models.CharField(max_length=100, blank=True)
    agencia = models.CharField(max_length=20, blank=True)
    conta_corrente = models.CharField(max_length=30, blank=True)
    tipo_conta = models.CharField(max_length=20, choices=[
        ('corrente', 'Conta Corrente'),
        ('poupanca', 'Poupança'),
        ('salario', 'Conta Salário'),
    ], blank=True)

    # Jornada
    carga_horaria_semanal = models.IntegerField(default=44, help_text="Horas semanais")
    horario_entrada = models.TimeField(null=True, blank=True)
    horario_saida = models.TimeField(null=True, blank=True)
    horario_almoco_inicio = models.TimeField(null=True, blank=True)
    horario_almoco_fim = models.TimeField(null=True, blank=True)
    trabalha_sabado = models.BooleanField(default=False)
    trabalha_domingo = models.BooleanField(default=False)
    trabalha_feriado = models.BooleanField(default=False)

    # Status
    ativo = models.BooleanField(default=True)
    em_experiencia = models.BooleanField(default=True)
    afastado = models.BooleanField(default=False)
    motivo_afastamento = models.TextField(blank=True)
    data_inicio_afastamento = models.DateField(null=True, blank=True)
    data_fim_afastamento = models.DateField(null=True, blank=True)

    observacoes = models.TextField(blank=True)
    observacoes_rh = models.TextField(blank=True, help_text="Observações confidenciais do RH")

    #foto = models.ImageField(upload_to='funcionarios/fotos/', null=True, blank=True, default='https://res.cloudinary.com/drb9m2gwz/image/upload/v1762087442/logo_wovikm.png')
    foto = CloudinaryField('foto', blank=True, null=True)


    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='funcionarios')

    class Meta:
        verbose_name = "Funcionário"
        verbose_name_plural = "Funcionários"
        indexes = [
            models.Index(fields=['matricula']),
            models.Index(fields=['bi']),
            models.Index(fields=['nome_completo', 'empresa']),
            models.Index(fields=['empresa', 'ativo']),
            models.Index(fields=['cargo', 'ativo']),
            models.Index(fields=['loja_principal', 'ativo']),
            models.Index(fields=['data_admissao']),
        ]
        ordering = ['nome_completo']

    def __str__(self):
        return f"{self.matricula} - {self.nome_exibicao}"
    
    def gerar_matricula(self):
        """Gera matrícula sequencial segura por empresa"""
        from django.db import transaction

        with transaction.atomic():
            funcionarios = Funcionario.objects.select_for_update().filter(empresa=self.empresa)
            ultima = funcionarios.order_by('-id').first()

            if ultima and ultima.matricula:
                try:
                    numero = int(str(ultima.matricula).split('-')[-1]) + 1
                except ValueError:
                    numero = 1
            else:
                numero = 1

            return f"FUNC-{numero:05d}"



    def save(self, *args, **kwargs):
        criando = self._state.adding  # indica se é um registro novo

        # 1️⃣ Gera matrícula automaticamente se ainda não existir
        if not self.matricula:
            self.matricula = self.gerar_matricula()

        # 2️⃣ Sincroniza empresa do usuário
        if self.usuario and getattr(self.usuario, 'empresa', None) != self.empresa:
            self.usuario.empresa = self.empresa
            self.usuario.save(update_fields=['empresa'])

        # ⚠️ 3️⃣ Antes de salvar, valida apenas se for criação e cargo estiver vazio
        from django.core.exceptions import ValidationError

        if criando and not self.cargo:
            raise ValidationError({"cargo": "O campo 'cargo' é obrigatório ao criar o funcionário."})

        # 4️⃣ Salva o funcionário (isso já garante que o cargo_id seja persistido)
        super().save(*args, **kwargs)

        # 5️⃣ Após salvar, sincroniza grupo e permissões
        if self.usuario and self.cargo_id:
            group, _ = Group.objects.get_or_create(name=self.cargo.nome)
            if hasattr(self.cargo, "permissions"):
                group.permissions.set(self.cargo.permissions.all())

            self.usuario.groups.clear()
            self.usuario.groups.add(group)



    
    def clean(self):
        if self.data_demissao and self.data_demissao <= self.data_admissao:
            raise ValidationError("Data de demissão deve ser posterior à admissão")

    @property
    def nome_exibicao(self):
        return self.nome_completo

    @property
    def idade(self):
        hoje = date.today()
        return hoje.year - self.data_nascimento.year - (
            (hoje.month, hoje.day) < (self.data_nascimento.month, self.data_nascimento.day)
        )
    
    @property
    def permissoes_cargo(self):
        if not self.cargo:
            return {}
        return {k: getattr(self.cargo, k, False) for k in vars(self.cargo) if k.startswith('pode_')}


    @property
    def tempo_empresa_dias(self):
        fim = self.data_demissao or date.today()
        return (fim - self.data_admissao).days

    @property
    def tempo_empresa_anos(self):
        return self.tempo_empresa_dias / 365.25

    #@property
    #def ofa_vencido(self):
    #    if self.data_validade_ofa:
    #        return self.data_validade_ofa < date.today()
    #    return False

    @property
    def endereco_completo(self):
        partes = [
            f"{self.endereco}, {self.numero}",
            self.bairro,
            f"{self.cidade}/{self.provincia}",
            f"Postal: {self.postal}"
        ]
        return " - ".join(filter(None, partes))

    @property
    def salario_total(self):
        return sum([
            self.salario_atual or Decimal('0'),
            self.vale_alimentacao or Decimal('0'),
            self.vale_transporte or Decimal('0'),
            self.outros_beneficios or Decimal('0'),
        ])

    def pode_realizar_acao(self, acao, *args, **kwargs):
        """Valida se funcionário tem permissão baseada no cargo"""
        if not self.ativo:
            return False
        atributo = f'pode_{acao}'
        return getattr(self.cargo, atributo, False)

class Equipe(models.Model):
    nome = models.CharField(max_length=100) 

class EscalaTrabalho(TimeStampedModel):
    """Escalas de trabalho dos funcionários"""
    TURNO_CHOICES = [
        ('manha', 'Manhã'),
        ('tarde', 'Tarde'),
        ('noite', 'Noite'),
        ('madrugada', 'Madrugada'),
        ('integral', 'Integral'),
    ]
    
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='escalas')
    
    # Data e turno
    data_trabalho = models.DateField()
    turno = models.CharField(max_length=15, choices=TURNO_CHOICES)
    
    # Horários
    horario_entrada = models.TimeField()
    horario_saida = models.TimeField()
    horario_almoco_inicio = models.TimeField(null=True, blank=True)
    horario_almoco_fim = models.TimeField(null=True, blank=True)
    
    # Local
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    departamento = models.ForeignKey(Departamento, on_delete=models.CASCADE, null=True, blank=True)
    
    # Função específica do dia
    funcao_dia = models.CharField(max_length=100, blank=True, help_text="Função específica para este dia")
    
    # Status
    confirmada = models.BooleanField(default=False)
    trabalhada = models.BooleanField(default=False)
    observacoes = models.TextField(blank=True)
    
    # Quem criou a escala
    criada_por = models.ForeignKey(
        Funcionario, 
        on_delete=models.PROTECT,
        related_name='escalas_criadas'
    )
    
    class Meta:
        verbose_name = "Escala de Trabalho"
        verbose_name_plural = "Escalas de Trabalho"
        unique_together = ['funcionario', 'data_trabalho', 'turno']
        ordering = ['data_trabalho', 'turno', 'funcionario']
    
    def __str__(self):
        return f"{self.funcionario.nome_exibicao} - {self.data_trabalho} ({self.get_turno_display()})"
    
    @property
    def horas_trabalhadas(self):
        """Calcula horas trabalhadas no dia"""
        if not (self.horario_entrada and self.horario_saida):
            return 0
        
        entrada = datetime.combine(date.today(), self.horario_entrada)
        saida = datetime.combine(date.today(), self.horario_saida)
        
        # Se saída é menor que entrada, considera que passou da meia-noite
        if saida < entrada:
            saida += timedelta(days=1)
        
        total = saida - entrada
        
        # Descontar horário de almoço
        if self.horario_almoco_inicio and self.horario_almoco_fim:
            almoco_inicio = datetime.combine(date.today(), self.horario_almoco_inicio)
            almoco_fim = datetime.combine(date.today(), self.horario_almoco_fim)
            almoco_duracao = almoco_fim - almoco_inicio
            total -= almoco_duracao
        
        return total.total_seconds() / 3600  # Retorna em horas



class RegistroPonto(TimeStampedModel):
    """Registro de ponto dos funcionários"""
    TIPO_REGISTRO_CHOICES = [
        ('entrada', 'Entrada'),
        ('saida_almoco', 'Saída para Almoço'),
        ('volta_almoco', 'Volta do Almoço'),
        ('saida', 'Saída'),
        ('entrada_extra', 'Entrada Extra'),
        ('saida_extra', 'Saída Extra'),
    ]
    
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='registros_ponto')
    
    # Data e hora
    data_registro = models.DateField()
    hora_registro = models.TimeField()
    tipo_registro = models.CharField(max_length=15, choices=TIPO_REGISTRO_CHOICES)
    
    # Localização
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    ip_registro = models.GenericIPAddressField(null=True, blank=True)
    
    # Justificativa (para registros manuais)
    registro_manual = models.BooleanField(default=False)
    justificativa = models.TextField(blank=True)
    aprovado_por = models.ForeignKey(
        Funcionario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='pontos_aprovados'
    )
    
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Registro de Ponto"
        verbose_name_plural = "Registros de Ponto"
        ordering = ['-data_registro', '-hora_registro']
    
    def __str__(self):
        return f"{self.funcionario.nome_exibicao} - {self.data_registro} {self.hora_registro} ({self.get_tipo_registro_display()})"




class Ferias(TimeStampedModel):
    """Férias dos funcionários"""
    STATUS_CHOICES = [
        ('planejada', 'Planejada'),
        ('aprovada', 'Aprovada'),
        ('em_andamento', 'Em Andamento'),
        ('concluida', 'Concluída'),
        ('cancelada', 'Cancelada'),
    ]
    
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='ferias')
    
    # Período aquisitivo
    periodo_aquisitivo_inicio = models.DateField(help_text="Início do período aquisitivo")
    periodo_aquisitivo_fim = models.DateField(help_text="Fim do período aquisitivo")
    
    # Período de gozo
    data_inicio = models.DateField()
    data_fim = models.DateField()
    dias_ferias = models.IntegerField(help_text="Quantidade de dias de férias")
    
    # Valores
    valor_ferias = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_um_terco = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Adiantamento salarial
    adiantamento_13 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Status e aprovação
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='planejada')
    data_solicitacao = models.DateField(auto_now_add=True)
    aprovada_por = models.ForeignKey(
        Funcionario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='ferias_aprovadas'
    )
    data_aprovacao = models.DateField(null=True, blank=True)
    
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Férias"
        verbose_name_plural = "Férias"
        ordering = ['-data_inicio']
    
    def __str__(self):
        return f"{self.funcionario.nome_exibicao} - {self.data_inicio} a {self.data_fim}"
    
    def save(self, *args, **kwargs):
        # Calcular valores das férias
        if self.funcionario:
            salario_base = self.funcionario.salario_atual
            self.valor_ferias = (salario_base / 30) * self.dias_ferias
            self.valor_um_terco = self.valor_ferias / 3
            self.total = self.valor_ferias + self.valor_um_terco + self.adiantamento_13
        
        super().save(*args, **kwargs)
    
    @property
    def dias_calendario(self):
        """Total de dias de calendário"""
        return (self.data_fim - self.data_inicio).days + 1

class Capacitacao(TimeStampedModel):
    """Capacitações e treinamentos dos funcionários"""
    TIPO_CHOICES = [
        ('treinamento', 'Treinamento'),
        ('curso', 'Curso'),
        ('palestra', 'Palestra'),
        ('workshop', 'Workshop'),
        ('seminario', 'Seminário'),
        ('congresso', 'Congresso'),
        ('certificacao', 'Certificação'),
        ('reciclagem', 'Reciclagem'),
    ]
    
    STATUS_CHOICES = [
        ('planejada', 'Planejada'),
        ('inscrito', 'Inscrito'),
        ('em_andamento', 'Em Andamento'),
        ('concluida', 'Concluída'),
        ('cancelada', 'Cancelada'),
        ('reprovado', 'Reprovado'),
    ]
    
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='capacitacoes')
    
    # Dados da capacitação
    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    carga_horaria = models.IntegerField(help_text="Carga horária em horas")
    
    # Datas
    data_inicio = models.DateField()
    data_fim = models.DateField()
    data_inscricao = models.DateField(auto_now_add=True)
    
    # Instituição
    instituicao = models.CharField(max_length=200)
    instrutor = models.CharField(max_length=200, blank=True)
    local = models.CharField(max_length=200, blank=True)
    modalidade = models.CharField(max_length=20, choices=[
        ('presencial', 'Presencial'),
        ('online', 'Online'),
        ('hibrido', 'Híbrido'),
        ('ead', 'EAD'),
    ], default='presencial')
    
    # Custos
    valor_inscricao = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_transporte = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_hospedagem = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_alimentacao = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Resultado
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='planejada')
    nota_final = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    certificado = models.FileField(upload_to='funcionarios/certificados/', null=True, blank=True)
    
    # Aprovação
    aprovada_por = models.ForeignKey(
        Funcionario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='capacitacoes_aprovadas'
    )
    
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Capacitação"
        verbose_name_plural = "Capacitações"
        ordering = ['-data_inicio']
    
    def __str__(self):
        return f"{self.funcionario.nome_exibicao} - {self.titulo}"
    
    def save(self, *args, **kwargs):
        # Calcular valor total
        self.total = (
            self.valor_inscricao + 
            self.valor_transporte + 
            self.valor_hospedagem + 
            self.valor_alimentacao
        )
        super().save(*args, **kwargs)

class AvaliacaoDesempenho(TimeStampedModel):
    """Avaliações de desempenho dos funcionários"""
    PERIODO_CHOICES = [
        ('experiencia', 'Período de Experiência'),
        ('anual', 'Avaliação Anual'),
        ('semestral', 'Avaliação Semestral'),
        ('promocao', 'Avaliação para Promoção'),
        ('extraordinaria', 'Avaliação Extraordinária'),
    ]
    
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='avaliacoes')
    
    # Período da avaliação
    tipo_avaliacao = models.CharField(max_length=15, choices=PERIODO_CHOICES)
    periodo_inicio = models.DateField()
    periodo_fim = models.DateField()
    data_avaliacao = models.DateField()
    
    # Avaliador
    avaliador = models.ForeignKey(
        Funcionario, 
        on_delete=models.PROTECT,
        related_name='avaliacoes_realizadas'
    )
    
    # Critérios de avaliação (notas de 1 a 5)
    pontualidade = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    assiduidade = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    qualidade_trabalho = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    produtividade = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    iniciativa = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    relacionamento_interpessoal = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    conhecimento_tecnico = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    lideranca = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], null=True, blank=True)
    
    # Média geral
    nota_geral = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    
    # Comentários
    pontos_fortes = models.TextField()
    pontos_melhorar = models.TextField()
    metas_objetivos = models.TextField()
    plano_desenvolvimento = models.TextField(blank=True)
    
    # Recomendações
    recomenda_promocao = models.BooleanField(default=False)
    recomenda_aumento = models.BooleanField(default=False)
    recomenda_capacitacao = models.BooleanField(default=False)
    
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Avaliação de Desempenho"
        verbose_name_plural = "Avaliações de Desempenho"
        ordering = ['-data_avaliacao']
    
    def __str__(self):
        return f"{self.funcionario.nome_exibicao} - {self.get_tipo_avaliacao_display()} - {self.data_avaliacao}"
    
    def save(self, *args, **kwargs):
        # Calcular nota geral
        notas = [
            self.pontualidade, self.assiduidade, self.qualidade_trabalho,
            self.produtividade, self.iniciativa, self.relacionamento_interpessoal,
            self.conhecimento_tecnico
        ]
        
        if self.lideranca:
            notas.append(self.lideranca)
        
        self.nota_geral = sum(notas) / len(notas)
        super().save(*args, **kwargs)

class JornadaTrabalho(models.Model):
    """Horários padrões de trabalho, utilizados para gerar Escalas"""
    nome = models.CharField(max_length=100, unique=True)
    turno = models.CharField(
        max_length=15,
        choices=[
            ('manha', 'Manhã'),
            ('tarde', 'Tarde'),
            ('noite', 'Noite'),
            ('madrugada', 'Madrugada'),
            ('integral', 'Integral'),
        ]
    )
    horario_entrada = models.TimeField()
    horario_saida = models.TimeField()
    horario_almoco_inicio = models.TimeField(null=True, blank=True)
    horario_almoco_fim = models.TimeField(null=True, blank=True)
    departamento = models.ForeignKey(Departamento, on_delete=models.SET_NULL, null=True, blank=True)
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Jornada de Trabalho"
        verbose_name_plural = "Jornadas de Trabalho"
        ordering = ['nome', 'turno']

    def __str__(self):
        return f"{self.nome} ({self.get_turno_display()})"

    def criar_escala(self, funcionario, data_trabalho, funcao_dia='', criada_por=None):
        """
        Cria uma EscalaTrabalho baseada nesta jornada.
        Não altera a EscalaTrabalho existente.
        """
        from apps.funcionarios.models import EscalaTrabalho

        escala = EscalaTrabalho.objects.create(
            funcionario=funcionario,
            data_trabalho=data_trabalho,
            turno=self.turno,
            horario_entrada=self.horario_entrada,
            horario_saida=self.horario_saida,
            horario_almoco_inicio=self.horario_almoco_inicio,
            horario_almoco_fim=self.horario_almoco_fim,
            departamento=self.departamento,
            loja=self.loja,
            funcao_dia=funcao_dia,
            criada_por=criada_por or funcionario,
        )
        return escala

class Afastamento(TimeStampedModel):
    """Registra afastamentos de funcionários (férias, licenças, etc.)"""

    TIPO_CHOICES = [
        ('ferias', 'Férias'),
        ('doenca', 'Doença'),
        ('maternidade', 'Maternidade'),
        ('paternidade', 'Paternidade'),
        ('outra', 'Outro'),
    ]

    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name='afastamentos'
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    data_inicio = models.DateField()
    data_fim = models.DateField()
    descricao = models.TextField(blank=True, help_text="Motivo ou observações adicionais")
    
    # Aprovação (opcional)
    aprovado_por = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='afastamentos_aprovados'
    )
    aprovado = models.BooleanField(default=False)
    
    # Localização/Departamento (opcional)
    loja = models.ForeignKey(
        Loja,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='afastamentos'
    )
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='afastamentos'
    )

    class Meta:
        verbose_name = "Afastamento"
        verbose_name_plural = "Afastamentos"
        ordering = ['-data_inicio', 'funcionario']

    def __str__(self):
        return f"{self.funcionario.nome_exibicao} - {self.get_tipo_display()} ({self.data_inicio} a {self.data_fim})"

    @property
    def duracao_dias(self):
        """Retorna a duração do afastamento em dias"""
        return (self.data_fim - self.data_inicio).days + 1

class Beneficio(TimeStampedModel):
    """Benefícios dos funcionários, como VT, VR, plano de saúde, etc."""

    TIPO_CHOICES = [
        ('vale_transporte', 'Vale Transporte'),
        ('vale_refeicao', 'Vale Refeição'),
        ('plano_saude', 'Plano de Saúde'),
        ('outro', 'Outro'),
    ]

    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name='beneficios'
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Benefício"
        verbose_name_plural = "Benefícios"
        ordering = ['funcionario', 'tipo']

    def __str__(self):
        return f"{self.funcionario.nome_exibicao} - {self.get_tipo_display()} ({self.valor})"

class PontoEletronico(TimeStampedModel):
    """
    Regista as marcações de ponto diárias de um funcionário.
    """
    STATUS_CHOICES = [
        ('presente', 'Presente'),
        ('falta', 'Falta'),
        ('falta_justificada', 'Falta Justificada'),
        ('ferias', 'Férias'),
        ('feriado', 'Feriado'),
    ]

    # --- Relações e Identificação ---
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='pontos')
    data = models.DateField("Data", default=timezone.now)

    # --- Marcações de Ponto ---
    entrada_manha = models.TimeField("Entrada Manhã", null=True, blank=True)
    saida_almoco = models.TimeField("Saída Almoço", null=True, blank=True)
    entrada_tarde = models.TimeField("Entrada Tarde", null=True, blank=True)
    saida = models.TimeField("Saída", null=True, blank=True)
    
    # --- Controlo e Auditoria ---
    status = models.CharField("Status do Dia", max_length=20, choices=STATUS_CHOICES, default='presente')
    observacoes = models.TextField("Observações / Justificativa", blank=True)

    class Meta:
        verbose_name = "Registo de Ponto"
        verbose_name_plural = "Registos de Ponto"
        # Garante que só existe um registo de ponto por funcionário por dia
        unique_together = ('funcionario', 'data')
        ordering = ['-data', 'funcionario']

    def __str__(self):
        return f"Ponto de {self.funcionario} em {self.data.strftime('%d/%m/%Y')}"

    # --- Propriedades Calculadas (Lógica de Negócio) ---
    
    def _calcular_duracao(self, inicio, fim):
        """Função auxiliar para calcular a duração entre dois horários no mesmo dia."""
        if not inicio or not fim:
            return timezone.timedelta(0)
        
        datetime_inicio = datetime.combine(self.data, inicio)
        datetime_fim = datetime.combine(self.data, fim)
        return datetime_fim - datetime_inicio

    @property
    def horas_periodo_manha(self):
        return self._calcular_duracao(self.entrada_manha, self.saida_almoco)
        
    @property
    def horas_periodo_tarde(self):
        return self._calcular_duracao(self.entrada_tarde, self.saida)
        
    @property
    def horas_almoco(self):
        return self._calcular_duracao(self.saida_almoco, self.entrada_tarde)
        
    @property
    def horas_trabalhadas_dia(self):
        """Calcula o total de horas trabalhadas no dia."""
        total = self.horas_periodo_manha + self.horas_periodo_tarde
        return total if total.total_seconds() > 0 else timezone.timedelta(0)

class Formacao(models.Model):
    funcionario = models.OneToOneField(Funcionario, on_delete=models.CASCADE, related_name="funcionario")
    especialidade_principal = models.CharField(max_length=100, blank=True)
    curso = models.CharField(max_length=150)
    titulo = models.CharField(max_length=150)
    instituicao = models.CharField(max_length=150)
    ano_conclusao = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.funcionario.nome_exibicao} | {self.titulo} - {self.instituicao}"

class ResponsabilidadeTecnica(models.Model):
    responsabilidade = models.ForeignKey(Cargo, on_delete=models.CASCADE, related_name="responsabilidades")
    estabelecimento = models.CharField(max_length=200)
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.estabelecimento} ({self.responsabilidade})"

class Meta(models.Model):
    funcionario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="metas",
        verbose_name="Funcionário"
    )
    titulo = models.CharField(max_length=200, verbose_name="Título da Meta")
    descricao = models.TextField(blank=True, null=True, verbose_name="Descrição")
    data_inicio = models.DateField(default=timezone.now, verbose_name="Data de Início")
    data_fim = models.DateField(verbose_name="Data Limite")
    concluida = models.BooleanField(default=False, verbose_name="Concluída")
    progresso = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.00,
        verbose_name="Progresso (%)"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Meta"
        verbose_name_plural = "Metas"
        ordering = ["-data_fim"]

    def __str__(self):
        return f"{self.titulo} - {self.funcionario}"
    
    def esta_atrasada(self):
        """Verifica se a meta está atrasada"""
        return not self.concluida and timezone.now().date() > self.data_fim

class ProcessoSeletivo(models.Model):
    titulo = models.CharField(max_length=255, verbose_name="Título")
    descricao = models.TextField(blank=True, null=True, verbose_name="Descrição")
    data_inicio = models.DateField(default=timezone.now, verbose_name="Data de Início")
    data_fim = models.DateField(blank=True, null=True, verbose_name="Data de Encerramento")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Processo Seletivo"
        verbose_name_plural = "Processos Seletivos"
        ordering = ["-data_inicio"]

    def __str__(self):
        return self.titulo

    def em_andamento(self):
        """Retorna True se o processo ainda estiver ativo e dentro da data limite"""
        hoje = timezone.now().date()
        return self.ativo and (not self.data_fim or hoje <= self.data_fim)

class Candidato(models.Model):
    nome = models.CharField(max_length=200, verbose_name="Nome Completo")
    email = models.EmailField(unique=True, verbose_name="E-mail")
    telefone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefone")
    curriculo = models.FileField(upload_to="curriculos/", blank=True, null=True, verbose_name="Currículo")
    experiencia = models.TextField(blank=True, null=True, verbose_name="Experiência Profissional")
    formacao = models.TextField(blank=True, null=True, verbose_name="Formação Acadêmica")

    processo = models.ForeignKey(
        ProcessoSeletivo,
        on_delete=models.CASCADE,
        related_name="candidatos",
        verbose_name="Processo Seletivo"
    )

    STATUS_CHOICES = [
        ("analise", "Em Análise"),
        ("entrevista", "Entrevista"),
        ("aprovado", "Aprovado"),
        ("reprovado", "Reprovado"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="analise")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Candidato"
        verbose_name_plural = "Candidatos"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.get_status_display()})"

class Comunicado(models.Model):
    titulo = models.CharField(max_length=200)
    mensagem = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comunicados"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.titulo

class FolhaPagamento(TimeStampedModel):
    """Folha de pagamento mensal"""
    
    STATUS_CHOICES = [
        ('em_elaboracao', 'Em Elaboração'),
        ('calculada', 'Calculada'),
        ('aprovada', 'Aprovada'),
        ('fechada', 'Fechada'),
        ('paga', 'Paga'),
        ('cancelada', 'Cancelada'),
    ]
    
    # Identificação
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='folhas_pagamento')
    mes = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    ano = models.IntegerField(validators=[MinValueValidator(2020), MaxValueValidator(2050)])
    
    # Dados da folha
    descricao = models.CharField(max_length=200, help_text="Ex: Folha Janeiro 2024")
    data_fechamento = models.DateField(null=True, blank=True)
    data_pagamento = models.DateField(null=True, blank=True)
    
    # Status e controle
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='em_elaboracao')
    
    # Totalizadores
    total_funcionarios = models.IntegerField(default=0)
    total_salario_bruto = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_descontos = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_beneficios = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_liquido = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_inss_empresa = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_fgts = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Responsáveis
    elaborada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT,
        related_name='folhas_elaboradas'
    )
    aprovada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL,
        null=True, 
        blank=True,
        related_name='folhas_aprovadas'
    )
    
    # Observações
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Folha de Pagamento'
        verbose_name_plural = 'Folhas de Pagamento'
        unique_together = ['empresa', 'mes', 'ano']
        ordering = ['-ano', '-mes']
        
    def __str__(self):
        return f"Folha {self.mes:02d}/{self.ano} - {self.empresa.nome}"
    
    @property
    def mes_nome(self):
        """Retorna o nome do mês"""
        meses = [
            '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
            'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
        ]
        return meses[self.mes]
    
    @property
    def pode_editar(self):
        """Verifica se a folha pode ser editada"""
        return self.status in ['em_elaboracao', 'calculada']
    
    @property
    def pode_aprovar(self):
        """Verifica se a folha pode ser aprovada"""
        return self.status == 'calculada'
    
    @property
    def pode_fechar(self):
        """Verifica se a folha pode ser fechada"""
        return self.status == 'aprovada'
    
    def calcular_folha(self):
        """Calcula todos os valores da folha"""
        if not self.pode_editar:
            raise ValidationError("Folha não pode ser recalculada neste status")
        
        # Resetar totalizadores
        self.total_funcionarios = 0
        self.total_salario_bruto = Decimal('0.00')
        self.total_descontos = Decimal('0.00')
        self.total_beneficios = Decimal('0.00')
        self.total_liquido = Decimal('0.00')
        self.total_inss_empresa = Decimal('0.00')
        self.total_fgts = Decimal('0.00')
        
        # Calcular cada item da folha
        for item in self.itens.all():
            item.calcular()
            
            # Somar aos totalizadores
            self.total_funcionarios += 1
            self.total_salario_bruto += item.salario_bruto
            self.total_descontos += item.total_descontos
            self.total_beneficios += item.total_beneficios
            self.total_liquido += item.salario_liquido
            self.total_inss_empresa += item.inss_empresa
            self.total_fgts += item.fgts
        
        self.status = 'calculada'
        self.save()
    
    def aprovar_folha(self, usuario):
        """Aprova a folha de pagamento"""
        if not self.pode_aprovar:
            raise ValidationError("Folha não pode ser aprovada neste status")
        
        self.status = 'aprovada'
        self.aprovada_por = usuario
        self.save()
    
    def fechar_folha(self):
        """Fecha a folha de pagamento"""
        if not self.pode_fechar:
            raise ValidationError("Folha não pode ser fechada neste status")
        
        self.status = 'fechada'
        self.data_fechamento = date.today()
        self.save()
    
    def marcar_como_paga(self, data_pagamento=None):
        """Marca a folha como paga"""
        if self.status != 'fechada':
            raise ValidationError("Apenas folhas fechadas podem ser marcadas como pagas")
        
        self.status = 'paga'
        self.data_pagamento = data_pagamento or date.today()
        self.save()

class ItemFolhaPagamento(TimeStampedModel):
    """Item individual da folha de pagamento por funcionário"""
    
    folha = models.ForeignKey(FolhaPagamento, on_delete=models.CASCADE, related_name='itens')
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE)
    
    # Dados base para cálculo
    salario_base = models.DecimalField(max_digits=10, decimal_places=2)
    dias_trabalhados = models.IntegerField(default=30)
    dias_uteis_mes = models.IntegerField(default=22)
    horas_extras = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    valor_hora_extra = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Proventos
    salario_bruto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_horas_extras = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adicional_noturno = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adicional_insalubridade = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adicional_periculosidade = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    comissoes = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    outros_proventos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Descontos
    inss_funcionario = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    irrf = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vale_transporte = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vale_refeicao = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    plano_saude = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adiantamentos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    faltas = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    outros_descontos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Encargos do empregador
    inss_empresa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fgts = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Totalizadores calculados
    total_proventos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_descontos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_beneficios = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    salario_liquido = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Observações específicas
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Item da Folha de Pagamento'
        verbose_name_plural = 'Itens da Folha de Pagamento'
        unique_together = ['folha', 'funcionario']
        ordering = ['funcionario__nome_completo']
        
    def __str__(self):
        return f"{self.funcionario.nome_completo} - {self.folha}"
    
    def calcular(self):
        """Calcula todos os valores do item"""
        
        # 1. Calcular salário proporcional
        if self.dias_trabalhados < 30:
            self.salario_bruto = (self.salario_base / 30) * self.dias_trabalhados
        else:
            self.salario_bruto = self.salario_base
        
        # 2. Calcular horas extras
        if self.horas_extras > 0 and self.valor_hora_extra > 0:
            self.valor_horas_extras = self.horas_extras * self.valor_hora_extra
        
        # 3. Calcular total de proventos
        self.total_proventos = (
            self.salario_bruto +
            self.valor_horas_extras +
            self.adicional_noturno +
            self.adicional_insalubridade +
            self.adicional_periculosidade +
            self.comissoes +
            self.bonus +
            self.outros_proventos
        )
        
        # 4. Calcular INSS do funcionário
        self.inss_funcionario = self.calcular_inss()
        
        # 5. Calcular IRRF
        self.irrf = self.calcular_irrf()
        
        # 6. Calcular total de descontos
        self.total_descontos = (
            self.inss_funcionario +
            self.irrf +
            self.vale_transporte +
            self.adiantamentos +
            self.faltas +
            self.outros_descontos
        )
        
        # 7. Calcular benefícios (não descontados)
        self.total_beneficios = (
            self.vale_refeicao +
            self.plano_saude
        )
        
        # 8. Calcular salário líquido
        self.salario_liquido = self.total_proventos - self.total_descontos
        
        # 9. Calcular encargos do empregador
        self.inss_empresa = self.total_proventos * Decimal('0.20')  # 20% INSS empresa
        self.fgts = self.total_proventos * Decimal('0.08')  # 8% FGTS
        
        self.save()
    
    def calcular_inss(self):
        """Calcula o INSS do funcionário baseado na tabela atual"""
        salario = self.total_proventos
        
        # Tabela INSS 2024 (valores de exemplo - ajustar conforme legislação)
        if salario <= Decimal('1412.00'):
            return salario * Decimal('0.075')  # 7.5%
        elif salario <= Decimal('2666.68'):
            return salario * Decimal('0.09')   # 9%
        elif salario <= Decimal('4000.03'):
            return salario * Decimal('0.12')   # 12%
        elif salario <= Decimal('7786.02'):
            return salario * Decimal('0.14')   # 14%
        else:
            return Decimal('1089.72')  # Teto do INSS
    
    def calcular_irrf(self):
        """Calcula o IRRF baseado na tabela atual"""
        base_calculo = self.total_proventos - self.inss_funcionario
        
        # Dedução por dependente (valor de exemplo)
        deducao_dependentes = Decimal('189.59') * 0  # Assumindo 0 dependentes
        base_calculo -= deducao_dependentes
        
        # Tabela IRRF 2024 (valores de exemplo - ajustar conforme legislação)
        if base_calculo <= Decimal('2112.00'):
            return Decimal('0.00')  # Isento
        elif base_calculo <= Decimal('2826.65'):
            return (base_calculo * Decimal('0.075')) - Decimal('158.40')
        elif base_calculo <= Decimal('3751.05'):
            return (base_calculo * Decimal('0.15')) - Decimal('370.40')
        elif base_calculo <= Decimal('4664.68'):
            return (base_calculo * Decimal('0.225')) - Decimal('651.73')
        else:
            return (base_calculo * Decimal('0.275')) - Decimal('884.96')

class EventoFolha(TimeStampedModel):
    """Eventos específicos que afetam a folha de pagamento"""
    
    TIPO_EVENTO_CHOICES = [
        ('bonus', 'Bônus'),
        ('comissao', 'Comissão'),
        ('desconto', 'Desconto'),
        ('adiantamento', 'Adiantamento'),
        ('horas_extras', 'Horas Extras'),
        ('falta', 'Falta'),
        ('licenca', 'Licença'),
        ('ferias', 'Férias'),
        ('decimo_terceiro', '13º Salário'),
        ('outro', 'Outro'),
    ]
    
    item_folha = models.ForeignKey(ItemFolhaPagamento, on_delete=models.CASCADE, related_name='eventos')
    tipo_evento = models.CharField(max_length=20, choices=TIPO_EVENTO_CHOICES)
    descricao = models.CharField(max_length=200)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    quantidade = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    data_evento = models.DateField()
    
    # Controle
    aplicado = models.BooleanField(default=False)
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Evento da Folha'
        verbose_name_plural = 'Eventos da Folha'
        ordering = ['data_evento']
        
    def __str__(self):
        return f"{self.get_tipo_evento_display()} - {self.item_folha.funcionario.nome_completo}"
    
    @property
    def total(self):
        return self.valor * self.quantidade

class HistoricoSalarial(TimeStampedModel):
    """Histórico de alterações salariais"""
    
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='historico_salarial')
    salario_anterior = models.DecimalField(max_digits=10, decimal_places=2)
    salario_novo = models.DecimalField(max_digits=10, decimal_places=2)
    data_vigencia = models.DateField()
    motivo = models.CharField(max_length=200)
    observacoes = models.TextField(blank=True)
    
    # Responsável pela alteração
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )
    
    class Meta:
        verbose_name = 'Histórico Salarial'
        verbose_name_plural = 'Históricos Salariais'
        ordering = ['-data_vigencia']
        
    def __str__(self):
        return f"{self.funcionario.nome_completo} - {self.data_vigencia}"
    
    @property
    def percentual_aumento(self):
        if self.salario_anterior > 0:
            return ((self.salario_novo - self.salario_anterior) / self.salario_anterior) * 100
        return 0


class FechamentoTurno(TimeStampedModel):
    """Registro de fechamento de turno do funcionário"""
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='fechamentos_turno')
    data_fechamento = models.DateTimeField(default=timezone.now)
    
    # Valores informados pelo usuário
    valor_informado_caixa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_informado_tpa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_informado_transferencia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Valores calculados pelo sistema
    valor_sistema_caixa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_sistema_tpa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_sistema_transferencia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Fechamento de Turno"
        verbose_name_plural = "Fechamentos de Turno"
        ordering = ['-data_fechamento']
        
    def __str__(self):
        return f"Fechamento {self.funcionario.nome_exibicao} - {self.data_fechamento.strftime('%d/%m/%Y %H:%M')}"
    
    @property
    def diferenca_caixa(self):
        return self.valor_informado_caixa - self.valor_sistema_caixa
        
    @property
    def diferenca_tpa(self):
        return self.valor_informado_tpa - self.valor_sistema_tpa
        
    @property
    def diferenca_transferencia(self):
        return self.valor_informado_transferencia - self.valor_sistema_transferencia
        
    @property
    def total_informado(self):
        return self.valor_informado_caixa + self.valor_informado_tpa + self.valor_informado_transferencia
        
    @property
    def total_sistema(self):
        return self.valor_sistema_caixa + self.valor_sistema_tpa + self.valor_sistema_transferencia
        
    @property
    def diferenca_total(self):
        return self.total_informado - self.total_sistema

