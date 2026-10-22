from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.database import Base
from backend.app.models import VerificationLog
from backend.app.services.verification import (
    VerificationInputError,
    _prepare_image,
    run_verification,
)


def sample_image() -> bytes:
    image = Image.new("RGB", (800, 500), color="white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class VerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_rejects_non_image_upload(self) -> None:
        with self.assertRaises(VerificationInputError):
            _prepare_image(b"not an image", "Document")

    @patch("backend.app.services.verification._face_match", return_value=True)
    @patch("backend.app.services.verification._ocr", return_value=100)
    def test_pass_result_only_persists_minimal_log(self, _ocr: object, _face: object) -> None:
        image = sample_image()
        result = run_verification(image, image, "passport", self.db)
        log = self.db.scalar(select(VerificationLog))

        self.assertEqual(result["outcome"], "checks_passed")
        self.assertTrue(result["face_match"])
        self.assertIn("document_authenticity_not_confirmed", result["flags"])
        self.assertIsNotNone(log)
        self.assertFalse(hasattr(log, "ocr_text"))
        self.assertFalse(hasattr(log, "document_image"))
        self.assertFalse(hasattr(log, "selfie_image"))

    @patch("backend.app.services.verification._face_match", return_value=False)
    @patch("backend.app.services.verification._ocr", return_value=100)
    def test_face_mismatch_requires_manual_review(self, _ocr: object, _face: object) -> None:
        image = sample_image()
        result = run_verification(image, image, "aadhaar", self.db)

        self.assertEqual(result["outcome"], "manual_review_required")
        self.assertIn("face_mismatch", result["flags"])


if __name__ == "__main__":
    unittest.main()
