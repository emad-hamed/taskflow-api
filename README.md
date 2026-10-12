# TaskFlow API

A Django REST API for managing personal projects and their tasks. This portfolio project demonstrates registration, JWT authentication, relational data modeling, validation, and user isolation with a small, conventional backend.

## Features and stack

- Register with validated passwords and case-insensitive duplicate email checks.
- Obtain and refresh JWTs; retrieve and edit your own profile.
- Create, list, retrieve, partially update, and delete projects and tasks.
- Filter tasks by project, status, and priority; search their titles.
- Enforce ownership for both object access and project assignment.
- Automated API and configuration tests, plus a Postman collection.

Uses Python (3.12+; verified locally on 3.14.0), Django 6.1.2, Django REST Framework 3.18.3, SimpleJWT 5.5.1, SQLite, and Django ORM. Direct dependency versions are pinned in `requirements.txt`. No filtering or environment-loader dependency is required.

## Architecture

```text
config/                 Settings, root URLs, WSGI/ASGI, configuration tests
accounts/               Registration, JWT routes, profile serializers/views/tests
tasks/                  Project and Task models, serializers, views, URLs, tests
tasks/migrations/       Committed database schema changes
docs/REVIEW_GUIDE.md     Learning and independent review guide
docs/postman/           Intentional collection export, without credentials
manage.py               Django command entry point
requirements.txt        Direct dependencies
.env.example            Environment variable reference (not automatically loaded)
```

```text
User (Django built-in)
  └── Project (owner → User)
        └── Task (project → Project)
```

Both relationships use cascading deletion. Deleting a project deletes its tasks. A task has no separate owner: ownership is `task.project.owner`. Project fields are owner, name, description, created_at, and updated_at; task fields are project, title, description, status, priority, created_at, and updated_at. Django adds a primary key to each model.

## Local setup

Run these commands from the repository root in PowerShell. Install Python 3.12 or newer first.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Generate a private signing key for this shell session; do not commit it.
$env:DJANGO_SECRET_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
$env:DJANGO_DEBUG = 'true'
$env:DJANGO_ALLOWED_HOSTS = 'localhost,127.0.0.1'

.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000/api/`. This is a route prefix, not a homepage; use an endpoint below. Virtual environment activation is optional because commands use its interpreter directly. On macOS/Linux, use `python3 -m venv .venv`, `.venv/bin/python`, and `export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))')"` with the equivalent exported debug/host variables.

Environment variables must be set in every new shell, including the shell running tests. `.env.example` is a reference; neither Django nor this project automatically loads `.env`. To keep tokens valid across server restarts, reuse a privately stored key through your shell or environment manager. Generating a new key invalidates previously issued tokens. Never reuse the retired development signing key.

| Variable | Default / requirement |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required, random, at least 50 characters; also signs JWTs |
| `DJANGO_DEBUG` | `false`; only `true` or `false` (case-insensitive) |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1`; comma-separated hostnames without schemes/ports |
| `TASKFLOW_DB_PATH` | Optional alternate SQLite path; defaults to local `db.sqlite3` |

The database, environment files, virtual environments, caches, and local Postman metadata are ignored by Git. The example environment file and curated collection are intentional tracked artifacts. This repository is a portfolio snapshot with independently initialized public Git history. The original development repository and its history are retained separately and were not imported. A development signing key from that private history has been retired and must never be reused.

## Verification

After setting `DJANGO_SECRET_KEY`:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

The test runner builds and destroys a separate test database. Tests cover registration, hashing, JWT obtain/refresh and failures, profile editing, CRUD, cross-user ownership, task assignment and choices, filtering/search, unsupported methods, cascading deletion, and environment defaults. Tests use synthetic credentials, never personal accounts.

To verify migrations separately without touching your database, use a new temporary path:

```powershell
$env:TASKFLOW_DB_PATH = Join-Path ([System.IO.Path]::GetTempPath()) ('taskflow-' + [guid]::NewGuid().ToString() + '.sqlite3')
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py showmigrations
Remove-Item Env:TASKFLOW_DB_PATH
```

The temporary database can be deleted after inspection. Removing the environment variable restores the normal database path.

## Authentication and endpoints

Registration and token endpoints are public. All profile, project, and task endpoints require:

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

| Method | Endpoint | Behavior |
| --- | --- | --- |
| POST | `/api/auth/register/` | Create account, return public account fields (201) |
| POST | `/api/auth/token/` | Username/password → access and refresh (200) |
| POST | `/api/auth/token/refresh/` | Refresh token → new access (200) |
| GET, PATCH | `/api/profile/` | Retrieve/edit current user (200) |
| GET, POST | `/api/projects/` | List own projects (200), create (201) |
| GET, PATCH, DELETE | `/api/projects/<id>/` | Retrieve/update (200), delete (204) |
| GET, POST | `/api/tasks/` | List own tasks (200), create (201) |
| GET, PATCH, DELETE | `/api/tasks/<id>/` | Retrieve/update (200), delete (204) |

`PUT` is unsupported; use `PATCH` for partial updates. Generic views also support HEAD/OPTIONS where appropriate. `/admin/` is Django's staff-only administration site; an optional local admin can be created with `manage.py createsuperuser`. Project/task admin screens are not registered.

Access tokens expire after five minutes; refresh tokens after one day. Send the refresh token only to the refresh endpoint. Refresh does not rotate or revoke tokens, and there is no logout/blacklist endpoint. Removing a token from a client does not invalidate it. Inactive users cannot log in, refresh, or use an access token. Tokens for deleted accounts return 401; a small refresh serializer wrapper handles the library's deleted-user lookup failure.

## Request and response examples

These examples use placeholders. Supply your own username, email, and strong password locally. The email below is synthetic; no real credentials or tokens are supplied.

Register with `POST /api/auth/register/`:

```json
{
  "username": "demo_member",
  "email": "demo@example.com",
  "password": "<your-strong-password>",
  "password_confirm": "<your-strong-password>"
}
```

```json
{"id": 1, "username": "demo_member", "email": "demo@example.com"}
```

Obtain tokens with `POST /api/auth/token/`:

```json
{"username": "demo_member", "password": "<your-strong-password>"}
```

```json
{"access": "<access-token>", "refresh": "<refresh-token>"}
```

Refresh with `POST /api/auth/token/refresh/`, body `{"refresh": "<refresh-token>"}`. The response is `{"access": "<new-access-token>"}`.

`GET /api/profile/` returns `id`, `username`, `email`, `first_name`, and `last_name`. `PATCH /api/profile/` accepts email, first_name, and last_name, for example `{"first_name": "Demo"}`. Username/id are read-only; password is not a profile field.

Create with `POST /api/projects/`, body `{"name": "Portfolio", "description": "Backend practice"}`:

```json
{
  "id": 1,
  "name": "Portfolio",
  "description": "Backend practice",
  "created_at": "2026-10-12T12:00:00Z",
  "updated_at": "2026-10-12T12:00:00Z"
}
```

Create with `POST /api/tasks/`:

```json
{"project": 1, "title": "Write API tests", "description": "Cover isolation", "priority": "high"}
```

```json
{
  "id": 1,
  "project": 1,
  "title": "Write API tests",
  "description": "Cover isolation",
  "status": "todo",
  "priority": "high",
  "created_at": "2026-10-12T12:00:00Z",
  "updated_at": "2026-10-12T12:00:00Z"
}
```

IDs and timestamps above are illustrative. Lists return plain JSON arrays of these objects. `PATCH /api/tasks/1/` with `{"status": "done"}` returns the updated object. You may change `project` to another project you own. `DELETE /api/tasks/1/` returns 204 with no response body. Project PATCH/DELETE follow the same pattern.

Names/titles are required, nonblank, and at most 200 characters. Descriptions are optional and may be blank. Task statuses are `todo` (default), `in_progress`, `done`; priorities are `low`, `medium` (default), `high`. Invalid request fields return 400 with field errors. Example: `{"status": ["\"invalid\" is not a valid choice."]}`. Missing/invalid/expired authentication returns 401, inaccessible or missing detail objects return 404, and unsupported methods return 405.

## Task filtering and search

```text
GET /api/tasks/?project=1
GET /api/tasks/?status=done
GET /api/tasks/?priority=high
GET /api/tasks/?search=backend
GET /api/tasks/?status=todo&priority=high
GET /api/tasks/?project=1&status=todo&search=backend
```

Filters combine with AND and operate on owned tasks only. Project must be a positive integer within SQLite's signed 64-bit range. Status/priority must exactly match the lowercase choices. Invalid or blank filter values return 400 with an error keyed by the filter name. A valid inaccessible or nonexistent project ID returns an empty array, as does any valid filter with no matches. Task lists are ordered by ID.

DRF `SearchFilter` provides case-insensitive title matching. Multiple space/comma-separated search terms must all match; quoted phrases are supported. Empty search and unknown query parameters are ignored. Repeated parameters use the last value. Filters apply to the list endpoint; detail lookup uses the URL ID and does not accept filter-based object selection.

## Ownership and security

JWT authentication identifies the user; `IsAuthenticated` requires a valid authenticated user. Querysets implement object isolation: projects use `owner=request.user`, tasks use `project__owner=request.user`. DRF's detail lookup uses those querysets, so another user's object looks missing for GET, PATCH, and DELETE.

Project creation assigns ownership on the server. Ownership is omitted from serializers, and IDs/timestamps are read-only. Task project assignment uses a `PrimaryKeyRelatedField` whose queryset contains only owned projects, protecting both POST and PATCH. Missing and inaccessible project assignments receive the same validation error category. Profile lookup returns `request.user` directly, and the serializer excludes passwords and privilege fields. Unknown/read-only payload fields are ignored by DRF rather than persisted.

Registration uses Django password validators and `create_user` hashing; passwords and confirmation are write-only. Django's built-in username uniqueness and serializer email checks catch duplicate accounts. API responses expose only explicitly listed fields. A default authenticated permission policy protects future DRF views unless explicitly overridden for public routes.

## Postman

Import `docs/postman/TaskFlow.postman_collection.json` (Collection v2.1). Set `base_url` (default `http://127.0.0.1:8000`), `access_token`, and `refresh_token` locally. Set the empty username, email, and password variables before registration/login. Token response scripts populate token variables in your local collection. Set project/task IDs from created responses before using detail requests. Clear credentials and tokens before exporting or sharing a collection. Never commit Postman workspace metadata.

## Limitations and future improvements

This is a local portfolio backend, not a production deployment. SQLite, unpaginated lists, no rate limiting, no email verification/reset, no refresh revocation, and no team sharing are intentional scope limits. Email uniqueness is checked in application code on Django's built-in User model, not protected by a database uniqueness constraint; concurrent requests can race. Direct dependencies are pinned, but transitive dependencies are not locked. The tests verify behavior on the installed stack; passing them does not replace dependency/security maintenance.

Possible future work includes pagination, throttling, email verification, password reset, refresh-token revocation, database-enforced normalized email uniqueness, and generated API documentation. A deployment would need a separate review of HTTPS, proxy/host settings, secure cookies, secret management, backups, dependency advisories, and operational requirements. No deployment infrastructure is included.

## Development transparency

This project was developed with AI-assisted coding tools under human direction. The code, tests, and documentation require human review and understanding. See [the review guide](docs/REVIEW_GUIDE.md) for a structured walkthrough and interview questions.
