BEGIN;

-- 1. IDENTIFICAÇÃO DO SCHEMA (Substitua se necessário)
-- Assumindo que o schema é 'mundo_e_maquinas' e o Usuário ID é 10

-- 2. CARGO ADMINISTRADOR: Ativando todas as permissões de negócio
-- Baseado no seu model Cargo, marcamos todos os privilégios como TRUE
UPDATE mundo_e_maquinas.funcionarios_cargo
SET 
    selecionar_todos = TRUE,
    pode_estornar_pagamento = TRUE,
    pode_pagar_salario = TRUE,
    pode_vender = TRUE,
    pode_ver_vendas = TRUE,
    pode_fazer_desconto = TRUE,
    limite_desconto_percentual = 100.00,
    pode_cancelar_venda = TRUE,
    pode_fazer_devolucao = TRUE,
    pode_alterar_preco = TRUE,
    pode_emitir_notacredito = TRUE,
    pode_aplicar_notacredito = TRUE,
    pode_aprovar_notacredito = TRUE,
    pode_emitir_notadebito = TRUE,
    pode_aplicar_notadebito = TRUE,
    pode_aprovar_notadebito = TRUE,
    pode_emitir_documentotransporte = TRUE,
    pode_confirmar_entrega = TRUE,
    pode_gerenciar_estoque = TRUE,
    pode_fazer_compras = TRUE,
    pode_aprovar_pedidos = TRUE,
    pode_gerenciar_funcionarios = TRUE,
    pode_editar_produtos = TRUE,
    pode_emitir_faturacredito = TRUE,
    pode_liquidar_faturacredito = TRUE,
    pode_emitir_proforma = TRUE,
    pode_aprovar_proforma = TRUE,
    pode_emitir_recibo = TRUE,
    pode_acessar_documentos = TRUE,
    pode_acessar_rh = TRUE,
    pode_acessar_financeiro = TRUE,
    pode_acessar_fornecedores = TRUE,
    pode_alterar_dados_fiscais = TRUE,
    pode_eliminar_detalhes_fiscal = TRUE,
    pode_acessar_detalhes_fiscal = TRUE,
    pode_fazer_backup_manual = TRUE,
    pode_ver_configuracoes = TRUE,
    pode_atualizar_backups = TRUE,
    pode_alterar_interface = TRUE,
    pode_acessar_configuracoes = TRUE,
    pode_exportar_saft = TRUE,
    pode_ver_historico_saft = TRUE,
    pode_baixar_saft = TRUE,
    pode_validar_saft = TRUE,
    pode_visualizar_saft = TRUE,
    pode_ver_status_saft = TRUE,
    pode_ver_taxaiva_agt = TRUE,
    pode_gerir_assinatura_digital = TRUE,
    pode_gerir_retencoes_na_fonte = TRUE,
    pode_acessar_dashboard_fiscal = TRUE,
    pode_acessar_painel_principal_fiscal = TRUE,
    pode_verificar_integridade_hash = TRUE,
    pode_acessar_configuracao_fiscal = TRUE,
    pode_verificar_integridade_cadeia_hash_fiscal = TRUE
WHERE nome ILIKE '%Administrador%';

-- 3. PERMISSÕES TÉCNICAS (auth_permission)
-- Vincula o Usuário 10 a TODAS as permissões dos apps que compõem o Tenant
INSERT INTO core_usuario_user_permissions (usuario_id, permission_id)
SELECT 10, p.id 
FROM auth_permission p 
INNER JOIN django_content_type ct ON p.content_type_id = ct.id
WHERE ct.app_label IN (
    'produtos', 'analytics', 'fornecedores', 'estoque', 'clientes', 
    'vendas', 'funcionarios', 'servicos', 'financeiro', 'relatorios', 
    'configuracoes', 'fiscal', 'saft', 'compras', 'site'
)
ON CONFLICT DO NOTHING;

-- 4. STATUS DE STAFF: Essencial para que o Django permita o login e acesso às Views
UPDATE core_usuario 
SET is_staff = TRUE, 
    is_superuser = FALSE, -- Mantemos como FALSE para testar o isolamento de tenant real
    e_administrador_empresa = TRUE 
WHERE id = 10;

COMMIT;