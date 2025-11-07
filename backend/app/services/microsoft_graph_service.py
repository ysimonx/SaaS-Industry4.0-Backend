"""
Microsoft Graph API Service

This service handles all interactions with Microsoft Graph API for Azure AD SSO.
Provides methods to fetch user profiles, group memberships, and validate tokens.
"""

import logging
from typing import Dict, Any, List, Optional
import requests
from datetime import datetime, timedelta
from flask import current_app

from app.utils.exceptions import (
    SSOError,
    UnauthorizedException,
    ExternalServiceError
)

logger = logging.getLogger(__name__)


class MicrosoftGraphService:
    """Service for interacting with Microsoft Graph API"""

    # Microsoft Graph API endpoints
    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    AUTH_BASE_URL = "https://login.microsoftonline.com"

    # Required scopes for Microsoft Graph
    DEFAULT_SCOPES = [
        "openid",
        "profile",
        "email",
        "User.Read",
        "offline_access"  # For refresh tokens
    ]

    # Optional scopes for enhanced features
    ENHANCED_SCOPES = [
        "GroupMember.Read.All",  # For group-based role mapping
        "Directory.Read.All"      # For advanced directory queries
    ]

    def __init__(self):
        """Initialize the Microsoft Graph service"""
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    def get_user_profile(
        self,
        access_token: str
    ) -> Dict[str, Any]:
        """
        Get user profile information from Microsoft Graph.

        Args:
            access_token: Valid Azure AD access token

        Returns:
            Dict containing user profile information:
                - id: Azure AD object ID
                - displayName: Full name
                - mail: Primary email address
                - userPrincipalName: UPN (usually email)
                - givenName: First name
                - surname: Last name
                - jobTitle: Job title (if available)
                - department: Department (if available)

        Raises:
            UnauthorizedException: If token is invalid
            ExternalServiceError: If Graph API request fails
        """
        try:
            response = self.session.get(
                f"{self.GRAPH_BASE_URL}/me",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )

            if response.status_code == 401:
                raise UnauthorizedException("Invalid or expired access token")

            if response.status_code != 200:
                logger.error(f"Graph API error: {response.status_code} - {response.text}")
                raise ExternalServiceError(
                    f"Failed to fetch user profile: {response.status_code}"
                )

            profile = response.json()

            # Normalize the response
            return {
                "id": profile.get("id"),
                "displayName": profile.get("displayName"),
                "mail": profile.get("mail") or profile.get("userPrincipalName"),
                "userPrincipalName": profile.get("userPrincipalName"),
                "givenName": profile.get("givenName"),
                "surname": profile.get("surname"),
                "jobTitle": profile.get("jobTitle"),
                "department": profile.get("department"),
                "officeLocation": profile.get("officeLocation"),
                "mobilePhone": profile.get("mobilePhone")
            }

        except requests.exceptions.Timeout:
            logger.error("Graph API request timed out")
            raise ExternalServiceError("Microsoft Graph API timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"Graph API request failed: {str(e)}")
            raise ExternalServiceError(f"Microsoft Graph API error: {str(e)}")

    def get_user_groups(
        self,
        access_token: str
    ) -> List[Dict[str, Any]]:
        """
        Get user's group memberships from Microsoft Graph.

        Args:
            access_token: Valid Azure AD access token

        Returns:
            List of group dictionaries containing:
                - id: Group object ID
                - displayName: Group name
                - description: Group description
                - mail: Group email (if mail-enabled)

        Raises:
            UnauthorizedException: If token is invalid or lacks permissions
            ExternalServiceError: If Graph API request fails
        """
        try:
            response = self.session.get(
                f"{self.GRAPH_BASE_URL}/me/memberOf",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"$select": "id,displayName,description,mail"},
                timeout=10
            )

            if response.status_code == 401:
                raise UnauthorizedException("Invalid or expired access token")

            if response.status_code == 403:
                # User doesn't have permission to read groups
                logger.warning("Insufficient permissions to read user groups")
                return []

            if response.status_code != 200:
                logger.error(f"Graph API error: {response.status_code} - {response.text}")
                raise ExternalServiceError(
                    f"Failed to fetch user groups: {response.status_code}"
                )

            data = response.json()
            groups = []

            for item in data.get("value", []):
                if item.get("@odata.type") == "#microsoft.graph.group":
                    groups.append({
                        "id": item.get("id"),
                        "displayName": item.get("displayName"),
                        "description": item.get("description"),
                        "mail": item.get("mail")
                    })

            return groups

        except requests.exceptions.Timeout:
            logger.error("Graph API request timed out")
            raise ExternalServiceError("Microsoft Graph API timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"Graph API request failed: {str(e)}")
            raise ExternalServiceError(f"Microsoft Graph API error: {str(e)}")

    def get_user_photo(
        self,
        access_token: str,
        size: str = "48x48"
    ) -> Optional[bytes]:
        """
        Get user's profile photo from Microsoft Graph.

        Args:
            access_token: Valid Azure AD access token
            size: Photo size (48x48, 64x64, 96x96, 120x120, 240x240, 360x360, 432x432, 504x504, 648x648)

        Returns:
            Photo bytes or None if no photo exists

        Raises:
            ExternalServiceError: If Graph API request fails
        """
        try:
            response = self.session.get(
                f"{self.GRAPH_BASE_URL}/me/photos/{size}/$value",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )

            if response.status_code == 404:
                # No photo available
                return None

            if response.status_code == 200:
                return response.content

            logger.warning(f"Failed to fetch user photo: {response.status_code}")
            return None

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch user photo: {str(e)}")
            return None

    def validate_token(
        self,
        access_token: str
    ) -> Dict[str, Any]:
        """
        Validate an access token with Microsoft Graph.

        Args:
            access_token: Token to validate

        Returns:
            Dict with validation results:
                - valid: True if token is valid
                - expires_at: Token expiration datetime
                - scopes: List of granted scopes

        Raises:
            ExternalServiceError: If validation fails
        """
        try:
            # Try to get basic user info to validate token
            response = self.session.get(
                f"{self.GRAPH_BASE_URL}/me",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"$select": "id"},
                timeout=5
            )

            if response.status_code == 401:
                return {
                    "valid": False,
                    "expires_at": None,
                    "scopes": []
                }

            if response.status_code == 200:
                # Parse token to get expiration (simplified - in production use proper JWT library)
                # For now, assume token is valid for 1 hour from validation
                return {
                    "valid": True,
                    "expires_at": datetime.utcnow() + timedelta(hours=1),
                    "scopes": self.DEFAULT_SCOPES  # Would need to parse from token
                }

            raise ExternalServiceError(f"Token validation failed: {response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Token validation failed: {str(e)}")
            raise ExternalServiceError(f"Token validation error: {str(e)}")

    def refresh_access_token(
        self,
        tenant_id: str,
        client_id: str,
        refresh_token: str
    ) -> Dict[str, Any]:
        """
        Refresh an access token using a refresh token.

        Args:
            tenant_id: Azure AD tenant ID
            client_id: Azure AD application client ID
            refresh_token: Valid refresh token

        Returns:
            Dict containing:
                - access_token: New access token
                - refresh_token: New refresh token (may be rotated)
                - expires_in: Token lifetime in seconds

        Raises:
            UnauthorizedException: If refresh token is invalid
            ExternalServiceError: If token refresh fails
        """
        try:
            token_url = f"{self.AUTH_BASE_URL}/{tenant_id}/oauth2/v2.0/token"

            data = {
                "client_id": client_id,
                "scope": " ".join(self.DEFAULT_SCOPES),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }

            response = self.session.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10
            )

            if response.status_code == 400:
                error_data = response.json()
                if "invalid_grant" in error_data.get("error", ""):
                    raise UnauthorizedException("Refresh token expired or revoked")
                raise SSOError(f"Token refresh failed: {error_data.get('error_description', 'Unknown error')}")

            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                raise ExternalServiceError(f"Failed to refresh token: {response.status_code}")

            token_data = response.json()

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token", refresh_token),  # May not always return new refresh token
                "expires_in": token_data.get("expires_in", 3600),
                "token_type": token_data.get("token_type", "Bearer"),
                "scope": token_data.get("scope", "")
            }

        except requests.exceptions.Timeout:
            logger.error("Token refresh request timed out")
            raise ExternalServiceError("Azure AD token refresh timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"Token refresh request failed: {str(e)}")
            raise ExternalServiceError(f"Token refresh error: {str(e)}")

    def get_tenant_info(
        self,
        access_token: str
    ) -> Dict[str, Any]:
        """
        Get information about the user's Azure AD tenant.

        Args:
            access_token: Valid Azure AD access token

        Returns:
            Dict containing tenant information:
                - id: Tenant ID
                - displayName: Tenant display name
                - verifiedDomains: List of verified domains

        Raises:
            UnauthorizedException: If token is invalid
            ExternalServiceError: If Graph API request fails
        """
        try:
            response = self.session.get(
                f"{self.GRAPH_BASE_URL}/organization",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )

            if response.status_code == 401:
                raise UnauthorizedException("Invalid or expired access token")

            if response.status_code == 403:
                # User doesn't have permission to read organization info
                logger.warning("Insufficient permissions to read organization info")
                return {}

            if response.status_code != 200:
                logger.error(f"Graph API error: {response.status_code} - {response.text}")
                raise ExternalServiceError(
                    f"Failed to fetch tenant info: {response.status_code}"
                )

            data = response.json()
            if data.get("value") and len(data["value"]) > 0:
                org = data["value"][0]
                return {
                    "id": org.get("id"),
                    "displayName": org.get("displayName"),
                    "verifiedDomains": org.get("verifiedDomains", [])
                }

            return {}

        except requests.exceptions.Timeout:
            logger.error("Graph API request timed out")
            raise ExternalServiceError("Microsoft Graph API timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"Graph API request failed: {str(e)}")
            raise ExternalServiceError(f"Microsoft Graph API error: {str(e)}")

    def batch_request(
        self,
        access_token: str,
        requests_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple Graph API requests in a single batch.

        Args:
            access_token: Valid Azure AD access token
            requests_data: List of request dictionaries with:
                - id: Request identifier
                - method: HTTP method (GET, POST, etc.)
                - url: Relative URL path
                - body: Optional request body
                - headers: Optional request headers

        Returns:
            List of response dictionaries

        Raises:
            ExternalServiceError: If batch request fails
        """
        try:
            batch_data = {
                "requests": requests_data
            }

            response = self.session.post(
                f"{self.GRAPH_BASE_URL}/$batch",
                headers={"Authorization": f"Bearer {access_token}"},
                json=batch_data,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Batch request failed: {response.status_code} - {response.text}")
                raise ExternalServiceError(f"Batch request failed: {response.status_code}")

            batch_response = response.json()
            return batch_response.get("responses", [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Batch request failed: {str(e)}")
            raise ExternalServiceError(f"Batch request error: {str(e)}")


# Singleton instance
microsoft_graph_service = MicrosoftGraphService()