import hashlib


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_short(text: str, length: int = 12) -> str:
    return sha256_hex(text)[:length]


def body_hash(text: str) -> str:
    return sha256_hex(text)


def subject_hash(subject: str) -> str:
    return sha256_short(subject.strip().lower(), length=12)
