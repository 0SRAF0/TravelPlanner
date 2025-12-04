### Travel Planner UI

React + Vite frontend for the Travel Planner project.

### Prerequisites
- Node.js 23+ (20 LTS recommended)
- pnpm 9+

### Setup
```bash
cd frontend
npm ci  # or: npm install
```
 

### Run
#### Development
```bash
pnpm run dev
# default: http://localhost:3060
# optional: export VITE_APP_API_BASE_URL=http://localhost:8060
```
- Overrides: pass `--port` (e.g., `pnpm run dev -- --port 3060`).
- The app reads `import.meta.env.VITE_APP_API_BASE_URL` (default `http://localhost:8060`).

### Docker
#### Using Docker Compose
From the frontend directory:
```bash
cd frontend
docker compose -f docker-compose-dev.yml up -d --build
```
- App will be at `http://localhost:3060`
- Provide `VITE_APP_API_BASE_URL` via shell env or an `.env.dev` file in `frontend/`

Stop and remove containers:
```bash
cd frontend
docker compose -f docker-compose-dev.yml down
```

Production:
```bash
cd frontend
docker compose -f docker-compose-prod.yml up -d --build
```
- App will be at `http://localhost:3060`
- Provide `VITE_APP_API_BASE_URL` via an `.env.prod` file in `frontend/`

Stop and remove containers:
```bash
cd frontend
docker compose -f docker-compose-prod.yml down
```

#### Build and run the UI container only
From the frontend directory:
```bash
cd frontend
docker build \
  --build-arg VITE_APP_API_BASE_URL="http://localhost:8060" \
  --build-arg VITE_BUILD_MODE=prod \
  -t travelplanner-frontend .
docker run --rm -p 3060:80 travelplanner-frontend
```

#### Required environment variables
- `VITE_APP_API_BASE_URL` (required): Backend API base URL (e.g., `http://localhost:8060`)
- `VITE_BUILD_MODE` (optional, default `prod`)

### App URL
Once the server is running, open:
- `http://localhost:3060/`


### Notes
- Working directory should be `frontend/` when running commands so env files are discovered.
- For container builds, `VITE_APP_API_BASE_URL` is provided at build time and baked into the bundle.
- In local dev, set `VITE_APP_API_BASE_URL` via shell or `.env` files as needed.


