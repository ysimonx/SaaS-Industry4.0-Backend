# Configuration HashiCorp Vault - Mode Développement avec Persistance
# Documentation: https://developer.hashicorp.com/vault/docs/configuration

# Interface d'écoute
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

# Backend de stockage - File (persistant sur disque)
storage "file" {
  path = "/vault/data"
}

# Configuration de l'API
api_addr = "http://0.0.0.0:8200"
cluster_addr = "https://0.0.0.0:8201"

# Interface utilisateur Web
ui = true

# Désactiver mlock pour Docker (déjà géré par IPC_LOCK)
disable_mlock = true

# Niveau de logs
log_level = "info"

# Fichier de logs
log_file = "/vault/logs/vault.log"

# Rotation des logs
log_rotate_duration = "24h"
log_rotate_max_files = 7
