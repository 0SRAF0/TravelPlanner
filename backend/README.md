### Travel Planner API

FastAPI server for the Travel Planner project.

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

### Docker
#### Using Docker Compose (recommended)
From the project root (where `docker-compose.yml` is):
```bash
docker compose up -d --build
```
- API will be at `http://localhost:8060`
- MongoDB will listen on `localhost:27017` with default user `root`/`example`
- The API container uses `MONGODB_URI=mongodb://root:example@mongo:27017/travel_planer?authSource=admin`

Stop and remove containers:
```bash
docker compose down
```

#### Build and run the API container only
From the project root:
```bash
docker build -t travelplaner-api ./backend
docker run --rm -p 8060:8060 \
  -e ENVIRONMENT=production \
  -e SERVER_PORT=8060 \
  -e CORS_ORIGINS="http://localhost:3060,http://127.0.0.1:3060" \
  -e MONGODB_URI="mongodb://root:example@localhost:27017/travel_planer?authSource=admin" \
  -e JWT_SECRET="dev-secret-change-me" \
  travelplaner-api
```

#### Required environment variables
- `MONGODB_URI` (required): MongoDB connection string
- `SERVER_PORT` (optional, default `8060`)
- `CORS_ORIGINS` (optional)
- `JWT_SECRET` (recommended to set for auth)

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
 

