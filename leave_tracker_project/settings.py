from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent

def _load_env_file_fallback(path: Path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1].strip()
        os.environ.setdefault(key, value)

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", override=False)
except Exception:
    _load_env_file_fallback(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    raw = os.getenv(name, default)
    if raw is None:
        return default
    value = str(raw).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_bool(name: str, default: str = "0") -> bool:
    return _truthy(_env(name, default))


def _env_csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in _env(name, default).split(",") if item.strip()]


def _normalize_host(host: str) -> str:
    host = host.strip().strip("/")
    if "://" in host:
        parsed = urlparse(host)
        host = parsed.netloc or parsed.path
    if host.startswith("*."):
        host = host[1:]
    if host.count(":") == 1 and not host.startswith("["):
        host = host.split(":", 1)[0]
    return host


def _normalize_origin(origin: str) -> str:
    origin = origin.strip().strip("/")
    if not origin:
        return ""
    if not origin.startswith(("http://", "https://")):
        origin = f"https://{origin}"
    parsed = urlparse(origin)
    return f"{parsed.scheme}://{parsed.netloc}"


SECRET_KEY = _env("SECRET_KEY", "dev-insecure-secret-key-change-me")
DEBUG = _env_bool("DEBUG", "1")

ALLOWED_HOSTS = [_normalize_host(h) for h in _env_csv("ALLOWED_HOSTS", "127.0.0.1,localhost")]
ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h]
CSRF_TRUSTED_ORIGINS = [_normalize_origin(o) for o in _env_csv("CSRF_TRUSTED_ORIGINS")]
CSRF_TRUSTED_ORIGINS = [o for o in CSRF_TRUSTED_ORIGINS if o]
FRONTEND_ORIGINS = [
    _normalize_origin(o)
    for o in _env_csv("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
]
FRONTEND_ORIGINS = [o for o in FRONTEND_ORIGINS if o]
for origin in FRONTEND_ORIGINS:
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

REQUIRE_EXPLICIT_ORG_CONTEXT = _env_bool("REQUIRE_EXPLICIT_ORG_CONTEXT", "0" if DEBUG else "1")
ORG_CONTEXT_AUDIT_LOG = _env_bool("ORG_CONTEXT_AUDIT_LOG", "1")
ENABLE_POSTGRES_SCHEMA_TENANCY = _env_bool("ENABLE_POSTGRES_SCHEMA_TENANCY", "0")
TENANCY_AUTO_CREATE_SCHEMA = _env_bool("TENANCY_AUTO_CREATE_SCHEMA", "0")
ORG_CONTEXT_EXEMPT_PATHS = _env_csv(
    "ORG_CONTEXT_EXEMPT_PATHS",
    "/api/org/companies/,/api/org/companies,/api/org/context/,/api/org/context",
)
ORG_CONTEXT_EXEMPT_PATH_PREFIXES = _env_csv(
    "ORG_CONTEXT_EXEMPT_PATH_PREFIXES",
    "/api/auth/",
)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "users.apps.UsersConfig",
    "organization.apps.OrganizationConfig",
    "architecture.apps.ArchitectureConfig",
    "leaves.apps.LeavesConfig",
    "auditlog.apps.AuditlogConfig",
    "portal.apps.PortalConfig",
    "api.apps.ApiConfig",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "organization.middleware.OrganizationContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "leave_tracker_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "portal.context_processors.portal_globals",
            ],
        },
    },
]


WSGI_APPLICATION = "leave_tracker_project.wsgi.application"
ASGI_APPLICATION = "leave_tracker_project.asgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

raw_database_url = _env("DATABASE_URL")
USE_DATABASE_URL = _env_bool("USE_DATABASE_URL", "0") or (not DEBUG and bool(raw_database_url))
if USE_DATABASE_URL and raw_database_url:
    try:
        import dj_database_url  # type: ignore

        DATABASES["default"] = dj_database_url.parse(raw_database_url, conn_max_age=600)
    except Exception:
        pass


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = _env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = _env("MEDIA_URL", "/media/")
if not MEDIA_URL.endswith("/"):
    MEDIA_URL += "/"
MEDIA_ROOT = Path(_env("MEDIA_ROOT", str(BASE_DIR / "media")))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"


EMAIL_BACKEND = _env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = _env("EMAIL_HOST", "")
EMAIL_PORT = int(_env("EMAIL_PORT", "587") or "587")
EMAIL_HOST_USER = _env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", "1")
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL", "0")
EMAIL_TIMEOUT = int(_env("EMAIL_TIMEOUT", "20") or "20")
DEFAULT_FROM_EMAIL = _env("DEFAULT_FROM_EMAIL", "no-reply@leave-tracker.local")
EMAIL_FAIL_SILENTLY = _env_bool("EMAIL_FAIL_SILENTLY", "1")

if not EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


MANAGER_EMAILS = [e.strip().lower() for e in _env("MANAGER_EMAILS", "").split(",") if e.strip()]
LEAVE_EMAIL_NOTIFICATIONS_ENABLED = _env_bool("LEAVE_EMAIL_NOTIFICATIONS_ENABLED", "1")
LEAVE_NOTIFICATION_TARGET = _env("LEAVE_NOTIFICATION_TARGET", "MANAGER").strip().upper()
HR_MAILBOX = _env("HR_MAILBOX", "").strip().lower()
TEAM_DISTRIBUTION_EMAILS = [e.strip().lower() for e in _env("TEAM_DISTRIBUTION_EMAILS", "").split(",") if e.strip()]
LEAVE_RATE_LIMIT_PER_MINUTE = int(_env("LEAVE_RATE_LIMIT_PER_MINUTE", "5") or "5")
LEAVE_TEAM_OFF_THRESHOLD = int(_env("LEAVE_TEAM_OFF_THRESHOLD", "3") or "3")


AWS_STORAGE_BUCKET_NAME = _env("AWS_STORAGE_BUCKET_NAME", "")
AWS_ACCESS_KEY_ID = _env("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = _env("AWS_SECRET_ACCESS_KEY", "")
AWS_S3_REGION_NAME = _env("AWS_S3_REGION_NAME", "")
AWS_S3_CUSTOM_DOMAIN = _env("AWS_S3_CUSTOM_DOMAIN", "")

if AWS_STORAGE_BUCKET_NAME and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    INSTALLED_APPS += ["storages"]
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
    elif AWS_S3_REGION_NAME:
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
    else:
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"


CELERY_BROKER_URL = _env("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = _env("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
USE_CELERY = _env_bool("USE_CELERY", "0")

CORS_ALLOWED_ORIGINS = FRONTEND_ORIGINS
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-company-id",
    "x-dts-schema",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(_env("JWT_ACCESS_MINUTES", "30") or "30")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(_env("JWT_REFRESH_DAYS", "7") or "7")),
    "AUTH_HEADER_TYPES": ("Bearer",),
}
