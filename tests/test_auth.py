"""Unit tests for the HTTP Digest helpers (DeviceAuthHeaderInterceptor parity)."""

from __future__ import annotations

import hashlib
import unittest

from _load import load_module

auth = load_module("proto.auth")


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


class ParseChallengeTests(unittest.TestCase):
    def test_parses_digest_challenge(self) -> None:
        challenge = auth.parse_www_authenticate(
            'Digest realm="tdkcgi", nonce="abc123", qop="auth", opaque="op"'
        )
        assert challenge is not None
        self.assertEqual(challenge["realm"], "tdkcgi")
        self.assertEqual(challenge["nonce"], "abc123")
        self.assertEqual(challenge["qop"], "auth")
        self.assertEqual(challenge["opaque"], "op")

    def test_qop_list_with_comma_survives_splitting(self) -> None:
        challenge = auth.parse_www_authenticate(
            'Digest realm="r", nonce="n", qop="auth,auth-int"'
        )
        assert challenge is not None
        self.assertEqual(challenge["qop"], "auth,auth-int")

    def test_rejects_basic_and_empty(self) -> None:
        self.assertIsNone(auth.parse_www_authenticate('Basic realm="x"'))
        self.assertIsNone(auth.parse_www_authenticate(""))

    def test_header_without_digest_prefix(self) -> None:
        self.assertIsNone(auth.parse_www_authenticate("Bearer abc"))


class BuildAuthorizationTests(unittest.TestCase):
    def test_known_vector_qop_auth(self) -> None:
        challenge = {"realm": "tdkcgi", "nonce": "deadbeef", "qop": "auth"}
        value = auth.build_digest_authorization(
            challenge,
            password="s3cret",
            uri="/tdkcgi",
            method="POST",
            username="adminapp",
            nc="00000001",
            cnonce="cafe01",
        )
        ha1 = md5("adminapp:tdkcgi:s3cret")
        ha2 = md5("POST:/tdkcgi")
        expected = md5(f"{ha1}:deadbeef:00000001:cafe01:auth:{ha2}")
        self.assertEqual(
            value,
            "Digest username=\"adminapp\",realm=\"tdkcgi\",nonce=\"deadbeef\","
            f'uri="/tdkcgi",algorithm=MD5,response="{expected}",qop=auth,'
            "nc=00000001,cnonce=cafe01",
        )

    def test_known_vector_without_qop(self) -> None:
        challenge = {"realm": "r", "nonce": "n"}
        value = auth.build_digest_authorization(
            challenge, password="p", username="adminapp", cnonce="ignored"
        )
        expected = md5(f"{md5('adminapp:r:p')}:n:{md5('POST:/tdkcgi')}")
        self.assertIn(f'response="{expected}"', value)
        self.assertNotIn("qop=", value)

    def test_opaque_passthrough(self) -> None:
        challenge = {"realm": "r", "nonce": "n", "opaque": "op1", "qop": "auth"}
        value = auth.build_digest_authorization(
            challenge, password="p", cnonce="c"
        )
        self.assertIn("opaque=op1", value)

    def test_auth_preferred_whatever_the_order(self) -> None:
        # app parity: DeviceAuthHeaderInterceptor computes qop=auth
        challenge = {"realm": "r", "nonce": "n", "qop": "auth-int,auth"}
        value = auth.build_digest_authorization(
            challenge, password="p", cnonce="c"
        )
        self.assertIn("qop=auth", value)
        self.assertNotIn("qop=auth-int", value)


class DigestStateTests(unittest.TestCase):
    def test_nc_increments(self) -> None:
        state = auth.DigestState(
            {"realm": "r", "nonce": "n", "qop": "auth"}, password="p"
        )
        first = state.authorization()
        second = state.authorization()
        self.assertIn("nc=00000001", first)
        self.assertIn("nc=00000002", second)

    def test_from_header_rejects_non_digest(self) -> None:
        with self.assertRaises(ValueError):
            auth.DigestState.from_header("Basic realm=x", password="p")

    def test_requires_nonce(self) -> None:
        with self.assertRaises(ValueError):
            auth.DigestState({"realm": "r"}, password="p")


if __name__ == "__main__":
    unittest.main()
