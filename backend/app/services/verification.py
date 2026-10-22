from dataclasses import dataclass
from io import BytesIO
import os

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError
import pytesseract
from sqlalchemy.orm import Session

from ..models import VerificationLog

ALLOWED_DOCUMENT_TYPES = {"passport", "drivers_license", "aadhaar", "other"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
EDITING_SOFTWARE_MARKERS = ("photoshop", "gimp", "lightroom", "pixlr")


class VerificationInputError(Exception):
    pass


class VerificationUnavailable(Exception):
    pass


@dataclass
class PreparedImage:
    image: Image.Image
    array: np.ndarray
    format: str
    width: int
    height: int
    exif_software: str


def _prepare_image(data: bytes, label: str) -> PreparedImage:
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise VerificationInputError(f"{label} must be a readable image.") from exc

    if image.format not in ALLOWED_IMAGE_FORMATS:
        raise VerificationInputError(f"{label} must be JPEG, PNG, or WEBP.")
    if image.width < 100 or image.height < 100:
        raise VerificationInputError(f"{label} resolution is too small.")
    if image.width * image.height > 25_000_000:
        raise VerificationInputError(f"{label} dimensions exceed the processing limit.")

    exif = image.getexif()
    software = str(exif.get(305, "")).strip().lower()
    rgb_image = image.convert("RGB")
    array = cv2.cvtColor(np.asarray(rgb_image), cv2.COLOR_RGB2BGR)
    return PreparedImage(
        image=rgb_image,
        array=array,
        format=image.format,
        width=image.width,
        height=image.height,
        exif_software=software,
    )


def _face_count(image: PreparedImage) -> int:
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        raise VerificationUnavailable("The face-detection model could not be loaded.")
    gray = cv2.cvtColor(image.array, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    return len(faces)


def _face_match(document: PreparedImage, selfie: PreparedImage) -> bool | None:
    if _face_count(document) != 1 or _face_count(selfie) != 1:
        return None

    try:
        from deepface import DeepFace
    except ImportError as exc:
        raise VerificationUnavailable(
            "Face matching is unavailable. Install the configured DeepFace dependencies."
        ) from exc

    try:
        result = DeepFace.verify(
            img1_path=document.array,
            img2_path=selfie.array,
            model_name="Facenet512",
            detector_backend="opencv",
            enforce_detection=True,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerificationUnavailable(f"Face matching could not complete: {exc}") from exc
    return bool(result["verified"])


def _ocr(document: PreparedImage) -> int:
    try:
        text = pytesseract.image_to_string(document.image)
    except pytesseract.TesseractNotFoundError as exc:
        raise VerificationUnavailable(
            "OCR is unavailable. Install Tesseract OCR and ensure it is on PATH."
        ) from exc
    except pytesseract.TesseractError as exc:
        raise VerificationUnavailable(f"OCR could not complete: {exc}") from exc
    except RuntimeError as exc:
        raise VerificationUnavailable(f"OCR could not complete: {exc}") from exc
    return len("".join(text.split()))


def _tamper_signals(document: PreparedImage) -> list[str]:
    flags = []
    if document.width < 600 or document.height < 350:
        flags.append("low_document_resolution")
    if any(marker in document.exif_software for marker in EDITING_SOFTWARE_MARKERS):
        flags.append("possible_image_editor_metadata")
    return flags


def run_verification(
    document_bytes: bytes,
    selfie_bytes: bytes,
    document_type: str,
    db: Session,
) -> dict:
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise VerificationInputError("Choose a supported document type.")

    document = _prepare_image(document_bytes, "Document")
    selfie = _prepare_image(selfie_bytes, "Selfie")
    flags = _tamper_signals(document)

    ocr_char_count = _ocr(document)
    if ocr_char_count < 12:
        flags.append("low_ocr_text")

    face_match = _face_match(document, selfie)
    if face_match is None:
        flags.append("face_not_detected_or_ambiguous")
    elif not face_match:
        flags.append("face_mismatch")

    flags.append("document_authenticity_not_confirmed")
    outcome = (
        "checks_passed"
        if not any(flag != "document_authenticity_not_confirmed" for flag in flags)
        else "manual_review_required"
    )

    log = VerificationLog(
        document_type=document_type,
        outcome=outcome,
        face_match=face_match,
        flags=flags,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "verification_id": log.id,
        "outcome": log.outcome,
        "document_type": log.document_type,
        "ocr_readable": ocr_char_count >= 12,
        "face_match": log.face_match,
        "flags": log.flags,
        "message": (
            "Automated checks passed. Document authenticity still requires trusted-source "
            "validation or human review."
            if outcome == "checks_passed"
            else "One or more checks need human review; do not treat this result as a final decision."
        ),
    }


def max_upload_bytes() -> int:
    try:
        size_mb = int(os.getenv("MAX_UPLOAD_MB", "10"))
    except ValueError as exc:
        raise RuntimeError("MAX_UPLOAD_MB must be a positive integer.") from exc
    if size_mb < 1:
        raise RuntimeError("MAX_UPLOAD_MB must be a positive integer.")
    return size_mb * 1024 * 1024
