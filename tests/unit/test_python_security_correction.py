"""Bounded offline controls for the reference dependency correction."""

import pytest


def test_joserfc_rejects_oversized_compact_input_before_splitting():
    from joserfc import jws
    from joserfc.errors import BadSignatureError, ExceededSizeError
    from joserfc.jwk import OctKey

    class SplitForbidden(bytes):
        def split(self, *args, **kwargs):
            raise AssertionError("oversized compact input was split before rejection")

    registry = jws.JWSRegistry(algorithms=["HS256"])
    registry.max_header_length = 8
    registry.max_payload_length = 8
    registry.max_signature_length = 8
    # Tiny configured limits distinguish the early guard without a memory benchmark.
    oversized = SplitForbidden(b"e30." + b"x" * 32 + b".x")
    with pytest.raises(ExceededSizeError):
        jws.deserialize_compact(oversized, None, registry=registry)

    key = OctKey.import_key(b"synthetic-joserfc-regression-key-32")
    signed = jws.serialize_compact({"alg": "HS256"}, b"bounded control", key)
    assert jws.deserialize_compact(signed, key).payload == b"bounded control"
    with pytest.raises(BadSignatureError):
        jws.deserialize_compact(signed, OctKey.import_key(b"different-synthetic-control-key-32"))


@pytest.mark.parametrize("algorithm", ["HS256", "HS384", "HS512"])
def test_authlib_rejects_empty_hmac_material_and_preserves_valid_signatures(algorithm):
    from authlib.jose import JsonWebSignature
    from authlib.jose.errors import BadSignatureError

    jws = JsonWebSignature(algorithms=[algorithm])
    header = {"alg": algorithm}
    payload = b"synthetic dependency regression"
    for empty in (b"", {"kty": "oct", "k": ""}):
        with pytest.raises(ValueError, match="must not be empty"):
            jws.serialize_compact(header, payload, empty)
    key = b"synthetic-regression-material-" * 3
    signed = jws.serialize_compact(header, payload, key)
    assert jws.deserialize_compact(signed, key)["payload"] == payload
    with pytest.raises(BadSignatureError):
        jws.deserialize_compact(signed, b"different-synthetic-material-" * 3)


def test_dnspython_bounds_compression_indirection_and_preserves_valid_names():
    import dns.exception
    import dns.name

    wire = bytearray(b"\x00")
    offsets = [0]
    for _ in range(32):
        offsets.append(len(wire))
        wire.extend((0xC000 | offsets[-2]).to_bytes(2, "big"))
    assert dns.name.from_wire(bytes(wire), offsets[1])[0] == dns.name.root
    with pytest.raises(dns.exception.FormError, match="compression pointer chain was too long"):
        dns.name.from_wire(bytes(wire), offsets[-1])
    assert dns.name.from_wire(b"\x07example\x03com\x00", 0)[0].to_text() == "example.com."
