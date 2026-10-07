"""Scan do estado actual do PLANO_IMPLEMENTACAO.md v5.0"""
from pathlib import Path

def r(p):
    try: return Path(p).read_text(encoding='utf-8', errors='ignore')
    except: return ''

def ex(p):
    return Path(p).exists()

checks = {
    # ── SECÇÃO 1 — Infra ──────────────────────────────────────────────
    'S1.1 iniciar_infra.ps1 comentado':        'Bug 6' in r('iniciar_infra.ps1') or 'Celery Worker' in r('iniciar_infra.ps1'),
    'S1.2 iniciar_infra.sh Linux':             ex('iniciar_infra.sh'),
    'S1.3 Procfile':                           ex('Procfile'),
    'S1.4 check_settings.py melhorado':        'AGT_SOFTWARE_PRIVATE_KEY_PEM' in r('check_settings.py'),
    'S1.5 auditar_integridade.py 7 passos':    'PASSO 7' in r('auditar_integridade.py'),
    'S1.6 gerenciar_sotarq bugs corrigidos':   'Bug 1 corrigido' in r('gerenciar_sotarq.py'),
    'S1.7 gerenciar opcao 6 (migracoes)':      'aplicar_migracoes_tenant' in r('gerenciar_sotarq.py'),
    'S1.8 gerenciar opcao 12-15':              'listar_dominios' in r('gerenciar_sotarq.py'),

    # ── SECÇÃO 2 — Migrações ──────────────────────────────────────────
    'S2.1 migr fiscal 0003':                   ex('apps/fiscal/migrations/0003_assinaturadigital_campos_v2.py'),
    'S2.2 migr fiscal 0004 eac_code':          ex('apps/fiscal/migrations/0004_documentofiscal_eac_code.py'),
    'S2.3 migr fiscal 0005 seriefiscalagt':    ex('apps/fiscal/migrations/0005_seriefiscalagt.py'),
    'S2.4 migr fiscal 0006 imutabilidade':     ex('apps/fiscal/migrations/0006_documentofiscal_imutabilidade.py'),
    'S2.5 migr vendas 0002 onetone':           ex('apps/vendas/migrations/0002_fase2_documento_fiscal_onetone.py'),
    'S2.6 migr vendas 0003 certificacao':      ex('apps/vendas/migrations/0003_campos_certificacao_agt.py'),
    'S2.7 migr vendas 0004 proxies GF AF':     ex('apps/vendas/migrations/0004_faturaGenerica_faturaAutofacturacao_proxy.py'),
    'S2.8 migr empresas 0002 regime_fiscal':   ex('apps/empresas/migrations/0002_empresa_regime_fiscal.py'),

    # ── SECÇÃO 3 — Imutabilidade ──────────────────────────────────────
    'S3.1 CAMPOS_FISCAIS_IMUTAVEIS':           'CAMPOS_FISCAIS_IMUTAVEIS' in r('apps/fiscal/models.py'),
    'S3.2 documento_original FK':              'documento_original' in r('apps/fiscal/models.py'),
    'S3.3 campo comentarios DocFiscal':        'comentarios = models.TextField' in r('apps/fiscal/models.py'),
    'S3.4 motivo_cancelamento_codigo DocFiscal': 'motivo_cancelamento_codigo' in r('apps/fiscal/models.py'),
    'S3.5 _skip_immutability_check no save':   '_skip_immutability_check' in r('apps/fiscal/models.py'),
    'S3.6 lancar_documento method':            'def lancar_documento' in r('apps/fiscal/models.py'),
    'S3.7 rectificar_documento method':        'def rectificar_documento' in r('apps/fiscal/models.py'),
    'S3.8 DocumentoFiscalService':             ex('apps/fiscal/services/documento_fiscal_service.py'),
    'S3.9 DocumentoFiscalSerializer':          'DocumentoFiscalSerializer' in r('apps/fiscal/serializers.py'),
    'S3.10 DocumentoFiscalViewSet':            'DocumentoFiscalViewSet' in r('apps/fiscal/views.py'),
    'S3.11 router documentos-fiscais':         'documentos-fiscais' in r('apps/fiscal/urls.py'),
    'S3.12 IRPS sem bloqueio (choices.py)':    'TIPO_RETENCAO_DATA_VIGOR' not in r('apps/core/choices.py'),
    'S3.13 auditoria _registar_auditoria':     '_registar_auditoria_documento' in r('apps/fiscal/models.py'),

    # ── SECÇÃO 4 — PDF Redesign ───────────────────────────────────────
    'S4.1 PDFDocumentoService aceita doc_fiscal': 'documento_fiscal=None' in r('apps/fiscal/services/pdf_agt_service.py'),
    'S4.2 operation_type no PDF':              '_operation_type_label' in r('apps/fiscal/services/pdf_agt_service.py'),
    'S4.3 regime_fiscal no PDF':               'regime_fiscal' in r('apps/fiscal/services/pdf_agt_service.py'),
    'S4.4 comentarios no PDF':                 '_comentarios' in r('apps/fiscal/services/pdf_agt_service.py'),
    'S4.5 marca dagua ANULADO':                '_marca_dagua_anulado' in r('apps/fiscal/services/pdf_agt_service.py'),
    'S4.6 QR logo 18%':                        '0.18' in r('apps/fiscal/services/pdf_agt_service.py'),
    'S4.7 periodo contabilistico no PDF':      '_periodo' in r('apps/fiscal/services/pdf_agt_service.py'),
    'S4.8 rodape legal correcto':              '_rodape_legal' in r('apps/fiscal/services/pdf_agt_service.py'),
    'S4.9 Empresa.regime_fiscal campo novo':   'regime_fiscal' in r('apps/empresas/models.py'),
    'S4.10 Empresa.regime label corrigido':    'Tipo de Actividade' in r('apps/empresas/models.py'),

    # ── SECÇÃO 5 — Documentos homologação (estrutura de código) ──────
    'S5.1 FaturaGenerica proxy':               'class FaturaGenerica' in r('apps/vendas/models.py'),
    'S5.2 FaturaAutofacturacao proxy':         'class FaturaAutofacturacao' in r('apps/vendas/models.py'),
    'S5.3 SAFTValidarXSDView':                 'SAFTValidarXSDView' in r('apps/fiscal/views.py'),
    'S5.4 SaftValidacaoService':               ex('apps/fiscal/services/saft_validacao_service.py'),
    'S5.5 SerieFiscalAGT model':               'class SerieFiscalAGT' in r('apps/fiscal/models.py'),
    'S5.6 SerieFiscalService':                 ex('apps/fiscal/services/serie_fiscal_service.py'),

    # ── SECÇÃO 6 — Portal de Parceiros ───────────────────────────────
    'S6.1 app parceiros __init__':             ex('apps/parceiros/__init__.py'),
    'S6.2 app parceiros apps.py':              ex('apps/parceiros/apps.py'),
    'S6.3 Partner model':                      'class Partner' in r('apps/parceiros/models.py'),
    'S6.4 PartnerLicensePlan model':           'class PartnerLicensePlan' in r('apps/parceiros/models.py'),
    'S6.5 PartnerLicense model':               'class PartnerLicense' in r('apps/parceiros/models.py'),
    'S6.6 PartnerToken model (hash)':          'token_hash' in r('apps/parceiros/models.py'),
    'S6.7 PartnerClient model':                'class PartnerClient' in r('apps/parceiros/models.py'),
    'S6.8 PartnerQuotaUsage model':            'class PartnerQuotaUsage' in r('apps/parceiros/models.py'),
    'S6.9 PartnerBilling model':               'class PartnerBilling' in r('apps/parceiros/models.py'),
    'S6.10 PartnerAudit model':                'class PartnerAudit' in r('apps/parceiros/models.py'),
    'S6.11 PartnerService services.py':        ex('apps/parceiros/services.py'),
    'S6.12 PartnerService quota select_for_update': 'select_for_update' in r('apps/parceiros/services.py'),
    'S6.13 views.py portal parceiro':          ex('apps/parceiros/views.py'),
    'S6.14 urls.py parceiros':                 ex('apps/parceiros/urls.py'),
    'S6.15 admin.py parceiros':                ex('apps/parceiros/admin.py'),
    'S6.16 migration 0001_initial parceiros':  ex('apps/parceiros/migrations/0001_initial.py'),
    'S6.17 pode_gerir_parceiros em Cargo':     'pode_gerir_parceiros' in r('apps/funcionarios/models.py'),
    'S6.18 mgmt commands parceiros':           ex('apps/parceiros/management/commands/criar_partner.py'),
    'S6.19 parceiros em SHARED_APPS':          'apps.parceiros' in r('config/settings/base.py'),
    'S6.20 urls_public.py com parceiros':      'parceiros' in r('config/urls_public.py'),
}

ok   = [k for k,v in checks.items() if v]
fail = [k for k,v in checks.items() if not v]

print('='*60)
print(f'SCAN PLANO_IMPLEMENTACAO.md v5.0')
print(f'Implementado: {len(ok)}/{len(checks)}  |  Falta: {len(fail)}')
print('='*60)

if ok:
    print(f'\n[x] CONCLUÍDO ({len(ok)}):')
    for k in ok: print(f'    [x] {k}')

if fail:
    print(f'\n[ ] FALTA ({len(fail)}):')
    for k in fail: print(f'    [ ] {k}')
