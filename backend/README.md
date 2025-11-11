### Travel Planer API

FastAPI server for the Travel Planer project.

### Prerequisites
- Python 3.11+ (3.13 recommended)
- pip

### Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
 

### Run
#### Development
```bash
ENVIRONMENT=dev uvicorn app.main:app --reload --port 8060
```
- Overrides: set `SERVER_PORT` or pass `--port`.
- On startup, the app prints loaded environment variables (sensitive values masked).

#### Production
```bash
ENVIRONMENT=prod uvicorn app.main:app --host 0.0.0.0 --port 8060
```
Use a proper process manager or container/orchestrator for real deployments.

### API Documentation (Swagger)
Once the server is running, you can access the interactive API documentation at:
- **Swagger UI**: `http://<your_domain>:8060/`

The Swagger interface provides:
- Complete API endpoint documentation
- Interactive testing of all endpoints
- Request/response schemas
- Authentication testing capabilities

For local development, access it at `http://localhost:8060/`

### Tests
```bash
pytest
```

### Notes
- Working directory should be `backend/` when running commands so env files are discovered.
 - For IDEs (e.g., PyCharm): set Environment variables (e.g., `ENVIRONMENT=dev`) and Working directory to `backend/`.
 

