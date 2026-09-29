"""Django settings for KabQue."""

from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "insecure-dev-key")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]
# Render injects this automatically — prevents Host header 400s in production
_render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "queueapp.apps.QueueappConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "kabque.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "kabque.wsgi.application"


def _database_from_url(url: str) -> dict:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    options = {}
    if "sslmode" in qs:
        options["sslmode"] = qs["sslmode"][0]
    # Reuse connections across requests (Neon SSL handshake is expensive each time).
    conn_max_age = int(os.getenv("DB_CONN_MAX_AGE", "60"))
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (parsed.path or "/").lstrip("/") or "neondb",
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
        "OPTIONS": options,
        "CONN_MAX_AGE": max(0, conn_max_age),
        "CONN_HEALTH_CHECKS": True,
    }


DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:
    DATABASES = {"default": _database_from_url(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Kampala"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "queueapp.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True
if DEBUG:
    # Local browser variants (LAN IP, etc.) during development
    CORS_ALLOW_ALL_ORIGINS = True

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "https://kabque.onrender.com,https://kab-que.vercel.app",
    ).split(",")
    if o.strip()
]
if _render_host:
    _origin = f"https://{_render_host}"
    if _origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_origin)


EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "KabQue <noreply@kabale.ac.ug>")


def _clean_env(value: str) -> str:
    """Strip whitespace, BOM, and wrapping quotes from env values."""
    text = (value or "").strip().lstrip("\ufeff").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


# Brevo (Sendinblue) transactional email — used when BREVO_API_KEY is set
BREVO_API_KEY = _clean_env(os.getenv("BREVO_API_KEY", ""))
BREVO_SENDER_EMAIL = _clean_env(os.getenv("BREVO_SENDER_EMAIL", ""))
BREVO_SENDER_NAME = _clean_env(os.getenv("BREVO_SENDER_NAME", "KabQue")) or "KabQue"

# Kabale University Kikungiri Campus (production geofence).
CAMPUS_LATITUDE = float(os.getenv("CAMPUS_LATITUDE", "-1.272215"))
CAMPUS_LONGITUDE = float(os.getenv("CAMPUS_LONGITUDE", "29.988321"))
CAMPUS_RADIUS_METERS = float(os.getenv("CAMPUS_RADIUS_METERS", "800"))
GPS_ENFORCEMENT = os.getenv("GPS_ENFORCEMENT", "True").lower() in ("1", "true", "yes")
CAMPUS_NAME = os.getenv("CAMPUS_NAME", "Kabale University Kikungiri")
# Legacy QA flag — keep False for campus-only. Env CAMPUS_* is always applied.
NATIONWIDE_GPS_TESTING = os.getenv("NATIONWIDE_GPS_TESTING", "False").lower() in (
    "1",
    "true",
    "yes",
)

# Africa's Talking — SMS delivery
# ENVIRONMENT picks the host. "sandbox" only reaches numbers you registered as
# test numbers in the AT dashboard, and the sender always shows as "sandbox".
# Switch to "production" once you have a live key, credit, and an approved
# alphanumeric sender ID.
AFRICAS_TALKING_ENVIRONMENT = (
    _clean_env(os.getenv("AFRICAS_TALKING_ENVIRONMENT", "sandbox")).lower() or "sandbox"
)
if AFRICAS_TALKING_ENVIRONMENT not in ("sandbox", "production"):
    AFRICAS_TALKING_ENVIRONMENT = "sandbox"

AFRICAS_TALKING_API_KEY = _clean_env(
    os.getenv("AFRICAS_TALKING_API_KEY", "") or os.getenv("AT_API_KEY", "")
)
# The sandbox app username is always literally "sandbox".
AFRICAS_TALKING_USERNAME = (
    _clean_env(os.getenv("AFRICAS_TALKING_USERNAME", "") or os.getenv("AT_USERNAME", ""))
    or ("sandbox" if AFRICAS_TALKING_ENVIRONMENT == "sandbox" else "")
)
# Your approved alphanumeric sender ID (e.g. "KabQue") or numeric shortcode.
# Ignored by AT in the sandbox, where every message shows as "sandbox".
AFRICAS_TALKING_SHORTCODE = _clean_env(
    os.getenv("AFRICAS_TALKING_SHORTCODE", "") or os.getenv("AT_SHORTCODE", "")
)

AFRICAS_TALKING_BASE_URL = (
    "https://api.sandbox.africastalking.com"
    if AFRICAS_TALKING_ENVIRONMENT == "sandbox"
    else "https://api.africastalking.com"
)
