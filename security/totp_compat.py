"""Minimal RFC 6238 SHA-1 TOTP implementation for fully offline demo environments.

If pyotp is installed it is preferred. This implementation uses constant-time
comparison; the shared public demo secret MUST be replaced in deployments.
"""
import base64
import hashlib
import hmac
import struct
from datetime import datetime

class TOTP:
    def __init__(self, secret: str, interval: int = 30, digits: int = 6):
        self.secret = base64.b32decode(secret.upper() + '=' * (-len(secret) % 8))
        self.interval = interval
        self.digits = digits

    def at(self, for_time: datetime) -> str:
        counter = int(for_time.timestamp()) // self.interval
        digest = hmac.new(self.secret, struct.pack('>Q', counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        number = (struct.unpack('>I', digest[offset:offset+4])[0] & 0x7FFFFFFF) % (10**self.digits)
        return str(number).zfill(self.digits)

    def verify(self, otp: str, for_time: datetime, valid_window: int = 0) -> bool:
        if not isinstance(otp, str) or len(otp) != self.digits or not otp.isdigit():
            return False
        return any(hmac.compare_digest(otp, self.at(datetime.fromtimestamp(for_time.timestamp() + offset * self.interval,
                    tz=for_time.tzinfo))) for offset in range(-valid_window, valid_window+1))
