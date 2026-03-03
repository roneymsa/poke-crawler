"""
Poké-Crawler: extrai dados de Pokémon da Bulbapedia.

Uso:
  python main.py [Bulbasaur] [Charmander] ...
  python main.py --list list.txt
  python main.py --get-all
  python main.py --sync-links   (cron diário: atualiza lista de links no banco)
  python main.py --worker       (cron frequente: processa um lote pendente)

Recomendado: executar na raiz do projeto (onde estão main.py e crawler/).
Alternativa: python -m cli (a partir da raiz).
"""

from cli import main

if __name__ == "__main__":
    main()
