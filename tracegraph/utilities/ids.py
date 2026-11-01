import hashlib

_MASK_63 = (1 << 63) - 1


def stable_id(*parts: object) -> int:
    """
    #Feature: Graph identity
    #Scenario: Deterministic positive 63-bit id from ordered parts, e.g. (repo_id, "node", type, key)
    #Complexity: Time O(n) - linear in total part length

    Args:
        *parts: Values whose str() forms the identity; at least one is required.

    Returns:
        Integer in [0, 2**63) that fits a Postgres bigint.

    Raises:
        ValueError: When no parts are given.
    """
    if not parts:
        raise ValueError("[stable_id] At least one part is required.")
    digest = hashlib.blake2b("\x1f".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") & _MASK_63


def content_hash(text: str) -> str:
    """
    #Feature: Provenance
    #Scenario: Short hash of a source snippet or file for evidence and dirty-set detection
    #Complexity: Time O(n) - linear in text length

    Args:
        text: Content to hash.

    Returns:
        Hex digest (32 chars).

    Raises:
        ValueError: When text is None.
    """
    if text is None:
        raise ValueError("[content_hash] 'text' is required and must not be None.")
    return hashlib.blake2b(text.encode(), digest_size=16).hexdigest()
