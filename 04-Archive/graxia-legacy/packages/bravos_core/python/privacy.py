import re
from typing import Final

# Regex patterns for PII scrubbing
EMAIL_REGEX: Final[str] = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
# Supports 13-16 digits with spaces or hyphens
CC_REGEX: Final[str] = r"\b(?:\d[ -]*?){13,16}\b"
# Supports various formats: +1-555-555-5555, (555) 555-5555, 555-5555, etc.
PHONE_REGEX: Final[str] = r"(?:\+?\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}|\b\d{3}[- ]\d{4}\b"

class PrivacyScrubber:
    """
    Enterprise-grade PII scrubber for cleaning sensitive information from text logs and outputs.
    """

    @staticmethod
    def scrub(text: str) -> str:
        """
        Scrubs common PII from the provided text.
        
        Args:
            text: The input string containing potential PII.
            
        Returns:
            The scrubbed string with PII replaced by redaction markers.
        """
        if not text:
            return text

        # Scrub emails
        text = re.sub(EMAIL_REGEX, "[REDACTED_EMAIL]", text)
        
        # Scrub credit card numbers
        text = re.sub(CC_REGEX, "[REDACTED_CC]", text)
        
        # Scrub phone numbers
        text = re.sub(PHONE_REGEX, "[REDACTED_PHONE]", text)

        return text

def scrub_pii(text: str) -> str:
    """
    Convenience function for scrubbing PII.
    """
    return PrivacyScrubber.scrub(text)
