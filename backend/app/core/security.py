"""
Security Module

Provides encryption, input sanitization, and security utilities.
"""
import hashlib
import logging
import re
from typing import Optional

from cryptography.fernet import Fernet
from app.config import settings

logger = logging.getLogger(__name__)


class SecurityManager:
    """
    Security manager for encryption and input sanitization.
    
    Features:
    - API key encryption (AES-256)
    - Input sanitization (prompt injection protection)
    - PII anonymization
    - Password hashing
    """
    
    def __init__(self):
        # Generate or load encryption key
        self.encryption_key = self._get_or_create_key()
        self.cipher = Fernet(self.encryption_key)
    
    def _get_or_create_key(self) -> bytes:
        """Get or create encryption key."""
        key = settings.ENCRYPTION_KEY
        if not key:
            # Generate new key
            key = Fernet.generate_key()
            logger.warning("Generated new encryption key. Save this to ENCRYPTION_KEY env var!")
            logger.warning(f"ENCRYPTION_KEY={key.decode()}")
        else:
            key = key.encode() if isinstance(key, str) else key
        
        return key
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext string.
        
        Args:
            plaintext: String to encrypt
        
        Returns:
            Encrypted string (base64 encoded)
        """
        try:
            encrypted = self.cipher.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt ciphertext string.
        
        Args:
            ciphertext: Encrypted string (base64 encoded)
        
        Returns:
            Decrypted plaintext string
        """
        try:
            decrypted = self.cipher.decrypt(ciphertext.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise
    
    def sanitize_input(self, text: str, max_length: int = 5000) -> str:
        """
        Sanitize user input to prevent prompt injection.
        
        Removes:
        - System prompts (system:, assistant:, user:)
        - Code blocks (```)
        - HTML/script tags
        - Control characters
        
        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length
        
        Returns:
            Sanitized text
        """
        if not text:
            return ""
        
        # Remove system prompts
        text = re.sub(r'(system:|assistant:|user:)', '', text, flags=re.IGNORECASE)
        
        # Remove code blocks
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        
        # Remove HTML/script tags
        text = re.sub(r'<script.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<.*?>', '', text)
        
        # Remove control characters
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        
        # Limit length
        text = text[:max_length]
        
        return text.strip()
    
    def anonymize_email(self, email: str) -> str:
        """
        Anonymize email address.
        
        Args:
            email: Email address
        
        Returns:
            Anonymized email (user_<hash>@example.com)
        """
        if not email or '@' not in email:
            return "anonymous@example.com"
        
        # Hash email
        email_hash = hashlib.sha256(email.encode()).hexdigest()[:8]
        return f"user_{email_hash}@example.com"
    
    def anonymize_name(self, name: str, entity_id: str) -> str:
        """
        Anonymize person name.
        
        Args:
            name: Person name
            entity_id: Unique entity ID
        
        Returns:
            Anonymized name (Person_<id>)
        """
        if not name:
            return "Anonymous"
        
        # Use entity ID for consistency
        return f"Person_{entity_id[:8]}"
    
    def anonymize_phone(self, phone: str) -> str:
        """
        Anonymize phone number.
        
        Args:
            phone: Phone number
        
        Returns:
            Anonymized phone (+XX-XXX-XXXX)
        """
        if not phone:
            return "+XX-XXX-XXXX"
        
        # Keep country code, mask rest
        digits = re.sub(r'\D', '', phone)
        if len(digits) >= 10:
            return f"+{digits[0:2]}-XXX-{digits[-4:]}"
        
        return "+XX-XXX-XXXX"
    
    def hash_password(self, password: str) -> str:
        """
        Hash password using bcrypt.
        
        Args:
            password: Plain password
        
        Returns:
            Hashed password
        """
        import bcrypt
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            password: Plain password
            hashed: Hashed password
        
        Returns:
            True if password matches
        """
        import bcrypt
        return bcrypt.checkpw(password.encode(), hashed.encode())
    
    def validate_api_key(self, api_key: str) -> bool:
        """
        Validate API key format.
        
        Args:
            api_key: API key to validate
        
        Returns:
            True if valid format
        """
        if not api_key:
            return False
        
        # Check length (at least 32 characters)
        if len(api_key) < 32:
            return False
        
        # Check alphanumeric + special chars
        if not re.match(r'^[a-zA-Z0-9_\-\.]+$', api_key):
            return False
        
        return True
    
    def mask_api_key(self, api_key: str) -> str:
        """
        Mask API key for logging.
        
        Args:
            api_key: API key to mask
        
        Returns:
            Masked key (sk-...xyz)
        """
        if not api_key or len(api_key) < 8:
            return "***"
        
        return f"{api_key[:3]}...{api_key[-3:]}"


# Global instance
security_manager = SecurityManager()
