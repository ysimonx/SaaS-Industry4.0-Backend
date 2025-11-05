# Migration Guide: Environment Variables vs HashiCorp Vault

This document explains the changes made to clarify the difference between using environment variables and HashiCorp Vault for secrets management.

## Problem Statement

The original documentation had an inconsistency: it instructed users to copy `.env.docker` (which contains secrets) while also promoting HashiCorp Vault for secrets management. This created confusion about:

1. **Which approach to use**: Environment variables or Vault?
2. **How to set up each approach**: Different steps for each method
3. **Security implications**: `.env` files with secrets vs. Vault-managed secrets

## Solution Overview

We've restructured the documentation and configuration files to clearly separate two deployment approaches:

### Option A: With HashiCorp Vault (Recommended for Production)
- **Configuration**: Use `.env.docker.minimal` (NO secrets)
- **Secrets**: Managed in `vault/init-data/docker.env` and stored in Vault
- **Security**: Enterprise-grade with encryption, audit logging, rotation
- **Use case**: Production, staging, or production-like development

### Option B: Without Vault (Simple Development)
- **Configuration**: Use `.env.docker` (WITH secrets)
- **Secrets**: Stored in `.env` file
- **Security**: Basic file-based (never commit to Git!)
- **Use case**: Quick local development and testing

---

## Files Created

### 1. `.env.docker.minimal`

**Purpose**: Minimal environment file for Vault-based deployments

**Contents**:
- Non-secret configuration only (ports, timeouts, pool sizes, etc.)
- Clear comments indicating secrets are managed by Vault
- Footer listing all secrets managed by Vault

**Usage**:
```bash
cp .env.docker.minimal .env  # For Vault setup
```

**Key Features**:
- NO sensitive data (DATABASE_URL, JWT_SECRET_KEY, S3 credentials, etc.)
- All application configuration settings preserved
- Clear documentation at the top and bottom

---

## Files Modified

### 2. `README.md` - Quick Start Section

**Changes**:
- Split "Quick Start" into two clear options:
  - **Option A: With HashiCorp Vault** (recommended)
  - **Option B: Without Vault** (simple dev setup)

**Option A (Vault) - Key Steps**:
```bash
# 1.2. Copy minimal environment file (NO SECRETS)
cp .env.docker.minimal .env

# 1.3. Create secrets file for Vault
cat > vault/init-data/docker.env <<'EOF'
DATABASE_URL=postgresql://...
JWT_SECRET_KEY=$(openssl rand -hex 32)
# ... other secrets
EOF
```

**Option B (No Vault) - Key Steps**:
```bash
# 1.2. Copy environment file WITH secrets
cp .env.docker .env

# 2.1. Start services (excluding Vault)
docker-compose up -d postgres kafka zookeeper minio api worker
```

**Added Warnings**:
- Clear security warnings for Option B
- Recommendation to use Option A for production

### 3. `README.md` - Installation Section (Option 1: Docker)

**Changes**:

#### Section 1: Initial Setup
- Split into "With Vault" and "Without Vault" sub-sections
- Clear instructions for each approach
- Warning about committing secrets

#### Section 2: Generate Secure Secrets
- Added note: "Skip this section if using Vault"
- Clarified that secrets are in `vault/init-data/docker.env` for Vault

#### Section 3: Start Services
- Separate commands for Vault vs. non-Vault
- Vault: `docker-compose up -d` (all services)
- No Vault: `docker-compose up -d postgres kafka ... api worker` (exclude Vault)

#### Section 4: Initialize Database
- Added clear distinction for Flask commands:
  - **With Vault**: Use `/app/flask-wrapper.sh db upgrade`
  - **Without Vault**: Use `flask db upgrade`
- Side-by-side comparison for both approaches

### 4. `.env.example`

**Changes**:
- Added comprehensive header explaining both options
- Clear reference to README.md sections
- Documented all available environment variables
- Note that this file is for reference only

---

## Architecture: Secrets Management

### With Vault (Option A)

```
┌─────────────────────────────────────────────────────────────┐
│                    Configuration Flow                        │
└─────────────────────────────────────────────────────────────┘

1. Developer creates:
   ├── .env.docker.minimal → .env (NO secrets)
   └── vault/init-data/docker.env (secrets source)

2. Vault initialization:
   ├── vault-init service reads vault/init-data/docker.env
   ├── Injects secrets into Vault KV store
   └── Creates AppRole credentials → .env.vault

3. Application runtime:
   ├── Flask command: /app/flask-wrapper.sh db upgrade
   ├── Script loads secrets from Vault using AppRole
   ├── Sets environment variables dynamically
   └── Executes Flask command with secrets

4. Security benefits:
   ├── Secrets encrypted at rest and in transit
   ├── Audit logging of all secret access
   ├── Automatic rotation capabilities
   └── No secrets in .env file
```

### Without Vault (Option B)

```
┌─────────────────────────────────────────────────────────────┐
│                    Configuration Flow                        │
└─────────────────────────────────────────────────────────────┘

1. Developer creates:
   └── .env.docker → .env (WITH secrets)

2. Application runtime:
   ├── Flask command: flask db upgrade
   ├── Reads secrets from .env file
   └── Executes command

3. Security considerations:
   ├── Secrets in plain text file
   ├── Risk of accidental Git commit
   ├── No audit logging
   └── Manual rotation required

⚠️  NEVER use for production!
```

---

## Migration Guide

### For Existing Users

#### If Currently Using `.env` Files

**To migrate to Vault:**

```bash
# 1. Backup existing .env
cp .env .env.backup

# 2. Create Vault secrets file from existing .env
cat > vault/init-data/docker.env <<'EOF'
DATABASE_URL=$(grep DATABASE_URL .env | cut -d '=' -f2)
JWT_SECRET_KEY=$(grep JWT_SECRET_KEY .env | cut -d '=' -f2)
S3_ACCESS_KEY_ID=$(grep S3_ACCESS_KEY_ID .env | cut -d '=' -f2)
S3_SECRET_ACCESS_KEY=$(grep S3_SECRET_ACCESS_KEY .env | cut -d '=' -f2)
# ... copy other secrets
EOF

# 3. Replace .env with minimal version
cp .env.docker.minimal .env

# 4. Follow "Quick Start - Option A" to initialize Vault
```

#### If Currently Using Vault

**No changes needed!** Your setup is already correct.

### For New Users

**Recommended Path**:
1. Start with **Option A (Vault)** for production-like setup
2. Follow [Quick Start - Option A](#option-a-with-hashicorp-vault-recommended-for-production-like-setup)
3. Use Option B only for quick testing if Vault seems too complex

---

## Security Checklist

### With Vault ✅

- [ ] `.env` file contains NO secrets (only configuration)
- [ ] `vault/init-data/docker.env` is in `.gitignore`
- [ ] `.env.vault` (AppRole credentials) is in `.gitignore`
- [ ] Vault root token saved in password manager
- [ ] Vault unseal keys backed up securely
- [ ] Flask commands use `/app/flask-wrapper.sh` prefix

### Without Vault ⚠️

- [ ] `.env` file is in `.gitignore`
- [ ] `.env` never committed to Git (check with `git status`)
- [ ] Strong JWT secret generated (64+ characters)
- [ ] Database passwords changed from defaults
- [ ] Only used for local development (NEVER production)

---

## FAQ

### Q: Can I switch between Vault and non-Vault?

**A:** Yes, but not recommended for production.

- **Dev → Vault**: Copy secrets from `.env` to `vault/init-data/docker.env`, then use `.env.docker.minimal`
- **Vault → Dev**: Copy secrets from Vault to `.env` (discouraged)

### Q: Which Flask command prefix should I use?

**A:**
- **With Vault**: Always use `/app/flask-wrapper.sh` (e.g., `/app/flask-wrapper.sh db upgrade`)
- **Without Vault**: Use `flask` directly (e.g., `flask db upgrade`)

The wrapper script loads secrets from Vault before executing Flask commands.

### Q: What if I accidentally committed `.env` with secrets?

**A:**
1. Remove from Git: `git rm --cached .env`
2. Add to `.gitignore` (already done)
3. Rotate ALL secrets immediately
4. Use Vault going forward

### Q: Do I need Vault for local development?

**A:** No, but it's recommended if you want a production-like environment. Use Option B for quick testing.

### Q: Can I use Vault in production?

**A:** Yes! That's the recommended approach. However:
- Don't use Vault in dev mode (`-dev` flag)
- Configure proper storage backend (Consul, etcd, integrated storage)
- Enable TLS/SSL
- Set up proper policies and audit logging
- See: `vault/` directory for production configuration examples

---

## File Reference

| File | Purpose | Contains Secrets? | Commit to Git? |
|------|---------|-------------------|----------------|
| `.env.example` | Documentation template | No | ✅ Yes |
| `.env.docker` | Dev setup WITHOUT Vault | **Yes** | ❌ No |
| `.env.docker.minimal` | Dev setup WITH Vault | No | ✅ Yes |
| `.env` | Active configuration | Depends | ❌ No |
| `vault/init-data/docker.env` | Vault secrets source | **Yes** | ❌ No |
| `.env.vault` | AppRole credentials | **Yes** | ❌ No |
| `vault/data/root-token.txt` | Vault admin token | **Yes** | ❌ No |
| `vault/data/unseal-keys.json` | Vault unseal keys | **Yes** | ❌ No |

---

## Summary of Benefits

### Option A: HashiCorp Vault

✅ **Pros**:
- Enterprise-grade security
- Encryption at rest and in transit
- Audit logging of all secret access
- Automatic secret rotation
- Centralized secrets management
- Production-ready

❌ **Cons**:
- More complex initial setup
- Requires Vault infrastructure
- Learning curve for Vault operations

### Option B: Environment Variables

✅ **Pros**:
- Simple setup (2 commands)
- No additional infrastructure
- Familiar workflow
- Fast for quick testing

❌ **Cons**:
- Secrets in plain text
- Risk of accidental Git commit
- No audit logging
- Manual secret rotation
- NOT production-ready

---

## Related Documentation

- [README.md - Quick Start](README.md#quick-start) - Step-by-step setup guides
- [README.md - Installation](README.md#installation) - Detailed installation reference
- [specs/vault/plan-vault.md](specs/vault/plan-vault.md) - Complete Vault integration plan
- [vault/init-data/README.md](vault/init-data/README.md) - Vault secrets templates
- [.env.example](.env.example) - All environment variables reference

---

**Last Updated**: 2025-01-05
**Related Issue**: Documentation inconsistency between `.env.docker` copy instruction and Vault usage
