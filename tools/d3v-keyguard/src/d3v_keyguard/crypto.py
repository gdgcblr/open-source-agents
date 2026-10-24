"""Cryptographic primitives: peppered Argon2id KEK, X25519 sealed boxes, MACs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

FORMAT = "d3v-keyguard/2"


@dataclass(frozen=True)
class KdfParams:
    iterations: int = 3
    lanes: int = 4
    memory_cost: int = 65536  # KiB

    def as_dict(self) -> dict:
        return {"iterations": self.iterations, "lanes": self.lanes, "memory_cost": self.memory_cost}

    def at_least(self, other: "KdfParams") -> bool:
        return (
            self.iterations >= other.iterations
            and self.lanes >= other.lanes
            and self.memory_cost >= other.memory_cost
        )


DEFAULT_KDF = KdfParams()
_KDF_LIMITS = {"iterations": (1, 64), "lanes": (1, 64), "memory_cost": (8, 4 * 1024 * 1024)}


def parse_kdf(kdf: object) -> tuple[bytes, KdfParams]:
    """Strictly validate a stored KDF block. Raises ValueError on anything unexpected."""
    if not isinstance(kdf, dict) or set(kdf) != {"alg", "salt", "params"} or kdf["alg"] != "argon2id":
        raise ValueError("bad kdf block")
    salt = b64d(kdf["salt"])
    params = kdf["params"]
    if len(salt) != 16 or not isinstance(params, dict) or set(params) != set(_KDF_LIMITS):
        raise ValueError("bad kdf block")
    for key, (lo, hi) in _KDF_LIMITS.items():
        v = params[key]
        if type(v) is not int or not lo <= v <= hi:
            raise ValueError("bad kdf block")
    return salt, KdfParams(**params)


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"), validate=True)


def canonical(*parts: object) -> bytes:
    """Unambiguous encoding of values used as AAD / MAC input."""
    return json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def derive_kek(pin: str, salt: bytes, pepper: bytes, params: KdfParams) -> bytes:
    kdf = Argon2id(
        salt=salt,
        length=32,
        iterations=params.iterations,
        lanes=params.lanes,
        memory_cost=params.memory_cost,
        secret=pepper,
    )
    return kdf.derive(pin.encode("utf-8"))


def hkdf(key: bytes, info: bytes, salt: bytes | None = None) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(key)


def mac(key: bytes, data: bytes) -> str:
    return b64e(hmac.new(key, data, hashlib.sha256).digest())


def mac_ok(key: bytes, data: bytes, tag: object) -> bool:
    return isinstance(tag, str) and tag.isascii() and hmac.compare_digest(mac(key, data), tag)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def aead_encrypt(key: bytes, plaintext: bytes, aad: bytes) -> dict:
    nonce = os.urandom(12)
    return {"nonce": b64e(nonce), "ct": b64e(AESGCM(key).encrypt(nonce, plaintext, aad))}


def aead_decrypt(key: bytes, box: dict, aad: bytes) -> bytes:
    return AESGCM(key).decrypt(b64d(box["nonce"]), b64d(box["ct"]), aad)


def pub_bytes(pub: X25519PublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def priv_bytes(priv: X25519PrivateKey) -> bytes:
    return priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )


def fingerprint(pub_raw: bytes) -> str:
    return hashlib.sha256(b"d3v-keyguard/fp" + pub_raw).hexdigest()[:32]


def seal(recipient_pub_raw: bytes, plaintext: bytes, aad: bytes) -> dict:
    """Encrypt to a public key (ephemeral X25519 + HKDF-SHA256 + AES-256-GCM)."""
    recipient = X25519PublicKey.from_public_bytes(recipient_pub_raw)
    eph = X25519PrivateKey.generate()
    eph_raw = pub_bytes(eph.public_key())
    key = hkdf(eph.exchange(recipient), b"d3v-keyguard/1 seal" + eph_raw + recipient_pub_raw)
    box = aead_encrypt(key, plaintext, aad)
    box["epk"] = b64e(eph_raw)
    return box


def unseal(priv_raw: bytes, box: dict, aad: bytes) -> bytes:
    priv = X25519PrivateKey.from_private_bytes(priv_raw)
    eph_raw = b64d(box["epk"])
    key = hkdf(
        priv.exchange(X25519PublicKey.from_public_bytes(eph_raw)),
        b"d3v-keyguard/1 seal" + eph_raw + pub_bytes(priv.public_key()),
    )
    return aead_decrypt(key, box, aad)


def wipe(buf: bytearray | None) -> None:
    if buf is not None:
        for i in range(len(buf)):
            buf[i] = 0
