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
