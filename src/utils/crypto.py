"""Cryptographic utilities for API signing."""

import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


def load_private_key_from_file(file_path: str) -> rsa.RSAPrivateKey:
    """
    Load RSA private key from PEM file.

    Args:
        file_path: Path to PEM file

    Returns:
        RSA private key object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    with open(file_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend()
        )
    return private_key


def load_private_key_from_string(key_string: str) -> rsa.RSAPrivateKey:
    """
    Load RSA private key from PEM string.

    Args:
        key_string: PEM-formatted key string

    Returns:
        RSA private key object

    Raises:
        ValueError: If format is invalid
    """
    private_key = serialization.load_pem_private_key(
        key_string.encode('utf-8'),
        password=None,
        backend=default_backend()
    )
    return private_key


def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
    """
    Sign text using RSA-PSS signature scheme.

    Args:
        private_key: RSA private key
        text: Text to sign

    Returns:
        Base64-encoded signature

    Raises:
        ValueError: If signing fails
    """
    message = text.encode('utf-8')
    try:
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode('utf-8')
    except InvalidSignature as e:
        raise ValueError("RSA sign PSS failed") from e
