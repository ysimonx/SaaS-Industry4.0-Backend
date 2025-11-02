# Docker Configuration

This directory contains Docker configurations for the SaaS Platform.

## Files

- **Dockerfile.api** - Multi-stage Dockerfile for Flask API server
- **Dockerfile.worker** - Dockerfile for Kafka consumer worker
- **build-api.sh** - Build script for API Docker image
- **build-worker.sh** - Build script for worker Docker image (coming soon)

## Building Images

### API Server

```bash
# Build with default tag (latest)
./docker/build-api.sh

# Build with custom tag
./docker/build-api.sh v1.0.0
```

### Manual Build

```bash
# From project root
docker build -f docker/Dockerfile.api -t saas-platform-api:latest .
```

## Running Containers

### API Server

```bash
# Run with environment file
docker run -p 4999:4999 --env-file .env saas-platform-api:latest

# Run with environment variables
docker run -p 4999:4999 \
  -e DATABASE_URL=postgresql://user:pass@host/db \
  -e JWT_SECRET_KEY=your-secret-key \
  saas-platform-api:latest
```

### Health Check

```bash
# Check API health
curl http://localhost:4999/health

# Expected response
{"status": "healthy", "message": "SaaS Platform API is running"}
```

## Image Details

### Dockerfile.api

**Base Image**: `python:3.11-slim`

**Features**:
- Multi-stage build for optimized image size
- Non-root user for security
- Health check endpoint monitoring
- Gunicorn with 4 workers
- Automatic worker restart after 1000 requests
- Comprehensive logging to stdout/stderr

**Exposed Ports**:
- 4999 - Flask API

**Environment Variables**:
- `FLASK_APP` - Flask application entry point (default: run.py)
- `FLASK_ENV` - Flask environment (default: production)
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET_KEY` - JWT token secret key
- `KAFKA_BOOTSTRAP_SERVERS` - Kafka broker addresses
- `S3_ENDPOINT_URL` - S3 endpoint URL
- `S3_BUCKET` - S3 bucket name
- See `.env.example` for complete list

**Gunicorn Configuration**:
- Workers: 4
- Worker class: sync
- Timeout: 120 seconds
- Keep-alive: 5 seconds
- Max requests: 1000 (with 50 jitter)
- Logging: stdout/stderr

**Security**:
- Runs as non-root user (`appuser`)
- No unnecessary build tools in final image
- Minimal attack surface

**Image Size**: ~300-400MB (optimized with multi-stage build)

## Docker Compose

See `docker-compose.yml` in project root for complete stack setup including:
- PostgreSQL database
- Kafka + Zookeeper
- MinIO (S3-compatible storage)
- API server
- Worker process

## Troubleshooting

### Build fails with "requirements.txt not found"

Make sure you're running the build script from the project root:

```bash
cd /path/to/SaaSBackendWithClaude
./docker/build-api.sh
```

### Container exits immediately

Check logs:

```bash
docker logs <container-id>
```

Common issues:
- Missing environment variables (DATABASE_URL, JWT_SECRET_KEY)
- Database connection failure
- Port 4999 already in use

### Health check fails

1. Check if container is running:
   ```bash
   docker ps
   ```

2. Check container logs:
   ```bash
   docker logs <container-id>
   ```

3. Verify health endpoint inside container:
   ```bash
   docker exec <container-id> curl http://localhost:4999/health
   ```

### High memory usage

Reduce Gunicorn workers in Dockerfile.api:

```dockerfile
CMD ["gunicorn", "-w", "2", ...]  # Change from 4 to 2 workers
```

## Development vs Production

### Development

Use docker-compose with volume mounts for hot-reload:

```yaml
services:
  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    volumes:
      - ./backend:/app
    environment:
      FLASK_ENV: development
```

### Production

Use built image without volume mounts:

```bash
docker run -d \
  --name saas-api \
  --restart unless-stopped \
  -p 4999:4999 \
  --env-file .env.production \
  saas-platform-api:v1.0.0
```

## Best Practices

1. **Use specific tags** - Don't rely on `latest` in production
2. **Set resource limits** - Use `--memory` and `--cpus` flags
3. **Use secrets management** - Don't hardcode secrets in environment variables
4. **Monitor health checks** - Set up monitoring for `/health` endpoint
5. **Use reverse proxy** - Put Nginx/Traefik in front of API for SSL and load balancing
6. **Log aggregation** - Send logs to centralized logging system
7. **Image scanning** - Scan images for vulnerabilities before deployment

## Next Steps

1. Build the worker Dockerfile (Task 37)
2. Create docker-compose.yml (Task 38)
3. Set up CI/CD pipeline for automated builds
4. Configure container orchestration (Kubernetes/ECS)
