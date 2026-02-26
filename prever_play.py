# BY CHATGPT
import math
from collections import Counter

# ==========================
# BASE DE DADOS HISTÓRICA
# ==========================

historico = [
    (3.00, 3.15, 2.28, "1"),
    (2.26, 2.95, 3.25, "1"),
    (2.40, 3.50, 2.70, "1"),
    (1.36, 5.40, 6.60, "1"),
    (4.60, 3.75, 1.70, "2"),
    (2.16, 3.35, 3.25, "X"),
    (2.65, 2.85, 2.49, "2"),
    (1.94, 3.00, 3.55, "2"),
    (2.08, 3.40, 3.65, "2"),
    (2.28, 3.35, 2.55, "2"),
    (2.27, 3.50, 2.75, "X"),
    (1.13, 7.60, 13.00, "1"),
    (1.10, 8.20, 18.00, "1"),
    (1.93, 3.55, 3.45, "2"),
    (4.20, 3.60, 1.65, "2"),
    (2.90, 3.05, 2.29, "1"),
    (2.28, 3.40, 2.65, "2"),
    (2.11, 3.00, 3.85, "X"),
    (1.55, 3.65, 4.90, "1"),
    (4.30, 3.50, 1.66, "X"),
    (9.40, 6.00, 1.18, "2"),
    (3.50, 3.50, 1.83, "X"),
    (1.77, 3.95, 3.95, "1"),
    (1.11, 8.20, 23.00, "1"),
    (3.05, 2.90, 2.28, "1"),
    (2.90, 3.05, 2.29, "1"),#
    (2.90, 3.05, 2.29, "1"), 
    (2.55, 2.90, 2.70, "1"),
    (2.04, 2.55, 4.20, "X"), 
    (2.24, 2.70, 3.30, "2"), 
    (4.10, 3.20, 1.77, "X"),
    (3.45, 2.80, 2.13, "1"), 
    (1.42, 3.95, 6.20, "X"), 
    (1.22, 5.20, 9.20, "1"),
    (1.38, 4.30, 6.60, "1"), 
    (1.39, 4.40, 6.00, "1"),
]

# ==========================
# FUNÇÕES
# ==========================

def odds_para_prob(odd1, oddx, odd2):
    p1 = 1/odd1
    px = 1/oddx
    p2 = 1/odd2
    
    soma = p1 + px + p2
    
    return (p1/soma, px/soma, p2/soma)


def distancia(prob_nova, prob_hist):
    return math.sqrt(
        (prob_nova[0] - prob_hist[0])**2 +
        (prob_nova[1] - prob_hist[1])**2 +
        (prob_nova[2] - prob_hist[2])**2
    )

# ==========================
# LOOP PRINCIPAL
# ==========================

print("\n=== SISTEMA DE PREVISÃO 1X2 (LOOP ATIVO) ===")
print("Digite 'sair' a qualquer momento para encerrar.\n")

while True:
    entrada1 = input("Odd Casa (1): ")
    
    if entrada1.lower() == "sair":
        print("\nSistema encerrado.")
        break

    entradaX = input("Odd Empate (X): ")
    if entradaX.lower() == "sair":
        print("\nSistema encerrado.")
        break

    entrada2 = input("Odd Fora (2): ")
    if entrada2.lower() == "sair":
        print("\nSistema encerrado.")
        break

    try:
        odd1 = float(entrada1)
        oddx = float(entradaX)
        odd2 = float(entrada2)
    except ValueError:
        print("\n⚠️ Entrada inválida. Use apenas números.\n")
        continue

    prob_nova = odds_para_prob(odd1, oddx, odd2)

    distancias = []

    for jogo in historico:
        prob_hist = odds_para_prob(jogo[0], jogo[1], jogo[2])
        dist = distancia(prob_nova, prob_hist)
        distancias.append((dist, jogo[3]))

    distancias.sort(key=lambda x: x[0])

    mais_semelhantes = distancias[:10]

    resultados = [r[1] for r in mais_semelhantes]

    previsao = Counter(resultados).most_common(1)[0][0]

    print("\n🔎 Jogos mais semelhantes encontrados:")
    for jogo in mais_semelhantes:
        print(jogo)

    print("\n🎯 PREVISÃO FINAL:", previsao)
    print("\n---------------------------------------\n")
