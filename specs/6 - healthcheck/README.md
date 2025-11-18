# Health Monitoring Documentation

This directory contains comprehensive documentation for the Healthchecks.io monitoring integration in the SaaS platform.

## 📚 Documentation Files

### Core Documentation

1. **[plan-healthcheck.md](plan-healthcheck.md)**
   - Complete implementation plan
   - Architecture design decisions
   - Step-by-step setup guide
   - Monitoring strategy and service tiers

2. **[DOCKER_HEALTHCHECK.md](DOCKER_HEALTHCHECK.md)**
   - Docker Compose configuration
   - Service integration details
   - Environment variable management
   - Deployment instructions

### Troubleshooting & Solutions

3. **[UUID_SYNC_FIX.md](UUID_SYNC_FIX.md)** ⭐ NEW
   - Fix for checks recreated with new UUIDs
   - Django ORM-based UUID synchronization
   - Ensures checks keep UUIDs from .env.healthchecks
   - Replaces API REST approach with direct database access

4. **[HEALTHCHECKS_TIMING_FIX.md](HEALTHCHECKS_TIMING_FIX.md)**
   - Timing mismatch resolution
   - Grace period configuration
   - Celery Beat schedule alignment
   - Common issues and fixes

5. **[HEALTHCHECKS_UNLIMITED.md](HEALTHCHECKS_UNLIMITED.md)**
   - Self-hosted Healthchecks.io setup
   - Unlimited check configuration
   - Account limit solutions
   - Scaling considerations

## 🚀 Quick Start

### Initial Setup

```bash
# 1. Start Healthchecks.io service
docker-compose up -d healthchecks

bash scripts/healthcheck/start-healthchecks-enhanced.sh
# 2. Access dashboard
open http://localhost:8000
```

or ...

```bash
# 1. Start Healthchecks.io service
docker-compose up -d healthchecks

# 2. Create admin account (if first time)
docker-compose exec healthchecks ./manage.py createsuperuser
# Credentials: admin@example.com / 12345678

# 3. Generate and configure checks
docker-compose exec api python scripts/setup_healthchecks.py

# 4. Start monitoring worker
docker-compose up -d celery-worker-monitoring

# 5. Access dashboard
open http://localhost:8000
```

### Verify Configuration

```bash
# Check timing alignment
docker-compose exec api python scripts/fix_healthchecks_timing.py

# View monitoring logs
docker-compose logs -f celery-worker-monitoring

# Check service status via API
curl -H "X-Api-Key: $HEALTHCHECKS_API_KEY" \
  http://localhost:8000/api/v1/checks/
```

## 📊 Monitored Services

### Tier 1 - Critical (2-3 min intervals)
- **PostgreSQL**: Database health, connections, slow queries
- **Redis**: Cache/broker health, memory usage
- **Flask API**: Endpoint availability, response times

### Tier 2 - Essential (5 min intervals)
- **Celery Workers**: SSO tasks, background jobs
- **Celery Beat**: Scheduler health
- **Kafka**: Message broker availability

### Tier 3 - Supporting (10+ min intervals)
- **MinIO**: S3 storage health
- **Vault**: Secrets management availability

## 🔧 Configuration Files

### Environment Files
- `.env.healthchecks` - Monitoring configuration
- `.env` - Main application configuration

### Scripts
- `/backend/scripts/setup_healthchecks.py` - Initial setup
- `/backend/scripts/fix_healthchecks_timing.py` - Timing alignment
- `/scripts/healthcheck/restart-monitoring.sh` - Service restart helper

### Source Code
- `/backend/app/tasks/monitoring_tasks.py` - Health check tasks
- `/backend/app/monitoring/healthchecks_client.py` - API client
- `/backend/app/celery_app.py` - Beat schedule configuration

## ⚠️ Important Notes

### Timing Configuration
- **Formula**: Grace period = Timeout × 2
- **Example**: 2-minute checks need 4-minute grace period
- Always align Celery Beat schedules with Healthchecks expectations

### Account Limits
- Self-hosted version has **unlimited checks**
- Cloud version limited to 20 checks (free tier)
- Use self-hosted for production deployments

### Security
- Store API keys in `.env.healthchecks`
- Never commit credentials to version control
- Use HTTPS in production environments

## 📈 Monitoring Best Practices

1. **Start Small**: Begin with critical services
2. **Tune Grace Periods**: Avoid false positives
3. **Document Alerts**: Create runbooks for each check
4. **Test Regularly**: Verify alert channels work
5. **Review Metrics**: Analyze downtime patterns

## 🆘 Troubleshooting

### Common Issues

**PostgreSQL marked as down**
- Check if monitoring worker is running
- Verify HC_CHECK_POSTGRES environment variable
- Review timing configuration (2-min schedule, 4-min grace)

**Missing environment variables**
- Ensure both `.env` and `.env.healthchecks` are loaded
- Use `restart-monitoring.sh` script for proper restart

**False alerts**
- Increase grace periods
- Check network connectivity
- Review Celery queue processing times

## 📞 Support

For issues or questions:
1. Check the documentation in this directory
2. Review `/backend/logs/monitoring.log`
3. Access Flower dashboard: http://localhost:5555
4. Contact the development team

---

*Last updated: November 2024*
*Platform version: 1.0.0*