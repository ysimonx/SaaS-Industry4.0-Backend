"""
SSO Authentication Routes

This module provides API endpoints for Azure AD SSO authentication flow.
Implements OAuth2 Authorization Code Flow with PKCE for public applications.
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, redirect, session, current_app, url_for
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity
)

from app.models import User, Tenant, TenantSSOConfig, UserAzureIdentity
from app.services.azure_ad_service import AzureADService
from app.services.auth_service import AuthService
from app.extensions import db

logger = logging.getLogger(__name__)

bp = Blueprint('sso_auth', __name__, url_prefix='/api/auth/sso')


@bp.route('/azure/login/<string:tenant_id>', methods=['GET'])
def initiate_azure_login(tenant_id):
    """
    Initiate Azure AD login for a specific tenant.

    Query params:
        return_url: Optional URL to return to after successful login
        login_hint: Optional email hint for Azure AD

    Returns:
        Redirect to Azure AD authorization endpoint
    """
    try:
        # Check if tenant exists and has SSO enabled
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return jsonify({'error': 'Tenant not found'}), 404

        if tenant.auth_method not in ['sso', 'both']:
            return jsonify({'error': 'SSO not enabled for this tenant'}), 400

        # Get SSO configuration
        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(tenant_id)
        if not sso_config:
            return jsonify({'error': 'No active SSO configuration found'}), 404

        # Initialize Azure AD service
        azure_service = AzureADService(tenant_id)

        # Generate state token (always needed for CSRF protection)
        state = azure_service.generate_state_token()

        # Check if using client_secret (Confidential) or PKCE (Public)
        use_client_secret = sso_config.client_secret and sso_config.client_secret.strip()

        # Generate PKCE parameters only if NOT using client_secret
        code_verifier = None
        code_challenge = None
        if not use_client_secret:
            code_verifier, code_challenge = azure_service.generate_pkce_pair()
            logger.info("Using PKCE (Public Client mode)")
        else:
            logger.info("Using client_secret (Confidential Client mode)")

        # Store parameters in session
        azure_service.store_pkce_in_session(code_verifier, state)
        session['sso_tenant_id'] = tenant_id
        session['return_url'] = request.args.get('return_url')

        # Build redirect URI - use the configured redirect_uri from SSO config
        # This ensures consistency with what's configured in Azure AD
        redirect_uri = sso_config.redirect_uri
        logger.info(f"Using configured redirect URI: {redirect_uri}")

        # Additional parameters
        additional_params = {}
        if 'login_hint' in request.args:
            additional_params['login_hint'] = request.args['login_hint']

        # Generate authorization URL
        auth_url = azure_service.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,  # Will be None if using client_secret
            additional_params=additional_params
        )

        logger.info(f"Initiating Azure AD login for tenant {tenant_id}")
        logger.info(f"Generated auth URL: {auth_url}")

        # Safety check: Ensure URL doesn't contain HTML entities
        if '&amp;' in auth_url:
            logger.error(f"WARNING: Generated URL contains HTML entities: {auth_url}")
            # Fix the URL by replacing HTML entities
            auth_url = auth_url.replace('&amp;', '&')
            logger.info(f"Fixed auth URL: {auth_url}")

        return redirect(auth_url)

    except Exception as e:
        logger.error(f"Error initiating Azure login: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/azure/callback', methods=['GET'])
def azure_callback():
    """
    Handle Azure AD OAuth2 callback.

    Query params (from Azure AD):
        code: Authorization code
        state: State token for CSRF protection
        error: Error code if authorization failed
        error_description: Error details

    Returns:
        Redirect to application with JWT tokens or error
    """
    try:
        # Check for errors from Azure AD
        error = request.args.get('error')
        if error:
            error_description = request.args.get('error_description', 'Unknown error')
            logger.error(f"Azure AD error: {error} - {error_description}")
            return jsonify({
                'error': error,
                'description': error_description
            }), 400

        # Get authorization code
        code = request.args.get('code')
        if not code:
            return jsonify({'error': 'No authorization code received'}), 400

        # Validate state token
        received_state = request.args.get('state')
        code_verifier, stored_state = AzureADService.retrieve_pkce_from_session()

        if not AzureADService.validate_state_token(received_state, stored_state):
            return jsonify({'error': 'Invalid state token - possible CSRF attack'}), 400

        # Get tenant ID from session
        tenant_id = session.pop('sso_tenant_id', None)
        return_url = session.pop('return_url', None)

        if not tenant_id:
            return jsonify({'error': 'No tenant ID in session'}), 400

        # Initialize Azure AD service
        azure_service = AzureADService(tenant_id)

        # Get SSO config to use the configured redirect_uri
        from app.models import TenantSSOConfig
        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(tenant_id)
        if not sso_config:
            return jsonify({'error': 'SSO configuration not found'}), 404

        # Exchange code for tokens - use configured redirect_uri for consistency
        redirect_uri = sso_config.redirect_uri
        logger.info(f"Using configured redirect URI for token exchange: {redirect_uri}")

        token_response = azure_service.exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier
        )

        # Validate and decode ID token
        id_token_claims = azure_service.validate_and_decode_id_token(
            token_response.get('id_token')
        )

        # Process SSO login (create/update user and Azure identity)
        user, azure_identity = azure_service.process_sso_login(
            id_token_claims=id_token_claims,
            tokens=token_response
        )

        # Create JWT tokens for our application
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                'email': user.email,
                'tenant_id': tenant_id,
                'auth_method': 'sso'
            },
            expires_delta=timedelta(minutes=15)
        )

        refresh_token = create_refresh_token(
            identity=str(user.id),
            additional_claims={
                'email': user.email,
                'tenant_id': tenant_id,
                'auth_method': 'sso'
            },
            expires_delta=timedelta(days=7)
        )

        # Build response
        response_data = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(),
            'tenant_id': tenant_id,
            'auth_method': 'sso'
        }

        # If return_url is provided, redirect there with tokens
        if return_url:
            # In production, you might want to pass tokens differently (e.g., via cookies)
            import urllib.parse
            params = urllib.parse.urlencode({
                'access_token': access_token,
                'refresh_token': refresh_token
            })
            return redirect(f"{return_url}?{params}")

        return jsonify(response_data), 200

    except ValueError as e:
        logger.error(f"SSO login error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Unexpected error in Azure callback: {str(e)}")
        return jsonify({'error': 'Authentication failed'}), 500


@bp.route('/azure/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh_azure_tokens():
    """
    Refresh Azure AD tokens using stored refresh token.

    Returns:
        New access token
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Get tenant ID from request
        data = request.get_json()
        tenant_id = data.get('tenant_id')
        if not tenant_id:
            return jsonify({'error': 'Tenant ID required'}), 400

        # Get user's Azure identity for this tenant
        azure_identity = user.get_azure_identity_for_tenant(tenant_id)
        if not azure_identity:
            return jsonify({'error': 'No Azure identity found for user'}), 404

        # Get decrypted tokens
        tokens = azure_identity.get_decrypted_tokens()
        refresh_token = tokens.get('refresh_token')
        if not refresh_token:
            return jsonify({'error': 'No refresh token available'}), 400

        # Initialize Azure AD service
        azure_service = AzureADService(tenant_id)

        # Refresh tokens
        token_response = azure_service.refresh_access_token(refresh_token)

        # Save new tokens
        azure_identity.save_tokens(
            access_token=token_response.get('access_token'),
            refresh_token=token_response.get('refresh_token', refresh_token),
            id_token=token_response.get('id_token', tokens.get('id_token')),
            expires_in=token_response.get('expires_in', 3600)
        )

        db.session.commit()

        # Create new JWT access token
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                'email': user.email,
                'tenant_id': tenant_id,
                'auth_method': 'sso'
            },
            expires_delta=timedelta(minutes=15)
        )

        return jsonify({
            'access_token': access_token,
            'expires_in': 900  # 15 minutes
        }), 200

    except Exception as e:
        logger.error(f"Error refreshing Azure tokens: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/azure/logout/<string:tenant_id>', methods=['POST'])
@jwt_required()
def azure_logout(tenant_id):
    """
    Logout from Azure AD and clear tokens.

    Request body:
        {
            "post_logout_redirect_uri": "https://app.example.com/logout-complete"
        }

    Returns:
        Azure AD logout URL or success message
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Get user's Azure identity for this tenant
        azure_identity = user.get_azure_identity_for_tenant(tenant_id)
        if azure_identity:
            # Clear stored tokens
            azure_identity.clear_tokens()
            db.session.commit()

        # Blacklist current JWT token
        # AuthService.blacklist_token(get_jwt())  # Implement if needed

        # Get post-logout redirect URI from request
        data = request.get_json() or {}
        post_logout_redirect_uri = data.get('post_logout_redirect_uri')

        # Generate Azure AD logout URL
        azure_service = AzureADService(tenant_id)
        logout_url = azure_service.initiate_logout(post_logout_redirect_uri)

        return jsonify({
            'message': 'Logout successful',
            'logout_url': logout_url
        }), 200

    except Exception as e:
        logger.error(f"Error during Azure logout: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/azure/user-info', methods=['GET'])
@jwt_required()
def get_azure_user_info():
    """
    Get user information from Microsoft Graph API.

    Query params:
        tenant_id: Tenant ID to use for Azure identity

    Returns:
        User profile from Microsoft Graph
    """
    try:
        current_user_id = get_jwt_identity()
        tenant_id = request.args.get('tenant_id')

        if not tenant_id:
            return jsonify({'error': 'Tenant ID required'}), 400

        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Get user's Azure identity
        azure_identity = user.get_azure_identity_for_tenant(tenant_id)
        if not azure_identity:
            return jsonify({'error': 'No Azure identity found'}), 404

        # Check if token is expired
        if azure_identity.is_access_token_expired():
            return jsonify({'error': 'Access token expired, please refresh'}), 401

        # Get decrypted access token
        tokens = azure_identity.get_decrypted_tokens()
        access_token = tokens.get('access_token')
        if not access_token:
            return jsonify({'error': 'No access token available'}), 400

        # Initialize Azure AD service and get user info
        azure_service = AzureADService(tenant_id)
        user_info = azure_service.get_user_info(access_token)

        return jsonify(user_info), 200

    except Exception as e:
        logger.error(f"Error getting Azure user info: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/detect', methods=['POST'])
def detect_sso():
    """
    Detect SSO provider based on email domain.

    Checks if the user's email domain has SSO configured in any tenant.
    Used in login flow to redirect users to SSO automatically.

    Request body:
        {
            "email": "user@company.com"
        }

    Returns:
        {
            "has_sso": true,
            "tenants": [
                {
                    "tenant_id": "uuid",
                    "tenant_name": "Acme Corp",
                    "provider": "azure_ad",
                    "login_url": "/api/auth/sso/azure/login/uuid"
                }
            ]
        }
    """
    try:
        data = request.get_json()
        if not data or 'email' not in data:
            return jsonify({
                'error': 'Email is required'
            }), 400

        email = data['email'].lower().strip()

        # Extract domain from email
        if '@' not in email:
            return jsonify({
                'error': 'Invalid email format'
            }), 400

        domain = '@' + email.split('@')[1]

        # Find tenants with this domain in their whitelist
        matching_tenants = []

        # Query tenants that have SSO enabled and this domain in their whitelist
        tenants = Tenant.query.filter(
            Tenant.auth_method.in_(['sso', 'both']),
            Tenant.is_active == True,
            Tenant.sso_domain_whitelist.contains([domain])
        ).all()

        for tenant in tenants:
            # Check if SSO is properly configured
            sso_config = TenantSSOConfig.find_enabled_by_tenant_id(tenant.id)
            if sso_config:
                # Validate configuration
                is_valid, _ = sso_config.validate_configuration()
                if is_valid:
                    matching_tenants.append({
                        'tenant_id': str(tenant.id),
                        'tenant_name': tenant.name,
                        'provider': sso_config.provider_type,
                        'login_url': f"/api/auth/sso/{sso_config.provider_type}/login/{tenant.id}"
                    })

        return jsonify({
            'has_sso': len(matching_tenants) > 0,
            'tenants': matching_tenants
        }), 200

    except Exception as e:
        logger.error(f"Error detecting SSO: {str(e)}")
        return jsonify({'error': 'Failed to detect SSO configuration'}), 500


@bp.route('/check-availability/<string:tenant_id>', methods=['GET'])
def check_sso_availability(tenant_id):
    """
    Check if SSO is available and configured for a tenant.

    Returns:
        SSO availability status
    """
    try:
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return jsonify({
                'available': False,
                'error': 'Tenant not found'
            }), 404

        # Check if SSO is enabled
        if tenant.auth_method not in ['sso', 'both']:
            return jsonify({
                'available': False,
                'auth_method': tenant.auth_method,
                'message': 'SSO not enabled for this tenant'
            }), 200

        # Check if SSO is configured
        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(tenant_id)
        if not sso_config:
            return jsonify({
                'available': False,
                'auth_method': tenant.auth_method,
                'message': 'SSO configuration not found or disabled'
            }), 200

        # Validate configuration
        is_valid, error_msg = sso_config.validate_configuration()

        # Build SSO login URL if available
        sso_login_url = None
        if is_valid:
            sso_login_url = url_for('sso_auth.initiate_azure_login',
                                   tenant_id=tenant_id,
                                   _external=True)

        return jsonify({
            'available': is_valid,
            'auth_method': tenant.auth_method,
            'provider': sso_config.provider_type,
            'auto_provisioning': tenant.sso_auto_provisioning,
            'sso_login_url': sso_login_url,
            'error': error_msg if not is_valid else None
        }), 200

    except Exception as e:
        logger.error(f"Error checking SSO availability: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/identities', methods=['GET'])
@jwt_required()
def get_user_azure_identities():
    """
    Get all Azure identities for the current user.

    Returns:
        List of Azure identities across all tenants
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        identities = []
        for identity in user.azure_identities:
            tenant = Tenant.query.get(identity.tenant_id)
            identities.append({
                'tenant_id': str(identity.tenant_id),
                'tenant_name': tenant.name if tenant else 'Unknown',
                'azure_tenant_id': identity.azure_tenant_id,
                'azure_object_id': identity.azure_object_id,
                'azure_upn': identity.azure_upn,
                'last_sync': identity.last_sync.isoformat() if identity.last_sync else None,
                'token_expired': identity.is_access_token_expired()
            })

        return jsonify({
            'identities': identities,
            'total': len(identities)
        }), 200

    except Exception as e:
        logger.error(f"Error getting user Azure identities: {str(e)}")
        return jsonify({'error': str(e)}), 500