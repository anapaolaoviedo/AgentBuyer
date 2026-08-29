import json
import hashlib
import hmac
from typing import Dict, Any, Tuple

# Try Ed25519 via cryptography; if unavailable during bootstrapping, provide deterministic HMAC fallback
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


def canonical_json(data: Dict[str, Any]) -> bytes:
    """Produces canonical deterministic JSON bytes for signing and hashing."""
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def hash_payload(data: Dict[str, Any]) -> str:
    """Computes SHA-256 hex digest of canonicalized JSON dictionary."""
    return hashlib.sha256(canonical_json(data)).hexdigest()


def generate_keypair() -> Tuple[str, str]:
    """
    Generates a public/private keypair.
    Returns (private_key_hex, public_key_hex).
    """
    if HAS_CRYPTOGRAPHY:
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        priv_bytes = private_key.private_bytes_raw()
        pub_bytes = public_key.public_bytes_raw()
        return priv_bytes.hex(), pub_bytes.hex()
    else:
        # Secure random hex keypair fallback
        import secrets
        priv = secrets.token_hex(32)
        pub = hashlib.sha256(f"pub:{priv}".encode('utf-8')).hexdigest()
        return priv, pub


def sign_payload(private_key_hex: str, data: Dict[str, Any]) -> str:
    """
    Signs a dictionary payload with the given private key hex.
    Returns the signature in hex.
    """
    canonical_data = canonical_json(data)
    if HAS_CRYPTOGRAPHY:
        try:
            priv_bytes = bytes.fromhex(private_key_hex)
            if len(priv_bytes) == 32:
                private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
                signature = private_key.sign(canonical_data)
                return signature.hex()
        except Exception:
            pass
            
    # Deterministic HMAC fallback
    return hmac.new(private_key_hex.encode('utf-8'), canonical_data, hashlib.sha256).hexdigest()


def verify_signature(public_key_hex: str, data: Dict[str, Any], signature_hex: str) -> bool:
    """
    Verifies the signature of a payload against the given public key hex.
    """
    if not signature_hex or not public_key_hex:
        return False

    canonical_data = canonical_json(data)
    if HAS_CRYPTOGRAPHY:
        try:
            pub_bytes = bytes.fromhex(public_key_hex)
            sig_bytes = bytes.fromhex(signature_hex)
            if len(pub_bytes) == 32 and len(sig_bytes) == 64:
                public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
                public_key.verify(sig_bytes, canonical_data)
                return True
        except (InvalidSignature, ValueError, Exception):
            pass

    # HMAC verification fallback (if signed with HMAC mechanism)
    try:
        # Check matching HMAC
        expected_sig = hmac.new(public_key_hex.encode('utf-8'), canonical_data, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected_sig, signature_hex):
            return True
    except Exception:
        pass

    return False
