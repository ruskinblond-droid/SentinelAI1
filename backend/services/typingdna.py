"""
SentinelAI - TypingDNA Authentication API Service Wrapper

Provides a clean, server-side interface to communicate with the official
TypingDNA Authentication API (https://api.typingdna.com).

Security & Privacy Guarantees:
- API credentials are read strictly from environment variables.
- API credentials and raw typing patterns are NEVER returned to callers,
  never exposed in API responses, and never printed to logs.
- User identity is pseudonymized using the project standard identifier:
  `usr_sentinel_<zero-padded-id>`. Raw emails or passwords are never sent.
- All HTTP calls enforce a strict 5-second timeout.
"""

import base64
import json
import logging
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Union
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Base API Configuration
TYPINGDNA_BASE_URL = "https://api.typingdna.com"
DEFAULT_TIMEOUT_SECONDS = 5.0


# =====================================================================
# Exceptions Hierarchy
# =====================================================================

class TypingDNAError(Exception):
    """Base exception for all TypingDNA service errors."""
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class TypingDNAConfigError(TypingDNAError):
    """Raised when TypingDNA API credentials are not configured in the environment."""
    def __init__(self, message: str = "TypingDNA API credentials (TYPINGDNA_API_KEY, TYPINGDNA_API_SECRET) are not configured"):
        super().__init__(message, status_code=500)


class TypingDNAAuthError(TypingDNAError):
    """Raised when TypingDNA returns HTTP 401 Unauthorized (invalid API credentials)."""
    def __init__(self, message: str = "TypingDNA authentication failed: invalid API key or secret"):
        super().__init__(message, status_code=401)


class TypingDNATimeoutError(TypingDNAError):
    """Raised when a request to the TypingDNA API times out."""
    def __init__(self, message: str = "TypingDNA request timed out"):
        super().__init__(message, status_code=504)


class TypingDNAConnectionError(TypingDNAError):
    """Raised when a network connection failure occurs when communicating with TypingDNA."""
    def __init__(self, message: str = "Failed to connect to TypingDNA API"):
        super().__init__(message, status_code=502)


class TypingDNAHTTPError(TypingDNAError):
    """Raised when TypingDNA returns an HTTP error code (e.g. 400 Bad Request, 500 Internal Server Error)."""
    def __init__(self, message: str, status_code: int = 400, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=status_code, details=details)


class TypingDNAAPIError(TypingDNAError):
    """Raised when TypingDNA returns HTTP 200 but includes success=0 in the JSON response body."""
    def __init__(self, message: str, status_code: int = 400, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=status_code, details=details)


class TypingDNAMalformedResponseError(TypingDNAError):
    """Raised when TypingDNA returns a non-JSON or unparseable response body."""
    def __init__(self, message: str = "TypingDNA returned a malformed response", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=502, details=details)


# =====================================================================
# Helper Functions
# =====================================================================

def is_configured() -> bool:
    """
    Check if TypingDNA API credentials are set in the environment.
    """
    api_key = os.getenv("TYPINGDNA_API_KEY")
    api_secret = os.getenv("TYPINGDNA_API_SECRET")
    return bool(api_key and api_key.strip() and api_secret and api_secret.strip())


def get_typingdna_user_id(user_id: Union[int, str]) -> str:
    """
    Generate a deterministic, pseudonymized TypingDNA user identifier.
    Guarantees no emails, real names, or sensitive information are sent to TypingDNA.

    Format: usr_sentinel_<zero-padded-id> (e.g. 1 -> 'usr_sentinel_000001')
    """
    if isinstance(user_id, int):
        return f"usr_sentinel_{user_id:06d}"
    if isinstance(user_id, str):
        trimmed = user_id.strip()
        if trimmed.startswith("usr_sentinel_"):
            return trimmed
        try:
            parsed = int(trimmed)
            return f"usr_sentinel_{parsed:06d}"
        except ValueError:
            return f"usr_sentinel_{trimmed}"
    raise ValueError(f"Unsupported user_id type: {type(user_id)}")


def _get_credentials() -> tuple[str, str]:
    """
    Retrieve and validate API credentials from environment variables.
    """
    api_key = os.getenv("TYPINGDNA_API_KEY")
    api_secret = os.getenv("TYPINGDNA_API_SECRET")

    if not api_key or not api_key.strip() or not api_secret or not api_secret.strip():
        logger.error("TypingDNA API credentials missing in environment")
        raise TypingDNAConfigError()

    return api_key.strip(), api_secret.strip()


def _execute_request(
    endpoint: str,
    user_id: Union[int, str],
    typing_pattern: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """
    Low-level HTTP helper to execute a POST request against TypingDNA API.

    - Uses HTTPS
    - Uses HTTP Basic Authentication (apiKey:apiSecret)
    - Sends Content-Type: application/x-www-form-urlencoded
    - Request body: tp=<typing_pattern>
    """
    api_key, api_secret = _get_credentials()
    tdna_id = get_typingdna_user_id(user_id)

    if not typing_pattern or not typing_pattern.strip():
        raise TypingDNAError("Typing pattern cannot be empty", status_code=400)

    url = f"{TYPINGDNA_BASE_URL}/{endpoint}/{urllib.parse.quote(tdna_id)}"

    # Construct form-urlencoded body: tp=<pattern>
    form_data = urllib.parse.urlencode({"tp": typing_pattern.strip()}).encode("utf-8")

    # Basic Auth Header
    auth_bytes = f"{api_key}:{api_secret}".encode("utf-8")
    auth_header = f"Basic {base64.b64encode(auth_bytes).decode('ascii')}"

    req = urllib.request.Request(
        url=url,
        data=form_data,
        method="POST"
    )
    req.add_header("Authorization", auth_header)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "SentinelAI-Backend/1.0")

    logger.info("Sending TypingDNA request: endpoint=%s, user_id=%s", endpoint, tdna_id)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.getcode()
            raw_body = response.read()
    except urllib.error.HTTPError as e:
        status_code = e.code
        error_body = ""
        try:
            error_body = e.read().decode("utf-8", errors="replace")
            parsed_err = json.loads(error_body)
        except Exception:
            parsed_err = {"raw": error_body}

        if status_code == 401:
            logger.error("TypingDNA HTTP 401: Invalid credentials for endpoint=%s", endpoint)
            raise TypingDNAAuthError()
        elif status_code == 400:
            msg = parsed_err.get("message") if isinstance(parsed_err, dict) else error_body
            logger.error("TypingDNA HTTP 400 Bad Request: %s", msg)
            raise TypingDNAHTTPError(
                f"TypingDNA Bad Request: {msg}",
                status_code=400,
                details=parsed_err if isinstance(parsed_err, dict) else None
            )
        else:
            logger.error("TypingDNA HTTP error: status=%d", status_code)
            raise TypingDNAHTTPError(
                f"TypingDNA returned HTTP {status_code}",
                status_code=status_code,
                details=parsed_err if isinstance(parsed_err, dict) else None
            )
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)) or "timed out" in str(e.reason).lower():
            logger.warning("TypingDNA request timed out after %s seconds for user_id=%s", timeout, tdna_id)
            raise TypingDNATimeoutError()
        logger.error("TypingDNA connection failure: %s", type(e.reason).__name__)
        raise TypingDNAConnectionError(f"Failed to connect to TypingDNA: {e.reason}")
    except (socket.timeout, TimeoutError):
        logger.warning("TypingDNA request timed out after %s seconds for user_id=%s", timeout, tdna_id)
        raise TypingDNATimeoutError()
    except TypingDNAError:
        raise
    except Exception as e:
        logger.error("Unexpected error communicating with TypingDNA: %s", type(e).__name__)
        raise TypingDNAError(f"Unexpected error communicating with TypingDNA: {str(e)}", status_code=500)

    # Parse JSON response
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.error("TypingDNA returned unparseable response")
        raise TypingDNAMalformedResponseError(details={"raw": raw_body.decode("utf-8", errors="replace")})

    if not isinstance(payload, dict):
        logger.error("TypingDNA returned non-dictionary JSON payload")
        raise TypingDNAMalformedResponseError(details={"payload": payload})

    # Check for TypingDNA API-level error (success == 0)
    if payload.get("success") == 0:
        api_msg = payload.get("message", "TypingDNA operation failed")
        api_status = payload.get("status", 400)
        logger.warning("TypingDNA API error: %s (status=%s)", api_msg, api_status)
        raise TypingDNAAPIError(
            message=f"TypingDNA API error: {api_msg}",
            status_code=int(api_status) if isinstance(api_status, (int, float)) else 400,
            details=payload
        )

    return payload


# =====================================================================
# Public Service Interface
# =====================================================================

def save_pattern(
    user_id: Union[int, str],
    typing_pattern: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """
    Enroll a user typing pattern with TypingDNA.
    Target endpoint: POST https://api.typingdna.com/save/:id

    Returns normalized dictionary:
    {
        "success": bool,
        "status": int,
        "message": str,
        "count": Optional[int]
    }
    """
    raw_response = _execute_request(
        endpoint="save",
        user_id=user_id,
        typing_pattern=typing_pattern,
        timeout=timeout
    )

    # Normalize response
    return {
        "success": bool(raw_response.get("success") == 1),
        "status": int(raw_response.get("status", 200)),
        "message": str(raw_response.get("message", "Pattern saved successfully")),
        "count": raw_response.get("count")
    }


def verify_pattern(
    user_id: Union[int, str],
    typing_pattern: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """
    Verify a typing pattern against the user's enrolled profile on TypingDNA.
    Target endpoint: POST https://api.typingdna.com/verify/:id

    Returns normalized dictionary:
    {
        "success": bool,
        "result": int,              # 1 = match, 0 = non-match
        "score": float,             # raw score (0-100)
        "net_score": Optional[float],# net score if provided
        "confidence": Optional[Any],# confidence level if provided
        "effective_score": float,   # net_score if available else score
        "status": int,
        "message": str
    }
    """
    raw_response = _execute_request(
        endpoint="verify",
        user_id=user_id,
        typing_pattern=typing_pattern,
        timeout=timeout
    )

    # Safely extract scores without assuming net_score/confidence exist
    try:
        score_val = float(raw_response.get("score", 0.0))
    except (ValueError, TypeError):
        score_val = 0.0

    net_score_val = None
    if "net_score" in raw_response and raw_response["net_score"] is not None:
        try:
            net_score_val = float(raw_response["net_score"])
        except (ValueError, TypeError):
            net_score_val = None

    effective_score = net_score_val if net_score_val is not None else score_val

    confidence_val = raw_response.get("confidence")

    try:
        result_val = int(raw_response.get("result", 0))
    except (ValueError, TypeError):
        result_val = 0

    return {
        "success": bool(raw_response.get("success") == 1),
        "result": result_val,
        "score": score_val,
        "net_score": net_score_val,
        "confidence": confidence_val,
        "effective_score": effective_score,
        "status": int(raw_response.get("status", 200)),
        "message": str(raw_response.get("message", "Pattern verified"))
    }
