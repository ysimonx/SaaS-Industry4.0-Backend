"""
Standardized JSON response utilities for API endpoints.

Provides consistent response formats for success and error responses across all routes.
"""

from typing import Any, Dict, Optional, Union
from flask import jsonify, Response
from http import HTTPStatus


def success_response(
    data: Any = None,
    message: str = "Success",
    status_code: int = HTTPStatus.OK
) -> tuple[Response, int]:
    """
    Generate a standardized success response.

    Args:
        data: Response payload (dict, list, or any JSON-serializable data)
        message: Success message to include in response
        status_code: HTTP status code (default: 200 OK)

    Returns:
        Tuple of (JSON response, status code)

    Example:
        >>> return success_response({"user": user_dict}, "User created", 201)
        ({
            "success": true,
            "message": "User created",
            "data": {"user": {...}}
        }, 201)
    """
    response_body = {
        "success": True,
        "message": message,
    }

    if data is not None:
        response_body["data"] = data

    return jsonify(response_body), status_code


def error_response(
    code: str,
    message: str,
    details: Optional[Union[str, Dict[str, Any]]] = None,
    status_code: int = HTTPStatus.BAD_REQUEST
) -> tuple[Response, int]:
    """
    Generate a standardized error response.

    Args:
        code: Error code identifier (e.g., "AUTH_FAILED", "VALIDATION_ERROR")
        message: Human-readable error message
        details: Additional error details (string or dict with field-level errors)
        status_code: HTTP status code (default: 400 Bad Request)

    Returns:
        Tuple of (JSON response, status code)

    Example:
        >>> return error_response(
        ...     "VALIDATION_ERROR",
        ...     "Invalid input",
        ...     {"email": "Email is required"},
        ...     400
        ... )
        ({
            "success": false,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid input",
                "details": {"email": "Email is required"}
            }
        }, 400)
    """
    error_body = {
        "code": code,
        "message": message,
    }

    if details is not None:
        error_body["details"] = details

    response_body = {
        "success": False,
        "error": error_body,
    }

    return jsonify(response_body), status_code


# Convenience functions for common HTTP responses

def ok(data: Any = None, message: str = "Success") -> tuple[Response, int]:
    """
    200 OK response.

    Args:
        data: Response payload
        message: Success message

    Returns:
        Tuple of (JSON response, 200)
    """
    return success_response(data, message, HTTPStatus.OK)


def created(data: Any = None, message: str = "Resource created") -> tuple[Response, int]:
    """
    201 Created response.

    Args:
        data: Created resource data
        message: Success message

    Returns:
        Tuple of (JSON response, 201)
    """
    return success_response(data, message, HTTPStatus.CREATED)


def accepted(data: Any = None, message: str = "Request accepted") -> tuple[Response, int]:
    """
    202 Accepted response (for async operations).

    Args:
        data: Response payload
        message: Success message

    Returns:
        Tuple of (JSON response, 202)
    """
    return success_response(data, message, HTTPStatus.ACCEPTED)


def no_content(message: str = "No content") -> tuple[Response, int]:
    """
    204 No Content response.

    Args:
        message: Success message

    Returns:
        Tuple of (JSON response, 204)
    """
    return success_response(None, message, HTTPStatus.NO_CONTENT)


def bad_request(message: str, details: Optional[Union[str, Dict[str, Any]]] = None) -> tuple[Response, int]:
    """
    400 Bad Request error response.

    Args:
        message: Error message
        details: Additional error details

    Returns:
        Tuple of (JSON response, 400)
    """
    return error_response("BAD_REQUEST", message, details, HTTPStatus.BAD_REQUEST)


def unauthorized(message: str = "Authentication required", details: Optional[str] = None) -> tuple[Response, int]:
    """
    401 Unauthorized error response.

    Args:
        message: Error message
        details: Additional error details

    Returns:
        Tuple of (JSON response, 401)
    """
    return error_response("UNAUTHORIZED", message, details, HTTPStatus.UNAUTHORIZED)


def forbidden(message: str = "Access denied", details: Optional[str] = None) -> tuple[Response, int]:
    """
    403 Forbidden error response.

    Args:
        message: Error message
        details: Additional error details

    Returns:
        Tuple of (JSON response, 403)
    """
    return error_response("FORBIDDEN", message, details, HTTPStatus.FORBIDDEN)


def not_found(resource: str = "Resource", details: Optional[str] = None) -> tuple[Response, int]:
    """
    404 Not Found error response.

    Args:
        resource: Name of resource that was not found
        details: Additional error details

    Returns:
        Tuple of (JSON response, 404)
    """
    message = f"{resource} not found"
    return error_response("NOT_FOUND", message, details, HTTPStatus.NOT_FOUND)


def conflict(message: str, details: Optional[Union[str, Dict[str, Any]]] = None) -> tuple[Response, int]:
    """
    409 Conflict error response.

    Args:
        message: Error message
        details: Additional error details

    Returns:
        Tuple of (JSON response, 409)
    """
    return error_response("CONFLICT", message, details, HTTPStatus.CONFLICT)


def validation_error(message: str = "Validation failed", details: Optional[Dict[str, Any]] = None) -> tuple[Response, int]:
    """
    422 Unprocessable Entity error response (validation errors).

    Args:
        message: Error message
        details: Field-level validation errors

    Returns:
        Tuple of (JSON response, 422)

    Example:
        >>> return validation_error("Invalid input", {
        ...     "email": "Invalid email format",
        ...     "password": "Must be at least 8 characters"
        ... })
    """
    return error_response("VALIDATION_ERROR", message, details, HTTPStatus.UNPROCESSABLE_ENTITY)


def internal_error(message: str = "Internal server error", details: Optional[str] = None) -> tuple[Response, int]:
    """
    500 Internal Server Error response.

    Args:
        message: Error message
        details: Additional error details (avoid exposing sensitive info)

    Returns:
        Tuple of (JSON response, 500)
    """
    return error_response("INTERNAL_ERROR", message, details, HTTPStatus.INTERNAL_SERVER_ERROR)


def service_unavailable(message: str = "Service temporarily unavailable", details: Optional[str] = None) -> tuple[Response, int]:
    """
    503 Service Unavailable error response.

    Args:
        message: Error message
        details: Additional error details

    Returns:
        Tuple of (JSON response, 503)
    """
    return error_response("SERVICE_UNAVAILABLE", message, details, HTTPStatus.SERVICE_UNAVAILABLE)
