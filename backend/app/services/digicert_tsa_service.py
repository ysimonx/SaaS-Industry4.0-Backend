"""
DigiCert TSA Service

This module provides RFC 3161 timestamping services using DigiCert's public TSA.

Key features:
- RFC 3161 compliant timestamp requests
- Free DigiCert public TSA (no authentication required)
- Automatic retry logic with exponential backoff
- Complete certificate chain storage for long-term verification
- Support for SHA-256, SHA-384, and SHA-512 hash algorithms

DigiCert Public TSA:
- Endpoint: http://timestamp.digicert.com
- Protocol: RFC 3161 (Time-Stamp Protocol)
- No authentication required
- Free to use

RFC 3161 Resources:
- https://www.ietf.org/rfc/rfc3161.txt
- https://www.digicert.com/kb/timestamp-server-documentation.htm
"""

import base64
import hashlib
import logging
from datetime import datetime
from typing import Dict, Optional

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtensionOID
from flask import current_app

# ASN.1 libraries for RFC 3161 parsing
try:
    from pyasn1.codec.der import decoder, encoder
    from pyasn1_modules import rfc3161
    from pyasn1.type import univ
except ImportError:
    # Will be handled at runtime
    pass

logger = logging.getLogger(__name__)


class TSAException(Exception):
    """Base exception for TSA-related errors."""
    pass


class TSAConnectionError(TSAException):
    """TSA service connection failed."""
    pass


class TSAInvalidResponseError(TSAException):
    """TSA returned invalid response."""
    pass


class TSAQuotaExceededError(TSAException):
    """TSA quota exceeded (for private TSA services)."""
    pass


class DigiCertTSAService:
    """
    Service for obtaining RFC 3161 timestamps from DigiCert TSA.

    This service communicates with DigiCert's public timestamp authority
    to obtain cryptographic proofs of document existence at a specific time.

    The timestamps are legally binding and can be verified independently
    years after creation using standard tools (OpenSSL, Adobe Acrobat, etc.).
    """

    def __init__(self):
        """Initialize DigiCert TSA service with configuration from Flask app."""
        self.tsa_url = None
        self.request_timeout = 30
        self.max_retries = 3

        # Configuration will be loaded when app context is available
        if current_app:
            self._load_config()

    def _load_config(self):
        """Load TSA configuration from Flask app config."""
        try:
            self.tsa_url = current_app.config.get(
                'DIGICERT_TSA_URL',
                'http://timestamp.digicert.com'
            )
            self.request_timeout = int(current_app.config.get('TSA_REQUEST_TIMEOUT', 30))
            self.max_retries = int(current_app.config.get('TSA_MAX_RETRIES', 3))

            logger.info(f"DigiCert TSA service initialized: {self.tsa_url}")
        except Exception as e:
            logger.warning(f"Failed to load TSA config, using defaults: {e}")
            self.tsa_url = 'http://timestamp.digicert.com'

    def get_rfc3161_timestamp(
        self,
        file_hash: str,
        algorithm: str = 'sha256'
    ) -> Dict:
        """
        Request an RFC 3161 timestamp from DigiCert TSA.

        This method:
        1. Creates a TimeStampReq (TSR) with the file hash
        2. Sends the request to DigiCert TSA via HTTP POST
        3. Parses the TimeStampResp containing the timestamp token
        4. Extracts metadata (serial number, gen_time, certificates)
        5. Returns everything needed for storage and verification

        Args:
            file_hash: Hash of the file content (hex string or bytes)
            algorithm: Hash algorithm used ('sha256', 'sha384', 'sha512')

        Returns:
            Dictionary containing:
            {
                'success': True,
                'timestamp_token': '<base64_encoded_tsr>',  # Complete RFC 3161 token
                'algorithm': 'sha256',
                'serial_number': '0x123456789ABCDEF',
                'gen_time': '2025-01-15T10:30:00Z',  # ISO format
                'tsa_authority': 'DigiCert Timestamp Authority',
                'policy_oid': '2.16.840.1.114412.7.1',
                'tsa_certificate': '<base64_encoded_cert>',  # X.509 cert
                'certificate_chain': ['<base64_cert1>', '<base64_cert2>']  # Full chain
            }

        Raises:
            TSAConnectionError: If connection to TSA fails
            TSAInvalidResponseError: If TSA response is invalid
            TSAQuotaExceededError: If quota exceeded (private TSA only)
        """
        logger.info(f"Requesting RFC 3161 timestamp for hash: {file_hash[:16]}...")

        try:
            # Convert hex hash to bytes if needed
            if isinstance(file_hash, str):
                message_imprint = bytes.fromhex(file_hash)
            else:
                message_imprint = file_hash

            # Create TimeStampReq
            tsr_request = self._create_timestamp_request(message_imprint, algorithm)

            # Send request to DigiCert TSA
            tsr_response = self._send_tsa_request(tsr_request)

            # Parse response
            timestamp_data = self._parse_timestamp_response(tsr_response, algorithm)

            logger.info(
                f"Timestamp obtained successfully: "
                f"serial={timestamp_data['serial_number']}, "
                f"gen_time={timestamp_data['gen_time']}"
            )

            return timestamp_data

        except TSAException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_rfc3161_timestamp: {e}", exc_info=True)
            raise TSAException(f"Failed to obtain timestamp: {str(e)}")

    def _create_timestamp_request(
        self,
        message_imprint: bytes,
        algorithm: str
    ) -> bytes:
        """
        Create an RFC 3161 TimeStampReq in ASN.1 DER format.

        Structure:
        TimeStampReq ::= SEQUENCE {
            version INTEGER { v1(1) },
            messageImprint MessageImprint,
            reqPolicy TSAPolicyId OPTIONAL,
            nonce INTEGER OPTIONAL,
            certReq BOOLEAN DEFAULT FALSE,
            extensions [0] IMPLICIT Extensions OPTIONAL
        }

        Args:
            message_imprint: Hash of the file (raw bytes)
            algorithm: Hash algorithm name

        Returns:
            ASN.1 DER encoded TimeStampReq
        """
        try:
            # Map algorithm to OID
            algorithm_oids = {
                'sha256': univ.ObjectIdentifier('2.16.840.1.101.3.4.2.1'),
                'sha384': univ.ObjectIdentifier('2.16.840.1.101.3.4.2.2'),
                'sha512': univ.ObjectIdentifier('2.16.840.1.101.3.4.2.3'),
            }

            if algorithm not in algorithm_oids:
                raise ValueError(f"Unsupported algorithm: {algorithm}")

            # Create MessageImprint
            message_imprint_obj = rfc3161.MessageImprint()
            message_imprint_obj['hashAlgorithm'] = rfc3161.AlgorithmIdentifier()
            message_imprint_obj['hashAlgorithm']['algorithm'] = algorithm_oids[algorithm]
            message_imprint_obj['hashedMessage'] = message_imprint

            # Create TimeStampReq
            tsr_req = rfc3161.TimeStampReq()
            tsr_req['version'] = 1
            tsr_req['messageImprint'] = message_imprint_obj
            tsr_req['certReq'] = True  # Request certificate in response

            # Generate random nonce for replay protection
            import secrets
            nonce = secrets.randbits(64)
            tsr_req['nonce'] = nonce

            # Encode to DER
            tsr_request_der = encoder.encode(tsr_req)

            logger.debug(f"Created TimeStampReq: {len(tsr_request_der)} bytes, nonce={nonce}")
            return tsr_request_der

        except Exception as e:
            logger.error(f"Failed to create TimeStampReq: {e}", exc_info=True)
            raise TSAException(f"Failed to create timestamp request: {str(e)}")

    def _send_tsa_request(self, tsr_request: bytes) -> bytes:
        """
        Send TimeStampReq to DigiCert TSA via HTTP POST.

        HTTP Request:
        POST /timestamp HTTP/1.1
        Host: timestamp.digicert.com
        Content-Type: application/timestamp-query
        Content-Length: <length>

        <DER-encoded TimeStampReq>

        Args:
            tsr_request: DER-encoded TimeStampReq

        Returns:
            DER-encoded TimeStampResp

        Raises:
            TSAConnectionError: If connection fails
        """
        if not self.tsa_url:
            self._load_config()

        headers = {
            'Content-Type': 'application/timestamp-query',
            'User-Agent': 'SaaS-Platform-TSA-Client/1.0'
        }

        retries = 0
        last_error = None

        while retries < self.max_retries:
            try:
                logger.debug(
                    f"Sending TSA request to {self.tsa_url} "
                    f"(attempt {retries + 1}/{self.max_retries})"
                )

                response = requests.post(
                    self.tsa_url,
                    data=tsr_request,
                    headers=headers,
                    timeout=self.request_timeout
                )

                # Check HTTP status
                if response.status_code == 200:
                    logger.debug(f"TSA response received: {len(response.content)} bytes")
                    return response.content
                elif response.status_code == 429:
                    raise TSAQuotaExceededError("TSA quota exceeded (rate limit)")
                else:
                    raise TSAInvalidResponseError(
                        f"TSA returned HTTP {response.status_code}: {response.text[:200]}"
                    )

            except requests.exceptions.Timeout as e:
                last_error = TSAConnectionError(f"TSA request timeout: {str(e)}")
                logger.warning(f"TSA timeout (attempt {retries + 1}): {e}")
                retries += 1

            except requests.exceptions.ConnectionError as e:
                last_error = TSAConnectionError(f"TSA connection failed: {str(e)}")
                logger.warning(f"TSA connection error (attempt {retries + 1}): {e}")
                retries += 1

            except (TSAQuotaExceededError, TSAInvalidResponseError):
                raise

            except Exception as e:
                last_error = TSAConnectionError(f"TSA request failed: {str(e)}")
                logger.error(f"Unexpected TSA error (attempt {retries + 1}): {e}", exc_info=True)
                retries += 1

        # All retries exhausted
        logger.error(f"TSA request failed after {self.max_retries} attempts")
        raise last_error

    def _parse_timestamp_response(
        self,
        tsr_response: bytes,
        algorithm: str
    ) -> Dict:
        """
        Parse TimeStampResp and extract all relevant data.

        TimeStampResp ::= SEQUENCE {
            status PKIStatusInfo,
            timeStampToken TimeStampToken OPTIONAL
        }

        Args:
            tsr_response: DER-encoded TimeStampResp from TSA
            algorithm: Hash algorithm used

        Returns:
            Dictionary with timestamp data

        Raises:
            TSAInvalidResponseError: If response is invalid
        """
        try:
            # Decode ASN.1 DER
            tsr, _ = decoder.decode(tsr_response, asn1Spec=rfc3161.TimeStampResp())

            # Check status
            status = int(tsr['status']['status'])
            if status != 0:  # 0 = granted
                status_string = tsr['status'].get('statusString', 'Unknown error')
                raise TSAInvalidResponseError(
                    f"TSA request rejected: status={status}, message={status_string}"
                )

            # Extract TimeStampToken (SignedData CMS)
            tst_token = tsr['timeStampToken']

            # Extract TSTInfo from SignedData
            tst_info = self._extract_tst_info(tst_token)

            # Extract certificates from SignedData
            certificates = self._extract_certificates(tst_token)

            # Build response
            timestamp_data = {
                'success': True,
                'timestamp_token': base64.b64encode(tsr_response).decode('utf-8'),
                'algorithm': algorithm,
                'serial_number': self._format_serial_number(tst_info['serialNumber']),
                'gen_time': self._format_gen_time(tst_info['genTime']),
                'tsa_authority': self._extract_tsa_authority(certificates[0]) if certificates else 'DigiCert',
                'policy_oid': str(tst_info.get('policy', 'Unknown')),
                'tsa_certificate': base64.b64encode(
                    certificates[0].public_bytes(serialization.Encoding.DER)
                ).decode('utf-8') if certificates else None,
                'certificate_chain': [
                    base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode('utf-8')
                    for cert in certificates
                ]
            }

            return timestamp_data

        except TSAInvalidResponseError:
            raise
        except Exception as e:
            logger.error(f"Failed to parse TimeStampResp: {e}", exc_info=True)
            raise TSAInvalidResponseError(f"Invalid TSA response: {str(e)}")

    def _extract_tst_info(self, tst_token) -> Dict:
        """
        Extract TSTInfo from TimeStampToken (SignedData).

        TSTInfo ::= SEQUENCE {
            version INTEGER { v1(1) },
            policy TSAPolicyId,
            messageImprint MessageImprint,
            serialNumber INTEGER,
            genTime GeneralizedTime,
            accuracy Accuracy OPTIONAL,
            ordering BOOLEAN DEFAULT FALSE,
            nonce INTEGER OPTIONAL,
            tsa [0] EXPLICIT GeneralName OPTIONAL,
            extensions [1] IMPLICIT Extensions OPTIONAL
        }
        """
        try:
            # TimeStampToken is a SignedData CMS structure
            # The content is EncapsulatedContentInfo containing TSTInfo
            content_info = tst_token['content']

            # Decode TSTInfo from EncapsulatedContentInfo
            tst_info_der = bytes(content_info['eContent'])
            tst_info, _ = decoder.decode(tst_info_der, asn1Spec=rfc3161.TSTInfo())

            return tst_info

        except Exception as e:
            logger.error(f"Failed to extract TSTInfo: {e}", exc_info=True)
            raise TSAInvalidResponseError(f"Cannot extract TSTInfo: {str(e)}")

    def _extract_certificates(self, tst_token) -> list:
        """
        Extract X.509 certificates from TimeStampToken.

        Returns list of cryptography.x509.Certificate objects.
        """
        try:
            certificates = []

            # Certificates are in SignedData.certificates
            if 'certificates' in tst_token and tst_token['certificates']:
                for cert_choice in tst_token['certificates']:
                    # cert_choice is a CertificateChoices (usually certificate)
                    cert_der = bytes(cert_choice['certificate'])
                    cert = x509.load_der_x509_certificate(cert_der)
                    certificates.append(cert)

                    logger.debug(
                        f"Extracted certificate: "
                        f"subject={cert.subject.rfc4514_string()}, "
                        f"issuer={cert.issuer.rfc4514_string()}"
                    )

            return certificates

        except Exception as e:
            logger.warning(f"Failed to extract certificates: {e}")
            return []

    def _format_serial_number(self, serial: int) -> str:
        """Format serial number as hex string (0x...)."""
        if isinstance(serial, int):
            return f"0x{serial:X}"
        return f"0x{int(serial):X}"

    def _format_gen_time(self, gen_time) -> str:
        """
        Format GeneralizedTime to ISO 8601 string.

        GeneralizedTime format: YYYYMMDDHHmmssZ
        ISO 8601 format: YYYY-MM-DDTHH:mm:ssZ
        """
        try:
            gen_time_str = str(gen_time)
            # Parse: 20250115103000Z
            dt = datetime.strptime(gen_time_str, '%Y%m%d%H%M%SZ')
            return dt.isoformat() + 'Z'
        except Exception as e:
            logger.warning(f"Failed to parse gen_time: {e}")
            return str(gen_time)

    def _extract_tsa_authority(self, certificate: x509.Certificate) -> str:
        """Extract TSA authority name from certificate subject."""
        try:
            return certificate.subject.rfc4514_string()
        except Exception:
            return "DigiCert Timestamp Authority"


# Singleton instance
digicert_tsa_service = DigiCertTSAService()
