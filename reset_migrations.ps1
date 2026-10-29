# =========================================
# 1️⃣ Limpar migrações e caches
# =========================================
$apps = Get-ChildItem -Directory -Path "apps"

foreach ($app in $apps) {
    $migrationPath = Join-Path $app.FullName "migrations"

    if (Test-Path $migrationPath) {
        # Remove todos os arquivos de migração
        Get-ChildItem -Path $migrationPath -Include "000*.py","000*.pyc" -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue

        # Remove __pycache__ dentro de migrations
        Get-ChildItem -Path $migrationPath -Directory -Filter "__pycache__" -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }

    # Remove __pycache__ geral dentro do app
    Get-ChildItem -Path $app.FullName -Directory -Filter "__pycache__" -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

# Remove __pycache__ na raiz do projeto
Get-ChildItem -Path . -Directory -Filter "__pycache__" -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "✅ Todas as migrações antigas e caches foram removidos."

# =========================================
# 2️⃣ Criar novas migrações na ordem segura
# =========================================
$ordem = @(
    "core",
    "fornecedores",
    "produtos",
    "licenca",
    "estoque",
    "vendas",
    "clientes",
    "compras",
    "analytics",
    "funcionarios",
    "servicos",
    "financeiro",
    "relatorios",
    "configuracoes",
    "fiscal"
)

foreach ($app in $ordem) {
    Write-Host "Criando migrações para a app: $app"
    python manage.py makemigrations $app
}

Write-Host "✅ Todas as migrações foram recriadas na ordem correta."
