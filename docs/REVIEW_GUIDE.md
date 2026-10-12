# TaskFlow API: independent human review guide

Use this guide in a new review conversation with the repository available. Ask the reviewer to inspect actual code and run tests rather than assume these descriptions prove correctness. Read in the order below, then reproduce the two-user security scenarios locally. The implementation is AI-assisted; the learning goal is to understand and defend the design yourself.

## 1. Structure and request lifecycle

**What and why:** `config/` configures Django, `accounts/` handles identity, and `tasks/` holds the project/task domain. This separates responsibilities without adding service layers or a custom user model.

**Where:** `manage.py`, `config/urls.py`, `accounts/urls.py`, `tasks/urls.py`, each app's serializers/views/tests.

**Flow:** HTTP request → root URL include → app URL → DRF generic view → authentication/permissions → serializer or queryset → ORM/database → serialized response. Django middleware wraps this process. Writes validate before saving.

**Security:** A URL being reachable does not grant access. Authentication, permissions, scoped lookups, and write validation each play a different role.

**Interview questions:** Why split this into two apps? What does `include()` do? Walk through a task POST from URL to database and response. Why use generic views here?

## 2. Configuration and local environment

**What and why:** Settings configure installed apps, middleware, SQLite, password validators, JWT authentication, and an authenticated default permission policy. Environment variables keep the signing key outside current source files and default debug off.

**Where:** `config/settings.py`, `.env.example`, `.gitignore`, `requirements.txt`, `config/tests.py`, README setup.

**Flow:** The shell exports variables → Django imports settings → invalid/missing key or invalid debug flag raises `ImproperlyConfigured` → valid settings initialize the app. `TASKFLOW_DB_PATH` optionally selects a separate database. `.env.example` is not loaded by code.

**Security:** `DJANGO_SECRET_KEY` signs Django values and JWTs; changing it invalidates old JWTs. Never reuse the retired development key from the separately retained original repository. DEBUG can reveal internals. ALLOWED_HOSTS validates hosts, not user permissions or CORS. The repository does not configure production deployment security.

**Interview questions:** Why must the key stay private? Why can a new shell fail to start? What does DEBUG change? What does `.gitignore` fail to remove from history? How can you check a fresh database without touching local data?

## 3. Users and registration

**What and why:** The built-in Django User stores identity and hashed passwords. Registration adds confirmation and duplicate email checks while retaining standard Django password validation.

**Where:** `accounts/serializers.py` (`RegistrationSerializer`), `accounts/views.py` (`RegistrationView`), `accounts/urls.py`, `accounts/tests.py`.

**Flow:** Public POST → serializer checks required fields, username uniqueness, email format and case-insensitive duplicates → `validate()` compares passwords and invokes validators with user attributes → `create()` removes confirmation and calls `create_user` → response contains id/username/email only.

**Security:** Password fields are write-only and preserve whitespace. `create_user` hashes passwords; assigning plaintext to `user.password` would be wrong. Email uniqueness is application-level and can race under concurrent requests; username uniqueness is also protected by the database. API code does not allow registration to set staff/superuser flags.

**Interview questions:** Hashing versus encryption? Why pass a candidate User to password validation? Why is confirmation removed? What is the difference between serializer uniqueness and a database constraint?

## 4. JWT authentication

**What and why:** SimpleJWT provides short-lived access tokens and longer-lived refresh tokens without writing custom token code.

**Where:** `accounts/urls.py`, `SafeTokenRefreshView` in `accounts/views.py`, `SafeTokenRefreshSerializer` in `accounts/serializers.py`, `config/settings.py` (`REST_FRAMEWORK`, `SIMPLE_JWT`), `accounts/tests.py` (`JWTAuthenticationTests`).

**Flow:** Username/password POST → token pair → client sends `Authorization: Bearer ...` → JWTAuthentication validates signature, type, expiry and user → DRF sets `request.user`. Refresh POST validates a refresh token and returns an access token.

**Security:** A JWT payload is signed, not encrypted. Do not store secrets in claims or share tokens. Access lasts five minutes, refresh one day. There is no rotation/blacklist/logout revocation. Inactive users are refused at login, refresh, and protected API access. Tests cover expiry, malformed tokens, wrong token types, and inactive/deleted accounts. The refresh wrapper catches the library's uncaught User.DoesNotExist and converts it to AuthenticationFailed (401); other library validation stays intact.

**Interview questions:** Why two tokens? What does the signature prove? What happens on key rotation or expiry? Does deleting a token from a browser revoke it? How does a JWT become `request.user`?

## 5. Profile endpoint

**What and why:** A single endpoint retrieves or partially edits the authenticated user's safe public profile fields.

**Where:** `ProfileView.get_object()` in `accounts/views.py`, `ProfileSerializer` in `accounts/serializers.py`, root profile route, `ProfileTests`.

**Flow:** Authenticated GET/PATCH → `get_object()` returns `request.user` → serializer returns public fields or validates email/name changes → update that same user. No user ID in the URL or query chooses a different profile.

**Security:** ID and username are read-only. Password and privilege fields are absent and ignored if submitted. Duplicate emails exclude the current user. PUT/POST/DELETE are unsupported.

**Interview questions:** Why override `get_object()`? How does PATCH differ from PUT? Why is a separate password endpoint preferable? Can a submitted ID choose another user?

## 6. Models and relationships

**What and why:** Project belongs to User; Task belongs to Project. This gives one source of ownership and avoids inconsistent task/project owners.

**Where:** `tasks/models.py`; built-in auth User; `tasks/migrations/0001_initial.py` and `0002_task.py`.

**Flow:** Foreign keys store IDs; ORM access traverses `task.project.owner`. `user.projects` and `project.tasks` are reverse relationships. Deleting User cascades to Projects and Tasks; deleting Project cascades to its Tasks.

**Security:** Database relations ensure referenced objects exist, but foreign keys alone do not enforce which user may reference them. API validation supplies that boundary. Choice fields are serializer-validated; model `save()` alone does not run `full_clean()`.

**Interview questions:** Why no Task.owner? What does CASCADE do? What is `related_name`? Does a foreign key enforce ownership? What happens to tasks when a project is deleted?

## 7. Project API

**What and why:** Two generic views implement project list/create and retrieve/partial-update/delete with little custom code.

**Where:** `ProjectSerializer`, `ProjectListCreateView`, `ProjectDetailView`, `tasks/urls.py`, `ProjectTests`.

**Flow:** GET uses `owner=request.user`; POST validates name/description then `perform_create()` supplies current user; detail requests look up the URL primary key inside the owned queryset. Serializer renders ID, name, description, timestamps.

**Security:** Clients cannot set/change ownership because owner is excluded from fields and assigned on the server. Other users' detail objects return 404 on GET/PATCH/DELETE. IDs/timestamps are read-only. Names are required, nonblank, max 200 characters; duplicates are allowed.

**Interview questions:** Why put ownership in `perform_create()`? Why scope the queryset rather than retrieve globally? Why return 404 for another user's project? What fields can PATCH modify?

## 8. Task API and project assignment

**What and why:** Tasks support CRUD with default todo/medium choices and safe project changes between owned projects.

**Where:** `TaskSerializer.__init__()`, `TaskListCreateView`, `TaskDetailView`, `TaskTests`, Task model choices.

**Flow:** Serializer context includes request → project field queryset becomes owned projects → incoming project ID is resolved only there → valid POST/PATCH saves a project instance. Lists/details use `project__owner=request.user` independently of assignment validation.

**Security:** A default `Project.objects.none()` denies assignment without authenticated context. Both create and reassignment use the same field protection. Inaccessible and missing project IDs produce the same error category; denied updates leave the original task intact. Status/priority choices and title validation come from ModelSerializer fields.

**Interview questions:** Why must both read and write paths enforce ownership? What does a PrimaryKeyRelatedField return after validation? Why start its queryset at `.none()`? Can a task move to another user's project?

## 9. Serializers and validation

**What and why:** Serializers define the API contract, convert primitives to validated values, render model instances, and save allowed changes. A small non-model serializer validates query filters.

**Where:** Both `serializers.py` files, including `TaskFilterSerializer`.

**Flow:** Request data → field validation → field-specific validation → object validation → `validated_data` → create/update/save. Response fields are separately controlled by explicit field lists and write-only/read-only settings.

**Security:** Only declared writable fields reach persistence. DRF ignores unknown and read-only inputs; this is intentional and tested. Tests check that ignored passwords/owners never change stored values. Blank descriptions differ from invalid null values. Validation errors produce structured 400 responses.

**Interview questions:** `initial_data` versus `validated_data` versus `.data`? Field versus object validation? Why use a plain Serializer for filters? Are read-only fields rejected or ignored?

## 10. Views, querysets, and ownership

**What and why:** Generic views provide standard lifecycle behavior; querysets constrain available objects per request. Querysets are lazy database queries rather than already-fetched Python lists.

**Where:** `accounts/views.py`, `tasks/views.py`, `tasks/serializers.py` assignment queryset.

**Flow:** `get_queryset()` builds a scoped ORM query → list filters narrow it, or detail lookup adds primary key → database query evaluates → serializer returns data. `project__owner` causes an ORM relationship join. Task responses need project IDs, so accessing full Project objects for each result is unnecessary.

**Security:** Ownership belongs in every applicable queryset. A filtered list alone would not secure detail writes; a scoped detail queryset alone would not prevent foreign project assignment. These boundaries must stay aligned.

**Interview questions:** When is a queryset evaluated? How does `__` traverse a relation? What is an N+1 query? Why is `select_related()` unnecessary for the present ID-only task representation?

## 11. Authentication versus permissions

**What and why:** Authentication identifies a caller, permission checks decide access, and scoped querysets enforce object visibility in this simple ownership model.

**Where:** JWTAuthentication in settings, IsAuthenticated on protected views/default settings, AllowAny on registration, library token views, owned querysets.

**Flow:** DRF authenticates before checking permissions → anonymous/invalid tokens are refused → authenticated request reaches lookup/validation → owned object is returned or 404.

**Security:** IsAuthenticated alone does not enforce ownership. AllowAny does not mean malformed credentials in an Authorization header will always be ignored; authentication may still run. Default permissions reduce accidental exposure in future views but do not replace explicit design review.

**Interview questions:** Can every authenticated user access every object? Why no custom permission class here? What separates 401, 403, and 404? What additional rule would team sharing require?

## 12. Filtering and search

**What and why:** Useful task list filters stay simple: validated project/status/priority plus conventional DRF title search.

**Where:** `TaskFilterSerializer`, `TaskListCreateView.get_queryset()`, SearchFilter/search_fields, `TaskFilterTests`, README examples.

**Flow:** Owned queryset → convert QueryDict to plain dict → validate optional filters → apply exact filters and ID ordering → SearchFilter adds title matches. Multiple search terms are ANDed. Filters combine with AND. Detail endpoints do not use list filters.

**Security:** Every filter narrows an already-owned queryset. Invalid/blank filters return field errors; valid foreign/missing IDs return empty arrays. Project numbers are bounded to SQLite's signed 64-bit range to avoid overflow. Unknown parameters are ignored and repeated parameters use the last value. Converting QueryDict prevents HTML form blank handling from silently omitting an explicitly empty filter.

**Interview questions:** Why validate query parameters? How is an invalid ID different from an inaccessible valid ID? Why use SearchFilter instead of a new dependency? Why must ownership be applied first?

## 13. Migrations and database initialization

**What and why:** Migrations version schema changes so the same database structure can be reproduced on a new machine.

**Where:** `tasks/migrations/`, migration dependencies, README migration commands.

**Flow:** `makemigrations` compares model state to migration state → migration files describe schema operations → `migrate` applies missing operations and records them in `django_migrations`. User dependency uses `swappable_dependency(settings.AUTH_USER_MODEL)`.

**Security:** Do not delete a local database to prove reproducibility. Use an alternate temporary database path. `makemigrations --check --dry-run` detects missing schema changes; it does not prove all database content is correct.

**Interview questions:** What differs between makemigrations and migrate? Why commit migrations? Why can models and migrations drift? Why does Project migration depend on the User model?

## 14. Automated tests and manual review

**What and why:** APITestCase verifies requests against a real test database; SimpleTestCase subprocess tests verify environment behavior before Django startup. Subtests group related cases without duplicating whole methods.

**Where:** `accounts/tests.py`, `tasks/tests.py`, `config/tests.py`, README verification commands, Postman collection.

**Flow:** Django creates a test database → fixtures create synthetic users and objects → APIClient sends requests with real JWT headers → assertions inspect response and persisted state → database is destroyed. Configuration subprocesses import settings with controlled environment variables.

**Security:** Verify failed updates leave data unchanged, not just their status codes. Compare exact returned IDs to prove list isolation. Some tests mint tokens directly to focus on authorization; login tests separately verify password authentication.

**Interview questions:** Why APITestCase? Why check database state after a failed request? Why use two users? What do tests not prove? What is the difference between a test method count and cases within subtests?

Manual review sequence:

1. Set a private environment key; run checks and all tests.
2. Register two synthetic accounts and obtain separate token pairs.
3. Create a project and task as each user; list them with each token.
4. Try GET/PATCH/DELETE of the other user's IDs; expect 404.
5. Try creating/reassigning a task to the other user's project; expect 400 and no mutation.
6. Combine filters/search, including foreign project IDs and invalid values.
7. Submit owner, password, and privilege fields; verify they cannot change protected data.
8. Delete an owned project and confirm its tasks disappear while the other user's tasks remain.

## 15. Git history and repository safety

**What and why:** This public repository begins with one verified portfolio snapshot commit. The original development repository, including its incremental commits, is retained separately; its Git history was not imported. AI-assisted development and validation remain disclosed.

**Where:** `git log --oneline`, `git show <hash>`, `git status`, `git ls-files`, `.gitignore`.

**Flow:** Tracked snapshot export → independent Git initialization on main → audit and verification → stage reviewed files → one initial commit. Later changes can use normal incremental commits. The original repository is never rewritten or pushed as part of this snapshot preparation.

**Security:** Verify tracked files exclude databases, .env, virtual environments, local Postman metadata, and tokens. The retired development signing key is absent from this public history and must never be reused. The original development repository remains separate. Ignoring a file does not remove an already-tracked file or historical content. Test passwords are synthetic fixtures, not personal credentials.

**Interview questions:** Working tree versus index versus commit? Why stage specific files? Does `.gitignore` erase secrets? Why does creating clean public history not make a retired key safe to reuse? What changes between local commit and push?

## 16. README, Postman, and honest scope

**What and why:** README explains reproducible setup and contracts; the curated Postman collection supports manual requests; this guide supports independent learning. Documentation makes the project reviewable without overstating its maturity.

**Where:** `README.md`, `.env.example`, `docs/postman/TaskFlow.postman_collection.json`, this guide.

**Flow:** Follow setup → migrate → run server → register/login → copy or capture tokens → exercise authenticated requests. The Postman collection stores tokens locally after successful token responses; project/task IDs must be set from created objects.

**Security:** Collection credentials/token variables start empty. Clear them before re-exporting. Never present tests as proof of production readiness. Rate limiting, email verification/reset, database-enforced email uniqueness, pagination, refresh revocation, and deployment hardening remain future work.

**Interview questions:** Could a reviewer start from a fresh clone? Which API error contracts are documented? Which features are deliberately absent? What AI assistance was used, and how did you validate and learn from it? Which design would you change first for concurrent production usage?
