"""Local-only artifact import, hashing, and authorization checks."""

import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LocalArtifactStoreTests(unittest.TestCase):
    def test_imports_authorized_csv_by_hash_and_resolves_it_from_local_storage(self) -> None:
        from app.services.local_artifacts import LocalArtifactStore

        content = b"record_id,group_id,split,label\nr1,g1,train,a\n"
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory), max_artifact_bytes=1024)
            handle = store.import_csv(
                io.BytesIO(content),
                file_name="manifest.csv",
                authorization_confirmed=True,
            )

            resolved = store.resolve(handle.artifact_id)

            self.assertEqual(handle.sha256, hashlib.sha256(content).hexdigest())
            self.assertEqual(resolved.path.read_bytes(), content)
            self.assertTrue(resolved.path.is_relative_to(Path(directory)))
            self.assertEqual(handle.provenance, "user_selected_local_file")

    def test_rejects_missing_authorization_and_does_not_write_file(self) -> None:
        from app.services.local_artifacts import LocalArtifactError, LocalArtifactStore

        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory), max_artifact_bytes=1024)

            with self.assertRaises(LocalArtifactError) as raised:
                store.import_csv(
                    io.BytesIO(b"private"),
                    file_name="manifest.csv",
                    authorization_confirmed=False,
                )

            self.assertEqual(raised.exception.code, "ARTIFACT_AUTHORIZATION_REQUIRED")
            self.assertEqual(list((Path(directory) / "objects").rglob("*")), [])

    def test_rejects_oversized_csv_and_path_like_filename_is_reduced_to_a_name(self) -> None:
        from app.services.local_artifacts import LocalArtifactError, LocalArtifactStore

        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory), max_artifact_bytes=4)

            with self.assertRaises(LocalArtifactError) as raised:
                store.import_csv(
                    io.BytesIO(b"12345"),
                    file_name="..\\outside.csv",
                    authorization_confirmed=True,
                )

            self.assertEqual(raised.exception.code, "ARTIFACT_TOO_LARGE")
            self.assertFalse((Path(directory).parent / "outside.csv").exists())


if __name__ == "__main__":
    unittest.main()
