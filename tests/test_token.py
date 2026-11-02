import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app.services.token import (
    TokenStatus,
    load_token,
    mask_token,
    save_token,
    validate_token,
)


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status = status
        self._body = io.BytesIO(json.dumps(data or {}).encode("utf-8"))

    def getcode(self):
        return self.status

    def read(self, *args):
        return self._body.read(*args)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TokenFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temporary_directory.name) / ".env"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_load_token_reads_env_file(self):
        self.env_path.write_text("OTHER=value\nPYANNOTE_KEY=file-token\n", encoding="utf-8")

        self.assertEqual(load_token(self.env_path, environ={}), "file-token")

    def test_environment_override_and_empty_override(self):
        self.env_path.write_text("PYANNOTE_KEY=file-token\n", encoding="utf-8")

        self.assertEqual(
            load_token(self.env_path, environ={"PYANNOTE_KEY": "override-token"}),
            "override-token",
        )
        self.assertEqual(
            load_token(self.env_path, environ={"PYANNOTE_KEY": ""}), "file-token"
        )

    def test_save_preserves_other_content_replaces_token_and_sets_permissions(self):
        self.env_path.write_text(
            "# comentario\nOTHER=value\nPYANNOTE_KEY=old-token\nEMPTY=\n",
            encoding="utf-8",
        )

        save_token(self.env_path, "new-token")

        self.assertEqual(
            self.env_path.read_text(encoding="utf-8"),
            "# comentario\nOTHER=value\nPYANNOTE_KEY=new-token\nEMPTY=\n",
        )
        self.assertEqual(stat.S_IMODE(self.env_path.stat().st_mode), 0o600)

    def test_save_adds_missing_token(self):
        self.env_path.write_text("# comentario\nOTHER=value", encoding="utf-8")

        save_token(self.env_path, "new-token")

        self.assertEqual(
            self.env_path.read_text(encoding="utf-8"),
            "# comentario\nOTHER=value\nPYANNOTE_KEY=new-token\n",
        )
        self.assertEqual(load_token(self.env_path, environ={}), "new-token")


class TokenValidationTests(unittest.TestCase):
    @patch("app.services.token.urlopen")
    def test_valid_token_checks_identity_and_model_access(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            FakeResponse(data={"name": "test-user"}),
            FakeResponse(),
        ]

        result = validate_token("test-token")

        self.assertEqual(result.status, TokenStatus.VALID)
        self.assertEqual(result.user, "test-user")
        self.assertEqual(mocked_urlopen.call_count, 2)
        first_request = mocked_urlopen.call_args_list[0].args[0]
        self.assertEqual(first_request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(mocked_urlopen.call_args_list[0].kwargs["timeout"], 15)

    @patch("app.services.token.urlopen")
    def test_invalid_token(self, mocked_urlopen):
        mocked_urlopen.side_effect = HTTPError(
            "https://huggingface.co/api/whoami-v2", 401, "Unauthorized", {}, None
        )

        result = validate_token("test-token")

        self.assertEqual(result.status, TokenStatus.INVALID)
        self.assertNotIn("test-token", result.message)

    @patch("app.services.token.urlopen")
    def test_model_without_access(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            FakeResponse(data={"name": "test-user"}),
            HTTPError(
                "https://huggingface.co/api/models/pyannote/speaker-diarization-community-1",
                403,
                "Forbidden",
                {},
                None,
            ),
        ]

        result = validate_token("test-token")

        self.assertEqual(result.status, TokenStatus.NO_ACCESS)
        self.assertEqual(result.user, "test-user")

    @patch("app.services.token.urlopen")
    def test_network_error_does_not_raise_or_expose_token(self, mocked_urlopen):
        mocked_urlopen.side_effect = URLError("network unavailable")

        result = validate_token("test-token")

        self.assertEqual(result.status, TokenStatus.ERROR)
        self.assertNotIn("test-token", result.message)

    def test_mask_never_returns_complete_token(self):
        for token in ("", "short", "a-longer-test-token"):
            self.assertNotEqual(mask_token(token), token)


if __name__ == "__main__":
    unittest.main()
