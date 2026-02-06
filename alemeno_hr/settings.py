from pathlib import Path
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Load local `.env` for developer convenience, but never override real environment vars
# (Railway/Render/etc). This keeps deployments predictable.
load_dotenv(BASE_DIR / ".env", override=False)


def _env(name: str, default: str = "") -> str:
    """Read env var and strip accidental surrounding quotes (common in Railway UI)."""
    val = os.getenv(name, default)
    if val is None:
        return default
    val = str(val).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        val = val[1:-1].strip()
    return val


def _env_csv(name: str, default: str = "") -> list[str]:
    raw = _env(name, default)
    return [p.strip() for p in raw.split(",") if p.strip()]


def _truthy(val: str) -> bool:
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_host(host: str) -> str:
    host = host.strip().strip("/")
    if not host:
        return ""
    # Users sometimes paste full URLs into ALLOWED_HOSTS; keep only host.
    if "://" in host:
        parsed = urlparse(host)
        host = (parsed.netloc or parsed.path).strip().strip("/")
    # Convert "*.example.com" to Django's ".example.com" wildcard format.
    if host.startswith("*."):
        host = host[1:]
    # Strip a single :port (avoid breaking IPv6 literals).
    if host.count(":") == 1 and not host.startswith("["):
        host = host.split(":", 1)[0]
    return host


def _normalize_origin(origin: str) -> str:
    origin = origin.strip().strip("/")
    if not origin:
        return ""
    if not (origin.startswith("http://") or origin.startswith("https://")):
        origin = f"https://{origin}"
    parsed = urlparse(origin)
    # Keep only scheme + host[:port]; Django expects origins, not full URLs with paths.
    return f"{parsed.scheme}://{parsed.netloc}"


SECRET_KEY = _env("SECRET_KEY", "dev-secret-key-change-me")
# Make the project runnable out-of-the-box for local development.
# In production, set DEBUG=0 in your environment.
DEBUG = _truthy(_env("DEBUG", "0"))

ALLOWED_HOSTS = [_normalize_host(h) for h in _env_csv("ALLOWED_HOSTS", "127.0.0.1,localhost")]
ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h]
CSRF_TRUSTED_ORIGINS = [_normalize_origin(o) for o in _env_csv("CSRF_TRUSTED_ORIGINS", "")]
CSRF_TRUSTED_ORIGINS = [o for o in CSRF_TRUSTED_ORIGINS if o]

# If you're on Railway and forget to set ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS (or set them
# with quotes), Django will throw DisallowedHost / CSRF 403. This fallback keeps the app
# usable on Railway's generated domains.
IS_RAILWAY = any(k.startswith("RAILWAY_") for k in os.environ)
if IS_RAILWAY:
    if ".up.railway.app" not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(".up.railway.app")
    if not CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = ["https://*.up.railway.app"]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# We use custom portal auth routes (not Django's default `/accounts/login/`).
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/me/"
LOGOUT_REDIRECT_URL = "/login/"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "employees.apps.EmployeesConfig",
    "leave.apps.LeaveConfig",
    "portal.apps.PortalConfig",
    "audit.apps.AuditConfig",
    # REST framework is optional; enable only if you use the API module.
    # "rest_framework",
    # "django_filters",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "alemeno_hr.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "portal.context_processors.portal_globals",
            ],
        },
    },
]

WSGI_APPLICATION = "alemeno_hr.wsgi.application"

# --- Database ---
# Dev default: SQLite.
# Production/Neon: set DATABASE_URL (e.g. postgresql://user:pass@host/dbname?sslmode=require)
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DATABASE_URL = _env("DATABASE_URL", "")
# `.env`/platform UIs sometimes include an extra "=" by mistake (e.g. DATABASE_URL==...)
DATABASE_URL = DATABASE_URL.lstrip("=")
if DATABASE_URL:
    try:
        import dj_database_url  # type: ignore

        DATABASES["default"] = dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    except Exception as e:  # pragma: no cover
        # If dj-database-url isn't installed, keep SQLite so the app can still run locally.
        print("WARNING: DATABASE_URL is set but dj-database-url is missing or failed to parse:", e)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise: allow Django's static finders in dev (so /static/app.css works without collectstatic).
WHITENOISE_USE_FINDERS = True

MEDIA_URL = _env("MEDIA_URL", "/media/")
if not MEDIA_URL.endswith("/"):
    MEDIA_URL += "/"
MEDIA_ROOT = Path(_env("MEDIA_ROOT", str(BASE_DIR / "media")))

# --- Media storage (recommended for production) ---
# Railway's filesystem is ephemeral unless you attach a Volume. For a company-grade setup,
# point uploads to object storage (S3) by setting AWS_* env vars.
AWS_STORAGE_BUCKET_NAME = _env("AWS_STORAGE_BUCKET_NAME", "")
AWS_ACCESS_KEY_ID = _env("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = _env("AWS_SECRET_ACCESS_KEY", "")
AWS_S3_REGION_NAME = _env("AWS_S3_REGION_NAME", "")
AWS_S3_CUSTOM_DOMAIN = _env("AWS_S3_CUSTOM_DOMAIN", "")
AWS_S3_ENDPOINT_URL = _env("AWS_S3_ENDPOINT_URL", "")
AWS_S3_ADDRESSING_STYLE = _env("AWS_S3_ADDRESSING_STYLE", "path")
AWS_S3_SIGNATURE_VERSION = _env("AWS_S3_SIGNATURE_VERSION", "s3v4")

if AWS_STORAGE_BUCKET_NAME and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    # Only enable S3 storage when all required settings are present.
    try:
        import storages  # type: ignore  # noqa: F401
    except Exception as e:  # pragma: no cover
        print("WARNING: AWS_* vars are set but django-storages is unavailable:", e)
    else:
        INSTALLED_APPS += ["storages"]
        DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
        AWS_QUERYSTRING_AUTH = False
        AWS_DEFAULT_ACL = None
        AWS_S3_FILE_OVERWRITE = False
        AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}

        if AWS_S3_ENDPOINT_URL:
            AWS_S3_ENDPOINT_URL = AWS_S3_ENDPOINT_URL.rstrip("/")
        if AWS_S3_ADDRESSING_STYLE:
            AWS_S3_ADDRESSING_STYLE = AWS_S3_ADDRESSING_STYLE.strip().lower()
        if AWS_S3_SIGNATURE_VERSION:
            AWS_S3_SIGNATURE_VERSION = AWS_S3_SIGNATURE_VERSION.strip()

        if AWS_S3_CUSTOM_DOMAIN:
            MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
        elif AWS_S3_ENDPOINT_URL:
            if AWS_S3_ADDRESSING_STYLE == "virtual":
                host = AWS_S3_ENDPOINT_URL.replace("https://", "").replace("http://", "")
                MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.{host}/"
            else:
                MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/"
        else:
            # Default public bucket URL.
            if AWS_S3_REGION_NAME:
                MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
            else:
                MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = _env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = _env("EMAIL_HOST", "")
EMAIL_PORT = int(_env("EMAIL_PORT", "587") or "587")
EMAIL_HOST_USER = _env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _truthy(_env("EMAIL_USE_TLS", "1"))
EMAIL_USE_SSL = _truthy(_env("EMAIL_USE_SSL", "0"))
EMAIL_TIMEOUT = int(_env("EMAIL_TIMEOUT", "15") or "15")
# When true, email failures won't break user flows (useful in dev).
EMAIL_FAIL_SILENTLY = _truthy(_env("EMAIL_FAIL_SILENTLY", "0"))
# Dev fallback: if SMTP isn't configured, use console backend to avoid hard failures.
if not EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = _env("DEFAULT_FROM_EMAIL", "leave-tracker@company.com")
OTP_PROVIDER = _env("OTP_PROVIDER", "smtp").lower()
OTP_FROM_EMAIL = _env("OTP_FROM_EMAIL", DEFAULT_FROM_EMAIL)
RESEND_API_KEY = _env("RESEND_API_KEY", "")
RESEND_API_URL = _env("RESEND_API_URL", "https://api.resend.com/emails")

MANAGER_EMAILS = [e.strip().lower() for e in _env("MANAGER_EMAILS", "").split(",") if e.strip()]

EMAIL_NOTIFY_ON_LEAVE = _truthy(_env("EMAIL_NOTIFY_ON_LEAVE", "0"))
HR_NOTIFICATION_EMAILS = [e.strip() for e in _env("HR_NOTIFICATION_EMAILS", "").split(",") if e.strip()]
