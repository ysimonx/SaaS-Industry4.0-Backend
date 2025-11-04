# Vault Initial Secrets Directory

⚠️ **IMPORTANT:** All files in this directory (except `.gitignore` and this `README.md`) are **git-ignored** and contain sensitive secrets.

## Structure

```
vault/init-data/
├── .gitignore           # Ignore all files except itself
├── README.md            # This file
├── docker.env           # ✅ Active secrets for Docker environment (git-ignored)
├── docker.env.example   # Template for docker.env (committed to git)
├── dev.env.example      # Template for dev.env (committed to git)
└── prod.env.example     # Template for prod.env (committed to git)
```

## Files

### Active Secret Files (Git-Ignored)
- **`docker.env`** - Secrets for Docker Compose (default environment)
- **`dev.env`** - Secrets for local development without Docker
- **`prod.env`** - Secrets for production (create manually on prod server)

### Example Templates (Committed to Git)
- **`*.env.example`** - Templates showing the structure, safe to commit

## Usage

### For Docker Environment (Default)
The `docker.env` file has been auto-generated with a random JWT key. You can start using it immediately:

```bash
docker-compose up -d
```

### For Dev Environment
If you want to run without Docker:

```bash
cp vault/init-data/dev.env.example vault/init-data/dev.env
# Edit dev.env with your local configuration
export VAULT_ENV=dev
docker-compose up -d
```

### For Production
On your production server only:

```bash
cp vault/init-data/prod.env.example vault/init-data/prod.env
# Edit prod.env with strong, unique production secrets
# Generate JWT key: openssl rand -hex 32
# Use strong database passwords (20+ characters)
# Use production S3 credentials

# Backup the file encrypted (IMPORTANT!)
gpg --symmetric --cipher-algo AES256 vault/init-data/prod.env
# Store the .gpg file in a secure location (vault, password manager)

export VAULT_ENV=prod
docker-compose -f docker-compose.prod.yml up -d
```

## Security Best Practices

✅ **DO:**
- Keep `*.env` files git-ignored (already configured)
- Generate strong JWT keys: `openssl rand -hex 32`
- Use different secrets for dev/docker/prod
- Backup prod.env encrypted outside the repository
- Rotate secrets regularly (every 90 days for production)

❌ **DON'T:**
- Never commit `*.env` files (only `*.env.example`)
- Never reuse dev/docker secrets in production
- Never share secrets via email or chat
- Never hardcode secrets in application code

## How It Works

1. **Startup**: `vault-init` container reads secrets from `{env}.env`
2. **Injection**: Secrets are injected into Vault at startup
3. **AppRole**: `vault-init` generates ROLE_ID and SECRET_ID
4. **Output**: Credentials written to `.env.vault` (also git-ignored)
5. **Application**: API/worker use `.env.vault` to authenticate with Vault
6. **Runtime**: Application reads secrets from Vault (not from environment variables)

## Troubleshooting

**Error: "Fichier docker.env introuvable"**
- Make sure `vault/init-data/docker.env` exists
- Copy from `docker.env.example` if needed

**Need to change environment?**
```bash
# Switch to dev
export VAULT_ENV=dev
docker-compose up -d

# Switch to prod
export VAULT_ENV=prod
docker-compose up -d
```

**Reset everything?**
```bash
docker-compose down
rm .env.vault
docker-compose up -d
```
