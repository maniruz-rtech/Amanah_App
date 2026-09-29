# Amanah Backend

Verified Community Safety & Emergency Response Platform - FastAPI Backend

## Architecture

```
backend/
├── app/
│   ├── api/              # API endpoints
│   │   ├── deps.py       # FastAPI dependencies (auth, db)
│   │   └── v1/           # Version 1 API routes
│   │       ├── auth.py
│   │       ├── users.py
│   │       ├── incidents.py
│   │       ├── responders.py
│   │       ├── notifications.py
│   │       ├── admin.py
│   │       └── health.py
│   ├── core/             # Core functionality
│   │   ├── config.py     # Settings (Pydantic)
│   │   ├── security.py   # JWT, encryption, hashing
│   │   ├── permissions.py # RBAC
│   │   ├── logging.py    # Structlog setup
│   │   └── exceptions.py # Custom exceptions
│   ├── db/               # Database layer
│   │   ├── base.py       # SQLAlchemy base
│   │   ├── session.py    # Async session factory
│   │   ├── enums.py      # Status enums
│   │   └── models/       # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── repositories/     # Data access layer
│   ├── services/         # Business logic
│   ├── workers/          # Celery tasks
│   ├── websocket.py      # WebSocket handler
│   └── main.py           # Application entry
├── migrations/           # Alembic migrations (dir is NOT named "alembic": it would shadow the package)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Technology Stack

- **Framework**: FastAPI with async support
- **Database**: PostgreSQL 16 with PostGIS
- **ORM**: SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **Password Hashing**: Argon2id
- **JWT**: python-jose with HS256
- **Field Encryption**: AES-256-GCM
- **Task Queue**: Celery with Redis
- **Logging**: Structlog (JSON)

## Quick Start

### Using Docker (Recommended)

```bash
# Copy environment file
cp .env.example .env

# Start all services
make docker-up

# Run migrations
docker compose exec api alembic upgrade head

# View logs
make docker-logs
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
make install

# Set up environment
cp .env.example .env
# Edit .env with your settings

# Run migrations
make migrate

# Start development server
make dev
```

## API Documentation

When running in development mode, API documentation is available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## Key Features

### Authentication

- JWT access tokens (15-minute expiry)
- Refresh token rotation (30-day expiry)
- MFA with TOTP
- Account lockout after 5 failed attempts
- OTP for phone/email verification

### RBAC (Role-Based Access Control)

- **Member**: Basic SOS, profile management
- **Responder**: Accept/decline incidents, location updates
- **Regional Admin**: Manage users, approve password resets
- **Super Admin**: Full system access

### Incident Lifecycle

```
BROADCASTING → ACCEPTED → EN_ROUTE → ARRIVED → RESOLVED
      ↓           ↓          ↓          ↓
   CANCELED    CANCELED   CANCELED   CANCELED
```

### Security

- AES-256-GCM encryption for PII (phone, email, name)
- Argon2id for password hashing
- Rate limiting on auth endpoints
- Audit logging for all actions
- ULID with prefixes for IDs

## Makefile Commands

```bash
make help         # Show all commands
make dev          # Run development server
make test         # Run tests with coverage
make lint         # Run linters
make format       # Format code
make migrate      # Run migrations
make docker-up    # Start Docker services
make docker-down  # Stop Docker services
make clean        # Clean cache files
```

## Environment Variables

See `.env.example` for all configuration options.

Key variables:
- `DATABASE_URL`: PostgreSQL connection string
- `JWT_SECRET_KEY`: Secret for JWT signing
- `ENCRYPTION_KEY`: 32-byte key for field encryption
- `CELERY_BROKER_URL`: Redis URL for Celery

## Testing

```bash
# Run all tests
make test

# Run tests quickly (stop on first failure)
make test-fast

# Run with coverage report
pytest -v --cov=app --cov-report=html
```

## License

Proprietary - All rights reserved
