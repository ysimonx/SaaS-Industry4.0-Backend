"""
API routes for monitoring and health status
"""

from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from app.monitoring.healthchecks_client import healthchecks
from app.tasks.monitoring_tasks import (
    comprehensive_health_check,
    check_postgres_health,
    check_redis_health,
    check_api_health,
    check_celery_health,
    check_kafka_health,
    check_minio_health,
    check_vault_health
)
from app.utils.decorators import role_required
from app.models.user_tenant_association import UserTenantAssociation

logger = logging.getLogger(__name__)

monitoring_bp = Blueprint('monitoring', __name__)


@monitoring_bp.route('/health', methods=['GET'])
def health():
    """
    Basic health check endpoint (no authentication required)

    Returns:
        JSON with service health status
    """
    return jsonify({
        'status': 'healthy',
        'service': 'monitoring',
        'monitoring_enabled': healthchecks.enabled
    }), 200


@monitoring_bp.route('/status', methods=['GET'])
@jwt_required()
@role_required(['admin'])
def get_monitoring_status():
    """
    Get comprehensive monitoring status
    Requires admin role

    Returns:
        JSON with detailed monitoring status from Healthchecks
    """
    try:
        # Get status from Healthchecks
        if not healthchecks.enabled:
            return jsonify({
                'status': 'disabled',
                'message': 'Monitoring is not enabled'
            }), 200

        status = healthchecks.get_status()
        if not status:
            return jsonify({
                'status': 'error',
                'message': 'Could not retrieve monitoring status'
            }), 500

        return jsonify({
            'status': 'active',
            'monitoring_enabled': True,
            'healthchecks_url': 'http://localhost:8000',
            'summary': {
                'total_checks': status.get('total', 0),
                'healthy': status.get('up', 0),
                'down': status.get('down', 0),
                'paused': status.get('paused', 0),
                'new': status.get('new', 0)
            },
            'checks': status.get('checks', [])
        }), 200

    except Exception as e:
        logger.error(f"Error getting monitoring status: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@monitoring_bp.route('/check/<service>', methods=['GET'])
@jwt_required()
@role_required(['admin', 'user'])
def check_service_health(service):
    """
    Check health of a specific service

    Args:
        service: Service name (postgres, redis, api, celery, kafka, minio, vault)

    Returns:
        JSON with service health details
    """
    try:
        service_checks = {
            'postgres': check_postgres_health,
            'redis': check_redis_health,
            'api': check_api_health,
            'celery': check_celery_health,
            'kafka': check_kafka_health,
            'minio': check_minio_health,
            'vault': check_vault_health
        }

        if service not in service_checks:
            return jsonify({
                'error': f'Unknown service: {service}',
                'available_services': list(service_checks.keys())
            }), 400

        # Execute the health check synchronously
        result = service_checks[service]()

        return jsonify({
            'service': service,
            'result': result
        }), 200

    except Exception as e:
        logger.error(f"Error checking {service} health: {str(e)}")
        return jsonify({
            'service': service,
            'status': 'error',
            'error': str(e)
        }), 500


@monitoring_bp.route('/check/all', methods=['GET'])
@jwt_required()
@role_required(['admin'])
def check_all_services():
    """
    Run comprehensive health check on all services
    Requires admin role

    Returns:
        JSON with comprehensive health check results
    """
    try:
        # Run comprehensive check
        result = comprehensive_health_check()

        return jsonify({
            'timestamp': result.get('timestamp'),
            'overall_status': result.get('overall_status'),
            'healthy_services': result.get('healthy_services'),
            'total_services': result.get('total_services'),
            'services': result.get('services', {}),
            'errors': result.get('errors', []),
            'healthchecks_summary': result.get('healthchecks_summary', {})
        }), 200

    except Exception as e:
        logger.error(f"Error running comprehensive health check: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@monitoring_bp.route('/checks', methods=['GET'])
@jwt_required()
@role_required(['admin'])
def list_checks():
    """
    List all configured Healthchecks
    Requires admin role

    Returns:
        JSON with list of all checks
    """
    try:
        if not healthchecks.enabled:
            return jsonify({
                'status': 'disabled',
                'message': 'Monitoring is not enabled'
            }), 200

        checks = healthchecks.list_checks()

        return jsonify({
            'total': len(checks),
            'checks': checks
        }), 200

    except Exception as e:
        logger.error(f"Error listing checks: {str(e)}")
        return jsonify({
            'error': str(e)
        }), 500


@monitoring_bp.route('/checks/<check_id>/pause', methods=['POST'])
@jwt_required()
@role_required(['admin'])
def pause_check(check_id):
    """
    Pause a specific health check
    Requires admin role

    Args:
        check_id: UUID of the check to pause

    Returns:
        JSON with operation result
    """
    try:
        if not healthchecks.enabled:
            return jsonify({
                'status': 'disabled',
                'message': 'Monitoring is not enabled'
            }), 200

        success = healthchecks.pause_check(check_id)

        if success:
            return jsonify({
                'status': 'success',
                'message': f'Check {check_id} paused'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': f'Failed to pause check {check_id}'
            }), 500

    except Exception as e:
        logger.error(f"Error pausing check {check_id}: {str(e)}")
        return jsonify({
            'error': str(e)
        }), 500


@monitoring_bp.route('/checks/<check_id>/resume', methods=['POST'])
@jwt_required()
@role_required(['admin'])
def resume_check(check_id):
    """
    Resume a paused health check
    Requires admin role

    Args:
        check_id: UUID of the check to resume

    Returns:
        JSON with operation result
    """
    try:
        if not healthchecks.enabled:
            return jsonify({
                'status': 'disabled',
                'message': 'Monitoring is not enabled'
            }), 200

        success = healthchecks.resume_check(check_id)

        if success:
            return jsonify({
                'status': 'success',
                'message': f'Check {check_id} resumed'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': f'Failed to resume check {check_id}'
            }), 500

    except Exception as e:
        logger.error(f"Error resuming check {check_id}: {str(e)}")
        return jsonify({
            'error': str(e)
        }), 500


@monitoring_bp.route('/dashboard', methods=['GET'])
@jwt_required()
@role_required(['admin', 'user'])
def monitoring_dashboard():
    """
    Get monitoring dashboard data

    Returns:
        JSON with dashboard-friendly monitoring data
    """
    try:
        # Get basic status
        status = healthchecks.get_status() if healthchecks.enabled else None

        # Prepare dashboard data
        dashboard_data = {
            'monitoring_enabled': healthchecks.enabled,
            'timestamp': datetime.utcnow().isoformat()
        }

        if status:
            # Calculate health percentage
            total = status.get('total', 0)
            up = status.get('up', 0)
            health_percentage = (up / total * 100) if total > 0 else 0

            dashboard_data.update({
                'health_percentage': round(health_percentage, 2),
                'summary': {
                    'total_checks': total,
                    'healthy': up,
                    'down': status.get('down', 0),
                    'paused': status.get('paused', 0)
                },
                'recent_failures': [
                    check for check in status.get('checks', [])
                    if check.get('status') == 'down'
                ][:5],  # Last 5 failures
                'healthchecks_url': 'http://localhost:8000'
            })

        return jsonify(dashboard_data), 200

    except Exception as e:
        logger.error(f"Error getting dashboard data: {str(e)}")
        return jsonify({
            'error': str(e)
        }), 500