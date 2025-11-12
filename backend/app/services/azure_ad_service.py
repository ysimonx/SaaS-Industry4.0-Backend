"""
Azure AD Authentication Service

This service handles Azure AD / Microsoft Entra ID authentication using the
Web mode ( client_secret is required)  for enhanced security.

Key features:
- Token management (access, refresh, ID tokens)
- JWT validation and claims extraction
- Multi-tenant support with per-tenant configurations
"""

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any
from urllib.parse import urlencode, quote

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import current_app, session

from app.models import User, Tenant, TenantSSOConfig, UserAzureIdentity
from app.models.user_tenant_association import UserTenantAssociation
from app.extensions import db, redis_manager

logger = logging.getLogger(__name__)


class AzureADService:
    """
    Service for handling Azure AD authentication with PKCE.

    This service implements the OAuth2 Authorization Code Flow with PKCE
    as recommended for public applications (SPAs, mobile apps, etc.).
    """

    # Azure AD endpoints
    MICROSOFT_AUTHORITY = "https://login.microsoftonline.com"
    MICROSOFT_DISCOVERY_URL = "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"

    # OAuth2 scopes
    DEFAULT_SCOPES = [
        "openid",
        "profile",
        "email",
        "User.Read",
        "offline_access"  # REQUIRED to receive refresh_token from Azure AD
    ]

    def __init__(self, tenant_id: str = None):
        """
        Initialize Azure AD service.

        Args:
            tenant_id: Optional SaaS tenant ID to load configuration
        """
        self.tenant_id = tenant_id
        self.sso_config = None

        if tenant_id:
            self.sso_config = TenantSSOConfig.find_enabled_by_tenant_id(tenant_id)
            if not self.sso_config:
                logger.warning(f"No enabled SSO configuration found for tenant {tenant_id}")

    @staticmethod
    def generate_pkce_pair() -> Tuple[str, str]:
        """
        Generate PKCE code verifier and challenge for OAuth2 flow.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate a random code verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')

        # Generate code challenge using SHA256
        challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')

        logger.debug(f"Generated PKCE pair: verifier length={len(code_verifier)}, challenge length={len(code_challenge)}")

        return code_verifier, code_challenge

    @staticmethod
    def generate_state_token() -> str:
        """
        Generate a secure random state token for OAuth2 flow.

        Returns:
            Random state token
        """
        return secrets.token_urlsafe(32)

    def get_authorization_url(self, redirect_uri: str, state: str = None,
                            code_challenge: str = None, additional_params: Dict = None) -> str:
        """
        Generate Azure AD authorization URL with or without PKCE.

        Uses PKCE (Public Client) if no client_secret is configured.
        Uses traditional flow (Confidential Client) if client_secret exists.

        Args:
            redirect_uri: OAuth2 callback URL
            state: Optional state token (will be generated if not provided)
            additional_params: Additional query parameters

        Returns:
            Authorization URL for redirecting the user

        Raises:
            ValueError: If SSO configuration is not available
        """
        if not self.sso_config:
            raise ValueError("SSO configuration not available")

        if not state:
            state = self.generate_state_token()

        # Check if using client_secret (Confidential Client) or PKCE (Public Client)
        use_client_secret = self.sso_config.client_secret and self.sso_config.client_secret.strip()

        # Build authorization URL
        params = {
            'client_id': self.sso_config.client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'response_mode': 'query',
            'scope': ' '.join(self.DEFAULT_SCOPES),
            'state': state,
            'prompt': 'select_account'  # Allow user to select account
        }

        # Only add PKCE parameters if NOT using client_secret
        if not use_client_secret:
            if not code_challenge:
                _, code_challenge = self.generate_pkce_pair()
            params['code_challenge'] = code_challenge
            params['code_challenge_method'] = 'S256'
            logger.info(f"Using PKCE for authorization (Public Client mode)")
        else:
            logger.info(f"Using client_secret for authorization (Confidential Client mode)")

        # Add domain hint if email is provided
        if additional_params:
            if 'login_hint' in additional_params:
                params['login_hint'] = additional_params['login_hint']
            if 'domain_hint' in additional_params:
                params['domain_hint'] = additional_params['domain_hint']

        auth_url = f"{self.sso_config.get_authorization_url()}?{urlencode(params)}"

        logger.info(f"Generated authorization URL for tenant {self.tenant_id}")
        return auth_url

    def exchange_code_for_tokens(self, code: str, redirect_uri: str,
                                code_verifier: str) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens using PKCE.

        Args:
            code: Authorization code from Azure AD
            redirect_uri: Same redirect URI used in authorization request
            code_verifier: PKCE code verifier

        Returns:
            Dictionary with tokens (access_token, refresh_token, id_token)

        Raises:
            ValueError: If token exchange fails
        """
        if not self.sso_config:
            raise ValueError("SSO configuration not available")

        # Prepare token request
        token_data = {
            'client_id': self.sso_config.client_id,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'scope': ' '.join(self.DEFAULT_SCOPES)
        }

        # Add client_secret if configured (confidential app)
        # Otherwise use PKCE code_verifier (public app)
        # Check if client_secret exists and is not empty/None
        if self.sso_config.client_secret and self.sso_config.client_secret.strip():
            token_data['client_secret'] = self.sso_config.client_secret
            logger.info("Using client_secret for token exchange (confidential app)")
        else:
            token_data['code_verifier'] = code_verifier
            logger.info("Using PKCE code_verifier for token exchange (public app)")

        try:
            # Request tokens from Azure AD
            response = requests.post(
                self.sso_config.get_token_url(),
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_code = error_data.get('error', '')
                error_description = error_data.get('error_description', 'Unknown error')

                logger.error(f"Token exchange failed: {response.status_code} - {error_data}")

                # Provide specific guidance for common Azure AD errors
                if 'AADSTS9002327' in error_description:
                    raise ValueError(
                        "Azure AD app is configured as 'Single-Page Application'. "
                        "Please reconfigure it as 'Web' application in Azure Portal. "
                        "See AZURE_AD_CONFIGURATION_GUIDE.md for details."
                    )
                elif 'AADSTS7000218' in error_description:
                    raise ValueError(
                        "The application requires a client secret but none was provided. "
                        "Either add a client secret in Azure Portal or ensure the app "
                        "is configured for public client flow with PKCE."
                    )
                elif 'AADSTS50011' in error_description:
                    raise ValueError(
                        f"Redirect URI mismatch. Ensure the callback URL "
                        f"'{redirect_uri}' is registered in Azure Portal."
                    )

                raise ValueError(f"Token exchange failed: {error_description}")

            token_response = response.json()

            # Validate response has required tokens
            if 'access_token' not in token_response:
                raise ValueError("No access token in response")

            logger.info(f"Successfully exchanged code for tokens for tenant {self.tenant_id}")
            return token_response

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error during token exchange: {str(e)}")
            raise ValueError(f"Failed to connect to Azure AD: {str(e)}")

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            Dictionary with new tokens

        Raises:
            ValueError: If refresh fails
        """
        if not self.sso_config:
            raise ValueError("SSO configuration not available")

        # Prepare refresh request
        token_data = {
            'client_id': self.sso_config.client_id,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'scope': ' '.join(self.DEFAULT_SCOPES)
        }

        # Add client_secret if configured (confidential app)
        if self.sso_config.client_secret and self.sso_config.client_secret.strip():
            token_data['client_secret'] = self.sso_config.client_secret

        try:
            response = requests.post(
                self.sso_config.get_token_url(),
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_description = error_data.get('error_description', 'Unknown error')

                logger.error(f"Token refresh failed: {response.status_code} - {error_data}")

                # Provide specific guidance for common Azure AD errors
                if 'AADSTS9002327' in error_description:
                    raise ValueError(
                        "Azure AD app is configured as 'Single-Page Application'. "
                        "Please reconfigure it as 'Web' application in Azure Portal. "
                        "See AZURE_AD_CONFIGURATION_GUIDE.md for details."
                    )

                raise ValueError(f"Token refresh failed: {error_description}")

            token_response = response.json()
            logger.info(f"Successfully refreshed tokens for tenant {self.tenant_id}")
            return token_response

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error during token refresh: {str(e)}")
            raise ValueError(f"Failed to refresh token: {str(e)}")

    def validate_and_decode_id_token(self, id_token: str) -> Dict[str, Any]:
        """
        Validate and decode Azure AD ID token.

        Note: In production, you should validate the token signature using
        Azure AD's public keys from the discovery document.

        Args:
            id_token: JWT ID token from Azure AD

        Returns:
            Decoded token claims

        Raises:
            ValueError: If token validation fails
        """
        try:
            # Decode without verification for now (add signature verification in production)
            # In production, fetch keys from: https://login.microsoftonline.com/{tenant}/discovery/keys
            claims = jwt.decode(
                id_token,
                options={"verify_signature": False},  # TODO: Verify signature in production
                audience=self.sso_config.client_id if self.sso_config else None
            )

            # Validate required claims
            required_claims = ['oid', 'tid', 'email', 'name']
            missing_claims = [claim for claim in required_claims if claim not in claims]

            if missing_claims:
                # Email might be in 'preferred_username' or 'upn'
                if 'email' in missing_claims:
                    if 'preferred_username' in claims:
                        claims['email'] = claims['preferred_username']
                    elif 'upn' in claims:
                        claims['email'] = claims['upn']
                    else:
                        raise ValueError(f"Missing required claim: email")

            # Validate token is not expired
            if 'exp' in claims:
                exp_timestamp = claims['exp']
                if datetime.utcnow().timestamp() > exp_timestamp:
                    raise ValueError("ID token has expired")

            # Validate audience
            if self.sso_config and 'aud' in claims:
                if claims['aud'] != self.sso_config.client_id:
                    raise ValueError(f"Invalid audience: {claims['aud']}")

            # Validate issuer tenant
            if self.sso_config and 'tid' in claims:
                if claims['tid'] != self.sso_config.provider_tenant_id:
                    logger.warning(
                        f"Token tenant ID {claims['tid']} doesn't match "
                        f"configured tenant {self.sso_config.provider_tenant_id}"
                    )

            logger.info(f"Successfully validated ID token for user {claims.get('email')}")
            return claims

        except jwt.InvalidTokenError as e:
            logger.error(f"JWT validation error: {str(e)}")
            raise ValueError(f"Invalid ID token: {str(e)}")

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user information from Microsoft Graph API.

        Args:
            access_token: Valid access token

        Returns:
            User profile information

        Raises:
            ValueError: If API call fails
        """
        try:
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={'Authorization': f'Bearer {access_token}'}
            )

            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                logger.error(f"Graph API call failed: {response.status_code} - {error_data}")
                raise ValueError(f"Failed to get user info: {error_data.get('error', {}).get('message', 'Unknown error')}")

            user_info = response.json()
            logger.info(f"Retrieved user info for {user_info.get('userPrincipalName')}")
            return user_info

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error calling Graph API: {str(e)}")
            raise ValueError(f"Failed to get user info: {str(e)}")

    def process_sso_login(self, id_token_claims: Dict[str, Any],
                         tokens: Dict[str, str]) -> Tuple[User, UserAzureIdentity]:
        """
        Process SSO login - create or update user and Azure identity.

        Args:
            id_token_claims: Validated claims from ID token
            tokens: Dictionary with access_token, refresh_token, id_token

        Returns:
            Tuple of (User, UserAzureIdentity)

        Raises:
            ValueError: If processing fails
        """
        if not self.sso_config or not self.tenant_id:
            raise ValueError("SSO configuration not available")

        email = id_token_claims.get('email', '').lower()
        if not email:
            raise ValueError("No email in ID token")

        # Check if email domain is allowed
        if not self.sso_config.is_email_domain_allowed(email):
            raise ValueError(f"Email domain not allowed for SSO: {email}")

        # Load tenant
        tenant = Tenant.query.get(self.tenant_id)
        if not tenant:
            raise ValueError(f"Tenant not found: {self.tenant_id}")

        # Find or create user
        user = User.find_by_email(email)

        if not user:
            # Check if auto-provisioning is enabled
            auto_prov = self.sso_config.get_auto_provisioning_config()
            if not auto_prov.get('enabled', False):
                raise ValueError(f"User not found and auto-provisioning is disabled: {email}")

            # Extract first_name and last_name from claims
            # Azure AD peut fournir given_name/family_name ou juste name
            first_name = id_token_claims.get('given_name', '')
            last_name = id_token_claims.get('family_name', '')

            # Si given_name/family_name ne sont pas fournis, parser le champ 'name'
            if not first_name and not last_name:
                full_name = id_token_claims.get('name', '')
                if full_name:
                    name_parts = full_name.split(' ', 1)
                    first_name = name_parts[0] if len(name_parts) > 0 else ''
                    last_name = name_parts[1] if len(name_parts) > 1 else ''
                    logger.info(f"Parsed name '{full_name}' into first_name='{first_name}', last_name='{last_name}'")

            # Create new user (SSO-only, no password)
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=True
            )
            # No password for SSO-only user (password_hash is nullable)
            db.session.add(user)
            db.session.flush()  # Get user ID

            logger.info(f"Created new SSO user: {email}")

            # Create user-tenant association
            default_role = auto_prov.get('default_role', 'viewer')

            # Check for group-based role mapping
            if 'groups' in id_token_claims:
                user_groups = id_token_claims.get('groups', [])
                default_role = self.sso_config.get_role_from_azure_groups(user_groups)

            association = UserTenantAssociation(
                user_id=user.id,
                tenant_id=self.tenant_id,
                role=default_role
            )
            db.session.add(association)
            logger.info(f"Created user-tenant association with role: {default_role}")

        else:
            # Update existing user's info if sync is enabled
            if self.sso_config.get_auto_provisioning_config().get('sync_attributes_on_login', True):
                user.first_name = id_token_claims.get('given_name', user.first_name)
                user.last_name = id_token_claims.get('family_name', user.last_name)

            # Ensure user has access to this tenant
            if not user.has_access_to_tenant(self.tenant_id):
                # Check if auto-provisioning is enabled for existing users
                auto_prov = self.sso_config.get_auto_provisioning_config()
                if not auto_prov.get('enabled', False):
                    raise ValueError(f"User exists but has no access to tenant: {email}")

                # Add user to tenant
                default_role = auto_prov.get('default_role', 'viewer')
                association = UserTenantAssociation(
                    user_id=user.id,
                    tenant_id=self.tenant_id,
                    role=default_role
                )
                db.session.add(association)
                logger.info(f"Added existing user to tenant with role: {default_role}")

        # Create or update Azure identity
        azure_identity = UserAzureIdentity.find_or_create(
            user_id=user.id,
            tenant_id=self.tenant_id,
            azure_object_id=id_token_claims.get('oid'),
            azure_tenant_id=id_token_claims.get('tid'),
            azure_upn=id_token_claims.get('upn', email),
            azure_display_name=id_token_claims.get('name')
        )

        # Save tokens
        azure_identity.save_tokens(
            access_token=tokens.get('access_token'),
            refresh_token=tokens.get('refresh_token'),
            id_token=tokens.get('id_token'),
            expires_in=tokens.get('expires_in', 3600),
            refresh_expires_in=tokens.get('refresh_token_expires_in', 86400 * 7)
        )

        # Update from claims
        azure_identity.update_from_azure_claims(id_token_claims)

        # Update SSO metadata in azure_identity (not in user model)
        if not azure_identity.sso_metadata:
            azure_identity.sso_metadata = {}

        # Try to get profile info from Microsoft Graph API (more reliable)
        # Fall back to ID token claims if Graph API fails
        try:
            from app.services.microsoft_graph_service import microsoft_graph_service
            graph_profile = microsoft_graph_service.get_user_profile(tokens.get('access_token'))

            azure_identity.sso_metadata = {
                'job_title': graph_profile.get('jobTitle') or id_token_claims.get('jobTitle'),
                'department': graph_profile.get('department') or id_token_claims.get('department'),
                'company': id_token_claims.get('companyName'),  # Not available in Graph basic profile
                'office_location': graph_profile.get('officeLocation'),
                'mobile_phone': graph_profile.get('mobilePhone'),
                'last_sso_login': datetime.utcnow().isoformat()
            }
            logger.info(f"Updated SSO metadata from Microsoft Graph for {email}")
        except Exception as e:
            logger.warning(f"Failed to fetch Graph profile, using token claims only: {str(e)}")
            azure_identity.sso_metadata = {
                'job_title': id_token_claims.get('jobTitle'),
                'department': id_token_claims.get('department'),
                'company': id_token_claims.get('companyName'),
                'last_sso_login': datetime.utcnow().isoformat()
            }

        # Commit all changes
        db.session.commit()

        logger.info(f"Successfully processed SSO login for user {email} on tenant {self.tenant_id}")
        return user, azure_identity

    def initiate_logout(self, post_logout_redirect_uri: str = None) -> str:
        """
        Generate Azure AD logout URL.

        Args:
            post_logout_redirect_uri: URL to redirect after logout

        Returns:
            Logout URL
        """
        if not self.sso_config:
            raise ValueError("SSO configuration not available")

        params = {}
        if post_logout_redirect_uri:
            params['post_logout_redirect_uri'] = post_logout_redirect_uri

        logout_url = self.sso_config.get_logout_url()
        if params:
            logout_url = f"{logout_url}?{urlencode(params)}"

        return logout_url

    @staticmethod
    def store_pkce_in_session(code_verifier: Optional[str], state: str) -> None:
        """
        Store OAuth parameters in session for later verification.

        Stores code_verifier if using PKCE (Public Client).
        Stores only state if using client_secret (Confidential Client).

        Uses Redis if available, falls back to Flask session.

        Args:
            code_verifier: PKCE code verifier (None if using client_secret)
            state: OAuth2 state token
        """
        redis_client = redis_manager.get_client()

        if redis_client:
            # Store in Redis with TTL (10 minutes for OAuth flow)
            expire_time = current_app.config.get('REDIS_SESSION_EXPIRE', 600)
            session_data = {
                'code_verifier': code_verifier,
                'state': state,
                'timestamp': datetime.utcnow().isoformat()
            }

            # Use state as key for retrieval
            redis_key = f"sso_session:{state}"
            redis_client.setex(
                redis_key,
                expire_time,
                json.dumps(session_data)
            )

            # Also store state in Flask session for key retrieval
            session['oauth_state'] = state
            logger.info(f"Stored PKCE parameters in Redis with key: {redis_key}, state: {state[:10]}...")
        else:
            # Fallback to Flask session
            session['oauth_state'] = state
            session['oauth_code_verifier'] = code_verifier
            session['oauth_timestamp'] = datetime.utcnow().isoformat()
            logger.info(f"Stored PKCE parameters in Flask session, state: {state[:10]}...")
            logger.debug(f"Session keys after storing: {list(session.keys())}")

    @staticmethod
    def retrieve_pkce_from_session() -> Tuple[Optional[str], Optional[str]]:
        """
        Retrieve and clear PKCE parameters from session.

        Uses Redis if available, falls back to Flask session.

        Returns:
            Tuple of (code_verifier, state) or (None, None)
        """
        logger.info(f"Attempting to retrieve PKCE from session. Session keys: {list(session.keys())}")

        redis_client = redis_manager.get_client()

        # Get state from Flask session (always stored there)
        state = session.pop('oauth_state', None)

        logger.info(f"Retrieved state from Flask session: {state[:10] if state else 'None'}")

        if not state:
            logger.warning("No oauth_state found in Flask session")
            return None, None

        if redis_client:
            # Try to get from Redis
            redis_key = f"sso_session:{state}"
            session_data_str = redis_client.get(redis_key)

            if session_data_str:
                try:
                    session_data = json.loads(session_data_str)
                    code_verifier = session_data.get('code_verifier')

                    # Delete from Redis after retrieval
                    redis_client.delete(redis_key)

                    logger.info(f"Retrieved PKCE parameters from Redis and deleted key: {redis_key}, state: {state[:10]}...")
                    return code_verifier, state
                except json.JSONDecodeError:
                    logger.error("Failed to decode session data from Redis")
            else:
                logger.warning(f"No data found in Redis for key: {redis_key}")

        # Fallback to Flask session
        code_verifier = session.pop('oauth_code_verifier', None)
        session.pop('oauth_timestamp', None)

        if code_verifier and state:
            logger.info(f"Retrieved PKCE parameters from Flask session, state: {state[:10]}...")
            return code_verifier, state

        logger.warning(f"Failed to retrieve complete PKCE data. State: {state[:10] if state else 'None'}, Code verifier: {'Present' if code_verifier else 'None'}")
        return None, None

    @staticmethod
    def validate_state_token(received_state: str, stored_state: str) -> bool:
        """
        Validate OAuth2 state token to prevent CSRF attacks.

        Args:
            received_state: State token from callback
            stored_state: State token from session

        Returns:
            True if states match
        """
        if not received_state or not stored_state:
            logger.warning("Missing state token for validation")
            return False

        is_valid = secrets.compare_digest(received_state, stored_state)
        if not is_valid:
            logger.warning("State token mismatch - possible CSRF attempt")

        return is_valid