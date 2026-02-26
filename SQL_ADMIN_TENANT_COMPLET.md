BEGIN;

DO $$
DECLARE
    v_empresa_id integer;
    v_loja_id integer;
    v_usuario_id integer;
    v_cargo_id integer;
    v_dept_id integer;
BEGIN

    -- 1. INSERIR EMPRESA (Sem acentos no schema_name)
    INSERT INTO empresas_empresa (
        schema_name, nome, nome_fantasia, nif, codigo_validacao, 
        endereco, numero, bairro, cidade, provincia, postal, 
        telefone, email, ativa, data_cadastro, regime
    ) VALUES (
        'mundo_e_maquinas', 'Mundo e Maquinas LDA', 'Mundo Maquinas', '5001304461', 'ATCUD-999', 
        'Rua das Alfaias', '44', 'Talatona', 'Luanda', 'LUA', '0000', 
        '920000000', 'geral@mundoemaquinas.ao', TRUE, NOW(), 'MISTO'
    ) RETURNING id INTO v_empresa_id;

    -- 2. INSERIR DOMINIO
    INSERT INTO empresas_domain (domain, is_primary, tenant_id)
    VALUES ('mundoemaquinas.localhost', TRUE, v_empresa_id);

    -- 3. INSERIR LOJA MATRIZ
    INSERT INTO empresas_loja (
        empresa_id, nome, codigo, endereco, numero, bairro, cidade, 
        postal, provincia, ativa, eh_matriz, created_at, updated_at
    ) VALUES (
        v_empresa_id, 'Sede Talatona', 'MATRIZ-01', 'Rua das Alfaias', '44', 'Talatona', 'Luanda', 
        '0000', 'LUA', TRUE, TRUE, NOW(), NOW()
    ) RETURNING id INTO v_loja_id;

    -- 4. INSERIR USUARIO ADMINISTRADOR SUPREMO (is_staff = false)
    INSERT INTO core_usuario (
        password, is_superuser, username, first_name, last_name, 
        email, is_staff, is_active, date_joined, empresa_id, loja_id, 
        telefone, e_administrador_empresa
    ) VALUES (
        'pbkdf2_sha256$870000$hashexemplo...', FALSE, 'admin_mundo', 'Carlos', 'Sebastiao', 
        'admin@mundoemaquinas.ao', FALSE, TRUE, NOW(), v_empresa_id, v_loja_id, 
        '920000000', TRUE
    ) RETURNING id INTO v_usuario_id;

    -- 5. CRIACAO DO SCHEMA FISICO
    EXECUTE 'CREATE SCHEMA mundo_e_maquinas';

    -- 6. INSERIR CARGO NO SCHEMA NOVO (Poder Supremo)
    INSERT INTO mundo_e_maquinas.funcionarios_cargo (
        nome, codigo, descricao, nivel_hierarquico, categoria, 
        salario_base, selecionar_todos, pode_estornar_pagamento, pode_pagar_salario,
        pode_vender, pode_ver_vendas, pode_fazer_desconto, limite_desconto_percentual,
        pode_cancelar_venda, pode_fazer_devolucao, pode_alterar_preco,
        pode_gerenciar_estoque, pode_gerenciar_funcionarios, pode_editar_produtos,
        pode_acessar_rh, pode_acessar_financeiro, pode_acessar_configuracoes,
        pode_exportar_saft, pode_acessar_dashboard_fiscal,
        ativo, created_at, updated_at, empresa_id
    ) VALUES (
        'Administrador Supremo', 'SUPREMO-01', 'Controle total via UI', 1, 'diretoria', 
        0.00, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, 100.00, TRUE, TRUE, TRUE, 
        TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, 
        TRUE, NOW(), NOW(), v_empresa_id
    ) RETURNING id INTO v_cargo_id;

    -- 7. INSERIR DEPARTAMENTO
    INSERT INTO mundo_e_maquinas.funcionarios_departamento (
        nome, codigo, descricao, ativo, created_at, updated_at, loja_id
    ) VALUES (
        'Administrativo', 'DEP-001', 'Gestao Central', TRUE, NOW(), NOW(), v_loja_id
    ) RETURNING id INTO v_dept_id;

    -- 8. INSERIR REGISTRO DE FUNCIONARIO
    INSERT INTO mundo_e_maquinas.funcionarios_funcionario (
        matricula, nome_completo, bi, data_nascimento, sexo, nacionalidade,
        endereco, numero, bairro, cidade, provincia, postal,
        data_admissao, salario_atual, ativo, em_experiencia, 
        empresa_id, usuario_id, cargo_id, departamento_id, loja_principal_id,
        created_at, updated_at
    ) VALUES (
        'FUNC-00001', 'Carlos Sebastiao', '001234567LA044', '1985-01-01', 'M', 'Angolana',
        'Rua das Alfaias', '44', 'Talatona', 'Luanda', 'LUA', '0000',
        CURRENT_DATE, 1.00, TRUE, FALSE, 
        v_empresa_id, v_usuario_id, v_cargo_id, v_dept_id, v_loja_id, NOW(), NOW()
    );

    -- 9. VINCULAR PERMISSOES TECNICAS
    INSERT INTO core_usuario_user_permissions (usuario_id, permission_id)
    SELECT v_usuario_id, p.id 
    FROM auth_permission p 
    INNER JOIN django_content_type ct ON p.content_type_id = ct.id
    WHERE ct.app_label IN (
        'produtos', 'analytics', 'fornecedores', 'estoque', 'clientes', 
        'vendas', 'funcionarios', 'servicos', 'financeiro', 'relatorios', 
        'configuracoes', 'fiscal', 'saft', 'compras', 'site'
    )
    ON CONFLICT DO NOTHING;

    RAISE NOTICE 'Sucesso: Tenant Mundo e Maquinas criado! Usuario ID: %', v_usuario_id;

END $$;

COMMIT;