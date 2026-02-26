Django
djangorestframework
django-allauth
django-cors-headers
django-filter
django-environ
django-redis
django-crispy-forms
crispy-tailwind
django-widget-tweaks
django-celery-beat

celery
redis
gunicorn
whitenoise

psycopg2-binary
dj-database-url

cloudinary
django-cloudinary-storage

weasyprint
reportlab
qrcode
openpyxl
pandas
matplotlib
seaborn
scikit-learn
statsmodels

python-dotenv
requests
pytest

pip freeze > requirements.lock.txt



criar tabela manualmente
-- Garanta que está no banco sotarq_vendor
CREATE TABLE IF NOT EXISTS public.empresas_empresa (
    id SERIAL PRIMARY KEY,
    schema_name VARCHAR(63) UNIQUE NOT NULL,
    nome VARCHAR(200) NOT NULL,
    nome_fantasia VARCHAR(200),
    nif VARCHAR(10) UNIQUE NOT NULL,
    codigo_validacao VARCHAR(500),
    endereco VARCHAR(200) NOT NULL,
    numero VARCHAR(10),
    bairro VARCHAR(100) NOT NULL,
    cidade VARCHAR(100) NOT NULL,
    provincia VARCHAR(50) NOT NULL,
    postal VARCHAR(9) NOT NULL,
    telefone VARCHAR(20) NOT NULL,
    email VARCHAR(254) NOT NULL,
    foto VARCHAR(100),
    ativa BOOLEAN DEFAULT TRUE,
    data_cadastro TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de Domínios também é necessária
CREATE TABLE IF NOT EXISTS public.empresas_domain (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(253) UNIQUE NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    tenant_id INTEGER NOT NULL REFERENCES public.empresas_empresa(id)
);




1. Protocolo de Limpeza SQL (No psql)
Precisamos remover a constraint que está travando o sistema. Execute isso no seu terminal do Postgres:
-- 1. Remover a constraint problemática de auditoria
ALTER TABLE public.auditoria_publica_logauditoriapublica 
DROP CONSTRAINT IF EXISTS auditoria_publica_lo_empresa_relacionada__bb1a6021_fk_core_empr;

-- 2. Limpar a tabela de logs de auditoria para evitar novos conflitos de FK
TRUNCATE TABLE public.auditoria_publica_logauditoriapublica CASCADE;

-- 3. Por segurança, verifique se a tabela core_empresa ainda existe e remova-a se estiver vazia
DROP TABLE IF EXISTS public.core_empresa CASCADE;



##
-- Criar a tabela de Lojas (que herdou de TimeStampedModel)
CREATE TABLE IF NOT EXISTS public.empresas_loja (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    nome VARCHAR(200) NOT NULL,
    codigo VARCHAR(20) NOT NULL,
    endereco VARCHAR(200) NOT NULL,
    numero VARCHAR(10),
    bairro VARCHAR(100) NOT NULL,
    cidade VARCHAR(100) NOT NULL,
    postal VARCHAR(9) NOT NULL,
    provincia VARCHAR(50) NOT NULL,
    foto VARCHAR(100),
    telefone VARCHAR(20),
    email VARCHAR(254),
    ativa BOOLEAN DEFAULT TRUE,
    eh_matriz BOOLEAN DEFAULT FALSE,
    empresa_id INTEGER NOT NULL REFERENCES public.empresas_empresa(id) ON DELETE CASCADE,
    UNIQUE (empresa_id, codigo)
);

-- Criar a tabela de Categorias (que também está em empresas agora)
CREATE TABLE IF NOT EXISTS public.empresas_categoria (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    nome VARCHAR(100) NOT NULL,
    codigo VARCHAR(20),
    descricao TEXT,
    ativa BOOLEAN DEFAULT TRUE,
    empresa_id INTEGER NOT NULL REFERENCES public.empresas_empresa(id) ON DELETE CASCADE
);

-- Adicionar a constraint de unicidade para Categoria conforme o seu modelo
ALTER TABLE public.empresas_categoria 
ADD CONSTRAINT unique_categoria_empresa_nome UNIQUE (empresa_id, nome);