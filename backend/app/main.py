import asyncio
import hmac
import os
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .database import DATABASE_URL, Base, SessionLocal, engine, get_db
from .models import VerificationLog
from .services.verification import (
    ALLOWED_DOCUMENT_TYPES,
    VerificationInputError,
    VerificationUnavailable,
    max_upload_bytes,
    run_verification,
)

if os.getenv("ENVIRONMENT", "development").lower() == "production":
    if not os.getenv("API_KEY"):
        raise RuntimeError("Set API_KEY through the cloud secret manager before production startup.")
    if not DATABASE_URL.startswith("postgresql+psycopg://"):
        raise RuntimeError("Production requires DATABASE_URL to point to encrypted managed PostgreSQL.")

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Private ID Verification", version="1.0.0")
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("API_KEY")
    if expected and (not x_api_key or not hmac.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="A valid API key is required.")


def verify_and_log(document_bytes: bytes, selfie_bytes: bytes, document_type: str) -> dict:
    with SessionLocal() as db:
        return run_verification(document_bytes, selfie_bytes, document_type, db)


async def read_upload(upload: UploadFile, label: str) -> bytes:
    limit = max_upload_bytes()
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"{label} exceeds the configured upload limit.")
    if not data:
        raise HTTPException(status_code=400, detail=f"{label} is empty.")
    return data


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/verify", dependencies=[Depends(require_api_key)])
async def verify_identity(
    document_type: str = Form(...),
    document_image: UploadFile = File(...),
    selfie_image: UploadFile = File(...),
) -> dict:
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail="Choose a supported document type.")
    document_bytes = await read_upload(document_image, "Document image")
    selfie_bytes = await read_upload(selfie_image, "Selfie image")
    try:
        return await asyncio.to_thread(
            verify_and_log,
            document_bytes,
            selfie_bytes,
            document_type,
        )
    except VerificationInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VerificationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/verifications/{verification_id}", dependencies=[Depends(require_api_key)])
def get_verification(
    verification_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    log = db.get(VerificationLog, str(verification_id))
    if log is None:
        raise HTTPException(status_code=404, detail="Verification log not found.")
    return {
        "verification_id": log.id,
        "outcome": log.outcome,
        "document_type": log.document_type,
        "face_match": log.face_match,
        "flags": log.flags,
        "created_at": log.created_at.isoformat(),
    }
