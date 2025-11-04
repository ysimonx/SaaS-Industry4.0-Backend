# Docker Deployment Guide

Complete guide for running the SaaS Platform with Docker and Docker Compose.

## Prerequisites

- Docker 20.10+ installed
- Docker Compose 2.0+ installed
- At least 4GB RAM available for Docker
- Ports available: 4999, 5432, 9000, 9001, 9092, 9093

## Quick Start

### 1. Clone and Setup

```bash
# Clone repository
git clone <repository-url>
cd SaaSBackendWithClaude

# Copy environment file
cp .env.docker .env

# Edit .env and set JWT_SECRET_KEY
nano .env  # Change JWT_SECRET_KEY to a secure random value
```

### 2. Start All Services

```bash
# Start all services in background
docker-compose up -d

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f api
docker-compose logs -f worker
```

### 3. Initialize Database

```bash
# Run database initialization
docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant

# Follow prompts to create admin user
# Default: admin@example.com / password123
```

### 4. Verify Services

```bash
# Check API health
curl http://localhost:4999/health

# Expected response:
# {"status": "healthy", "message": "SaaS Platform API is running"}

# Check MinIO console
open http://localhost:9001  # Login: minioadmin / minioadmin

# Check service status
docker-compose ps
```

## Services

The docker-compose stack includes:

| Service | Port | Description |
|---------|------|-------------|
| **api** | 4999 | Flask REST API server |
| **worker** | - | Kafka consumer worker |
| **postgres** | 5432 | PostgreSQL database |
| **kafka** | 9092, 9093 | Message broker |
| **zookeeper** | 2181 | Kafka coordination |
| **minio** | 9000, 9001 | S3-compatible storage |
| **minio-init** | - | Bucket initialization (exits) |

## Common Operations

### Start/Stop Services

```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d api

# Stop all services
docker-compose down

# Stop and remove volumes (deletes data!)
docker-compose down -v
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f worker

# Last 100 lines
docker-compose logs --tail=100 api
```

### Rebuild Images

```bash
# Rebuild all images
docker-compose build

# Rebuild specific service
docker-compose build api

# Rebuild and restart
docker-compose up -d --build
```

### Execute Commands

```bash
# Open shell in API container
docker-compose exec api /bin/bash

# Run Flask shell
docker-compose exec api python -c "from app import create_app; app = create_app(); app.app_context().push()"

# Create admin user
docker-compose exec api python scripts/init_db.py --create-admin
```

### Flask Commands with Vault Integration

**Important**: With Vault integration enabled, Flask commands must use the wrapper script `/app/flask-wrapper.sh` to load environment variables from Vault:

```bash
# Database migrations
docker-compose exec api /app/flask-wrapper.sh db init
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Migration message"
docker-compose exec api /app/flask-wrapper.sh db upgrade
docker-compose exec api /app/flask-wrapper.sh db downgrade
docker-compose exec api /app/flask-wrapper.sh db current
docker-compose exec api /app/flask-wrapper.sh db history

# Other Flask commands
docker-compose exec api /app/flask-wrapper.sh shell
docker-compose exec api /app/flask-wrapper.sh routes

# The wrapper script automatically:
# 1. Loads variables from /.env.vault
# 2. Exports Vault credentials (VAULT_ADDR, VAULT_ROLE_ID, VAULT_SECRET_ID)
# 3. Executes the Flask command with proper environment
```

### Database Operations

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U postgres -d saas_platform

# Backup database
docker-compose exec postgres pg_dump -U postgres saas_platform > backup.sql

# Restore database
docker-compose exec -T postgres psql -U postgres saas_platform < backup.sql

# View database logs
docker-compose logs postgres
```

### Kafka Operations

```bash
# List topics
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# Create topic manually
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic test --partitions 1 --replication-factor 1

# Consume messages from topic
docker-compose exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic document.uploaded --from-beginning

# Produce test message
docker-compose exec kafka kafka-console-producer --bootstrap-server localhost:9092 --topic test
```

### MinIO (S3) Operations

```bash
# Access MinIO console
open http://localhost:9001

# Login credentials
# Username: minioadmin
# Password: minioadmin

# List buckets using mc client
docker-compose exec minio mc ls myminio

# Upload file to bucket
docker-compose exec minio mc cp /data/testfile.txt myminio/saas-documents/
```

## Development Workflow

### Hot Reload

The API and worker services mount the `backend/` directory as a volume, enabling hot reload:

```bash
# Edit code in backend/
# Changes are automatically detected and reloaded
# No need to rebuild containers for code changes
```

### Add Python Dependency

```bash
# 1. Add package to backend/requirements.txt
echo "requests==2.31.0" >> backend/requirements.txt

# 2. Rebuild container
docker-compose build api worker

# 3. Restart services
docker-compose up -d api worker
```

### Run Tests

```bash
# Unit tests
docker-compose exec api pytest tests/unit/

# Integration tests
docker-compose exec api pytest tests/integration/

# All tests with coverage
docker-compose exec api pytest --cov=app tests/
```

## Environment Variables

Key environment variables (see `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | postgres://... | PostgreSQL connection string |
| `JWT_SECRET_KEY` | dev-secret-key... | **Change in production!** |
| `KAFKA_BOOTSTRAP_SERVERS` | kafka:9092 | Kafka broker address |
| `S3_ENDPOINT_URL` | http://minio:9000 | S3 endpoint |
| `S3_BUCKET` | saas-documents | S3 bucket name |
| `FLASK_ENV` | development | Flask environment |
| `LOG_LEVEL` | DEBUG | Logging level |

## Troubleshooting

### API won't start

```bash
# Check logs
docker-compose logs api

# Common issues:
# - Database not ready: Wait for postgres healthcheck
# - Port conflict: Check if port 4999 is in use
# - Missing env vars: Verify .env file exists
```

### Worker not processing messages

```bash
# Check worker logs
docker-compose logs worker

# Verify Kafka connection
docker-compose exec worker nc -zv kafka 9092

# Check Kafka topics
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list
```

### Database connection errors

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check PostgreSQL logs
docker-compose logs postgres

# Test connection
docker-compose exec postgres psql -U postgres -d saas_platform -c "SELECT 1"
```

### MinIO access denied

```bash
# Verify MinIO is running
docker-compose ps minio

# Check MinIO logs
docker-compose logs minio

# Re-run bucket initialization
docker-compose up minio-init
```

### Out of disk space

```bash
# Check Docker disk usage
docker system df

# Clean up unused images
docker system prune -a

# Remove volumes (WARNING: deletes data!)
docker-compose down -v
```

### Kafka consumer lag

```bash
# Check consumer group status
docker-compose exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group saas-consumer-group

# Reset consumer offset (use with caution!)
docker-compose exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --group saas-consumer-group --reset-offsets --to-earliest --all-topics --execute
```

## Production Deployment

### Security Checklist

- [ ] Change `JWT_SECRET_KEY` to strong random value
- [ ] Change PostgreSQL password
- [ ] Change MinIO credentials
- [ ] Set `FLASK_ENV=production`
- [ ] Set `FLASK_DEBUG=0`
- [ ] Enable SSL for PostgreSQL
- [ ] Enable SSL for MinIO
- [ ] Use external Kafka cluster
- [ ] Set up proper logging aggregation
- [ ] Configure backup strategy
- [ ] Set up monitoring (Prometheus/Grafana)

### Production Compose

For production, create `docker-compose.prod.yml`:

```yaml
version: '3.8'
services:
  api:
    env_file: .env.production
    restart: always
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G

  worker:
    env_file: .env.production
    restart: always
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
```

Run with: `docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d`

## Performance Tuning

### PostgreSQL

```bash
# Increase max connections
docker-compose exec postgres psql -U postgres -c "ALTER SYSTEM SET max_connections = 200;"
docker-compose restart postgres

# Enable query logging
docker-compose exec postgres psql -U postgres -c "ALTER SYSTEM SET log_statement = 'all';"
```

### Gunicorn Workers

Edit `docker/Dockerfile.api` to adjust worker count:

```dockerfile
CMD ["gunicorn", "-w", "8", ...]  # Increase from 4 to 8
```

### Kafka Partitions

```bash
# Increase partitions for better parallelism
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --alter --topic document.uploaded --partitions 4
```

## Backup & Recovery

### Automated Backups

```bash
# Add to crontab
0 2 * * * docker-compose exec -T postgres pg_dump -U postgres saas_platform | gzip > /backups/saas_$(date +\%Y\%m\%d).sql.gz
```

### Restore from Backup

```bash
# Stop services
docker-compose down

# Restore database
gunzip < backup.sql.gz | docker-compose exec -T postgres psql -U postgres saas_platform

# Start services
docker-compose up -d
```

## Next Steps

1. Review and customize `.env` file
2. Set strong passwords for production
3. Configure external monitoring
4. Set up CI/CD pipeline
5. Configure load balancer (Nginx/Traefik)
6. Enable HTTPS with SSL certificates
7. Set up log aggregation (ELK/Loki)
8. Configure alerting (PagerDuty/Opsgenie)

## Support

- Documentation: `docs/` directory
- API Reference: http://localhost:4999/ (see available endpoints)
- GitHub Issues: [Repository Issues](https://github.com/your-repo/issues)
