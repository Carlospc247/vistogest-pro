             return HttpResponseBadRequest('Empresa não encontrada')
            
            # Criar workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Produtos"
            
            # Definir cabeçalhos
            headers = [
                'nome_produto', 'codigo_barras', 'categoria', 'preco_custo', 'preco_venda', 'taxa',
                'nome_comercial', 'codigo_interno', 'fabricante', 'fornecedor',
                'numero_lote', 'data_validade',
                'estoque_atual', 'estoque_minimo', 'estoque_maximo', 'margem_lucro',
                'desconto_percentual', 'observacoes', 'ativo'
            ]
            
            # Adicionar cabeçalhos
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = openpyxl.styles.Font(bold=True)
                cell.fill = openpyxl.styles.PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
            
    