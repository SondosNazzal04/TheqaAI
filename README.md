# Theqa AI

Theqa AI is an advanced AI-powered platform.

## Architecture

This repository is set up as a monorepo with the following components:

- `apps/api`: The backend API, built with **FastAPI**, **PostgreSQL** (via asyncpg), **SQLAlchemy**, and **Alembic** for migrations.
- `apps/web`: The frontend web application (Coming soon).

## Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose
- [Python 3.11+](https://www.python.org/)

## Setup Instructions

### 1. Start the Database

The project uses a PostgreSQL database. You can start it using Docker Compose from the root of the project:

```bash
docker-compose up -d
```

This will start a PostgreSQL container named `theqa_db` on port `5432`.

### 2. API Setup

Navigate to the API directory:

```bash
cd apps/api
```

Create and activate a virtual environment:

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 3. Database Migrations

With the database running and the virtual environment activated, apply the database migrations to set up your tables:

```bash
alembic upgrade head
```

### 4. Run the API Server

Start the FastAPI application using Uvicorn:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.
You can access the interactive Swagger API documentation at `http://127.0.0.1:8000/docs`.

## Health Check

To verify the API is running correctly, you can hit the health check endpoint:

```bash
curl http://127.0.0.1:8000/health
```

## Features Implemented So Far

### 1. Authentication & Users (Phase 2)
- Secure user registration and login endpoints utilizing Argon2 password hashing.
- Organization support allowing users to be tied to `personal`, `merchant`, or `platform` organizations with specific roles.
- JWT-based Bearer token authentication to protect endpoints.

### 2. Trust Score Engine (Phase 3)
- **Piecewise Rule Engine**: A fully dynamic mathematical scoring algorithm to evaluate both individuals and merchants on an exact 0-100 scale using metrics like dispute rates, success percent, and account age. Includes rigorous cold-start priors (e.g. baseline 5% refund expectation for new merchants).
- **Asynchronous Execution**: The heavy trust mathematics run safely in the background (using FastAPI `BackgroundTasks`), preventing API blocking.
- **Signal Ingestion API**: An internal `/mock` endpoint to inject raw performance signals into the database, instantly triggering a background score recalculation.
- **Read-Only Score Fetching**: A blazingly fast `GET` endpoint that retrieves the pre-calculated final score and detailed breakdown straight from the database.

## How to Test the Application

The fastest way to test everything together is by using the interactive **FastAPI Swagger UI** provided out of the box.

### Step 1: Access Swagger UI
Make sure your server is running (`uvicorn app.main:app --reload`).
Open your browser and navigate to: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Step 2: Inject a Trust Signal
1. Scroll down to the **Trust** section and find the `POST /v1/trust/internal/trust-signals/mock` endpoint.
2. Click **"Try it out"**.
3. Enter the following JSON payload. This simulates a user getting their Identity Verified:
```json
{
  "entity_type": "individual",
  "entity_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "signal_type": "identity_verification",
  "value": 1.0,
  "metadata_payload": {
    "level": "verified"
  }
}
```
4. Click **Execute**. You should get a `201` response indicating the signal was ingested and recalculation queued.

### Step 3: View the Calculated Trust Score
1. In the Swagger UI, locate the `GET /v1/trust/scores/{type}/{id}` endpoint.
2. Click **"Try it out"**.
3. Set `type` to `individual`.
4. Set `id` to `3fa85f64-5717-4562-b3fc-2c963f66afa6` (the same UUID you used above).
5. Click **Execute**. 

**Expected Result**: You should instantly receive a `200` response containing a computed `score` and a detailed JSON `breakdown`. Because you only verified their identity, the rest of their score components will automatically fall back to the cold-start baseline priors outlined in the Technical Blueprint (e.g., age=20, disputes=100)!
