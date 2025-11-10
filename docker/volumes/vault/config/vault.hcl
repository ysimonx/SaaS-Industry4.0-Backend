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
# Désactivé pour éviter les conflits en mode standalone
# cluster_addr = "https://0.0.0.0:8201"

# Interface utilisateur Web
ui = true

# Désactiver mlock pour Docker (déjà géré par IPC_LOCK)
disable_mlock = true

# Niveau de logs
log_level = "info"

# Les logs sont gérés par Docker (stdout/stderr)
# Pas de fichier de logs pour éviter les problèmes de permissions
