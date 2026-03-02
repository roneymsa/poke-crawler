"""
Configuração do crawler distribuído (cron jobs).
Usado por --sync-links e --worker.
"""

# Quantos Pokémon processar por execução do worker
BATCH_SIZE = 25

# Delay entre requisições (segundos) — anti-ban
DELAY_MIN = 2
DELAY_MAX = 6

# Tentativas máximas antes de marcar como failed
MAX_RETRIES = 3
