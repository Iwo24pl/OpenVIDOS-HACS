"""Unit tests for the CGI transport client (fake transport, no aiohttp)."""

from __future__ import annotations

import unittest

from _load import load_module

api = load_module("proto.device_api")
env = load_module("proto.envelope")

OK_BODY = (
    "<response><error>0</error><content><status>ok</status></content></response>"
)
CHALLENGE = 'Digest realm="tdkcgi", nonce="abc123", qop="auth"'


class FakeTransportClient(api.VidosCgiClient):
    """Client with ``_async_post`` replaced by a scripted queue."""

    def __init__(self, responses, **kwargs) -> None:
        kwargs.setdefault("session", None)
        super().__init__("192.168.1.10", 443, password="s3cret", **kwargs)
        self.scripted = list(responses)
        self.posts: list[tuple[bytes, dict[str, str]]] = []

    async def _async_post(self, data, headers):
        self.posts.append((data, dict(headers)))
        if not self.scripted:
            raise AssertionError("unexpected POST")
        return self.scripted.pop(0)


class ClientUrlTests(unittest.TestCase):
    def test_base_url(self) -> None:
        client = api.VidosCgiClient(
            "192.168.1.10", 443, username="adminapp2", password="x", session=None
        )
        self.assertEqual(client.base_url, "https://192.168.1.10:443/tdkcgi")
        self.assertEqual(client.configuration_url, "https://192.168.1.10:443/")

    def test_header_password_is_hashed_by_default(self) -> None:
        client = api.VidosCgiClient(
            "192.168.1.10", 443, username="adminapp2", password="s3cret", session=None
        )
        self.assertEqual(client.header_password, env.sha256_hex("s3cret"))

    def test_header_password_raw_when_hashing_disabled(self) -> None:
        client = api.VidosCgiClient(
            "192.168.1.10",
            443,
            username="adminapp2",
            password="s3cret",
            session=None,
            hash_password=False,
        )
        self.assertEqual(client.header_password, "s3cret")


class AsyncCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_success(self) -> None:
        client = FakeTransportClient([(200, {}, OK_BODY)])
        resp = await client.async_command("get.device.status")
        self.assertTrue(resp.ok)
        self.assertEqual(len(client.posts), 1)
        self.assertNotIn("Authorization", client.posts[0][1])
        self.assertIn(b"<command>get.device.status</command>", client.posts[0][0])
        self.assertIn(b"<security>httpauthen</security>", client.posts[0][0])

    async def test_digest_challenge_retries_once(self) -> None:
        client = FakeTransportClient(
            [(401, {"WWW-Authenticate": CHALLENGE}, ""), (200, {}, OK_BODY)]
        )
        resp = await client.async_command("get.device.status")
        self.assertTrue(resp.ok)
        self.assertEqual(len(client.posts), 2)
        self.assertNotIn("Authorization", client.posts[0][1])
        auth_header = client.posts[1][1].get("Authorization", "")
        self.assertTrue(auth_header.startswith("Digest "))
        self.assertIn('nonce="abc123"', auth_header)
        self.assertIn('username="adminapp"', auth_header)
        self.assertTrue(client.digest_ready)

    async def test_digest_state_reused_on_next_command(self) -> None:
        client = FakeTransportClient(
            [
                (401, {"www-authenticate": CHALLENGE.lower()}, ""),
                (200, {}, OK_BODY),
                (200, {}, OK_BODY),
            ]
        )
        await client.async_command("get.device.status")
        await client.async_command("get.lock.status")
        # third post proactively carries Authorization (nc incremented)
        self.assertIn("Authorization", client.posts[2][1])
        self.assertIn("nc=00000002", client.posts[2][1]["Authorization"])

    async def test_non_200_raises(self) -> None:
        client = FakeTransportClient([(500, {}, "boom")])
        with self.assertRaises(env.VidosCgiResponseError):
            await client.async_command("get.device.status")

    async def test_digest_disabled_never_retries(self) -> None:
        client = FakeTransportClient(
            [(401, {"WWW-Authenticate": CHALLENGE}, "")], digest_auth=False
        )
        with self.assertRaises(env.VidosCgiResponseError):
            await client.async_command("get.device.status")
        self.assertEqual(len(client.posts), 1)

    async def test_require_ok_raises_on_device_error(self) -> None:
        client = FakeTransportClient(
            [(200, {}, "<r><body><error>-10028</error></body></r>")]
        )
        with self.assertRaises(env.VidosCgiCommandError) as ctx:
            await client.async_command("set.device.opendoor")
        self.assertEqual(ctx.exception.error, -10028)

    async def test_open_door_content_shape(self) -> None:
        client = FakeTransportClient([(200, {}, OK_BODY)])
        await client.async_open_door(door=1, lock=1)
        data = client.posts[0][0].decode()
        self.assertIn(
            "<content><door>1</door><locknumber>1</locknumber><password>",
            data,
        )
        # password defaults to sha256(device password)
        self.assertIn(env.sha256_hex("s3cret"), data)


if __name__ == "__main__":
    unittest.main()
