"""Print a PBKDF2 hash for a PRODUCTION account passcode (CASHBRIDGE_USERS_JSON / _FILE).

    python scripts/hash_passcode.py
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from security.auth import hash_passcode  # noqa: E402

if __name__ == "__main__":
    first = getpass.getpass("Passcode (12+ characters): ")
    if len(first) < 12 or first != getpass.getpass("Again: "):
        sys.exit("Passcodes must match and be at least 12 characters.")
    print(hash_passcode(first))
