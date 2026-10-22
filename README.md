# Private ID Verification

cloud-based digital identity verification system using deep learning and computer vision.  The system should allow users to upload identity documents (e.g., passport, driver’s license, ) and perform real-time verification through OCR  The backend must be deployed on a cloud platform with REST API endpoints  for identity verification requests.

A modular starter for preliminary identity-document checks: HTML/CSS/JavaScript frontend, FastAPI REST API, Tesseract OCR, DeepFace face comparison, and a SQLAlchemy verification-log database.

> This is a prototype, not a proof of identity or document authenticity. OCR, face similarity, and image metadata are fallible. The API reports `checks_passed` only for its limited automated checks; it always includes `document_authenticity_not_confirmed`. Use independent trusted-source validation and human review before any consequential decision. Do not use this prototype as the only fraud control.

## Project layout

- `frontend/` — upload form and result display
- `backend/app/main.py` — REST endpoints and upload limits
- `backend/app/services/verification.py` — OCR, face matching, and review signals
- `backend/app/models.py` and `database.py` — minimal verification log storage
- `Dockerfile` — container image for local use or AWS App Runner

## Run locally

Requirements: Python 3.11, Tesseract OCR installed and available on `PATH`, and a supported CPU environment for DeepFace/TensorFlow.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn backend.app.main:app --reload
```

Open `http://127.0.0.1:8000`. The first face-comparison request may download DeepFace's model weights. Set `API_KEY` in `.env` to require the `X-API-Key` header; the local UI has an optional API-key field. The interactive API schema is at `/docs`.

Run the focused unit tests with `python -m unittest discover -s backend/tests`.

If Tesseract is installed outside `PATH`, set `pytesseract.pytesseract.tesseract_cmd` to its executable in your local environment or add the binary directory to `PATH`.

## REST API

### `POST /api/verify`

Multipart form fields:

- `document_type`: `passport`, `drivers_license`, `aadhaar`, or `other`
- `document_image`: document photo
- `selfie_image`: selfie
- `X-API-Key`: required when `API_KEY` is configured

Returns a verification reference, OCR readability, face-match result, preliminary review flags, and outcome (`checks_passed` or `manual_review_required`). OCR text and images are never returned or stored.

### `GET /api/verifications/{verification_id}`

Returns the minimal log for one request. Protected by the same optional API key.

### `GET /api/health`

Returns a liveness response.

## Data protection

- Images are size-limited, decoded in memory, and are not written to disk or the database.
- OCR text is discarded immediately after calculating a readability signal.
- Database logs contain only a random request ID, document category, outcome, face-match boolean, non-PII review flags, and timestamp.
- Local development uses SQLite. For cloud use set `DATABASE_URL` to a managed PostgreSQL instance with storage encryption enabled (for example, AWS RDS encryption at rest).
- Put the API behind HTTPS. Configure `API_KEY` through the cloud secret manager; do not commit secrets or put production credentials in browser code. For a real public-facing system, replace the shared API key with user authentication and authorization.
- Limit access, set an explicit log-retention policy, and verify local privacy, biometric, and identity-document laws before accepting real user documents.

The face comparison is a one-to-one DeepFace/Facenet512 similarity check. Haar-based face detection is only a precheck. The "possible editor metadata" flag and low-resolution/OCR flags are heuristic signals that can be absent or produce false alarms; they are not forensic tamper detection.

## AWS App Runner deployment

1. Create an encrypted PostgreSQL database in Amazon RDS. Restrict its network access to the App Runner VPC connector and create a least-privilege application database user.
2. Build the repository's Docker image and push it to Amazon ECR, or connect the repository to App Runner for a source-based Docker deployment.
3. Configure the App Runner service to listen on port `8080`. Set `ENVIRONMENT=production`, and add `DATABASE_URL` and `API_KEY` as secrets/environment variables in App Runner. Startup fails if production mode lacks an API key or a managed PostgreSQL URL. Use a URL such as `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME`; URL-encode reserved characters in credentials.
4. Configure App Runner's VPC connector and outbound security group to reach RDS. Keep the database private and enable its encryption-at-rest option.
5. App Runner provides HTTPS ingress. Set upload/body limits at the service or gateway as well as in the application, and restrict access with an authentication layer before accepting real identity documents.

Deployment requires an AWS account, an image repository or connected source repository, and cloud configuration/credentials; this repository does not contain credentials or provision paid services automatically.
