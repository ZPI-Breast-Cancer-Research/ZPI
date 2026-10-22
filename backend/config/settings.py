"""Django settings – every deployment-specific value comes from the environment (.env)."""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    POSTGRES_HOST=(str, "localhost"),
    POSTGRES_PORT=(int, 5432),
    ORTHANC_URL=(str, "http://orthanc:8042"),
    ORTHANC_PUBLIC_URL=(str, "http://localhost:8042"),
    ORTHANC_USER=(str, ""),
    ORTHANC_PASSWORD=(str, ""),
    CELERY_BROKER_URL=(str, "redis://localhost:6379/0"),
    MLFLOW_TRACKING_URI=(str, "http://mlflow:5000"),
)

# Local runs outside docker: pick up the repo-level .env if present.
_env_file = BASE_DIR.parent / ".env"
if _env_file.exists():
    environ.Env.read_env(_env_file)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "users",
    "patients",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
        "OPTIONS": {"connect_timeout": 3},
    }
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Authentication/roles are out of scope for the skeleton.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")

# Orthanc is an external service (separate setup); the backend only talks to it over HTTP.
ORTHANC_URL = env("ORTHANC_URL").rstrip("/")
ORTHANC_PUBLIC_URL = env("ORTHANC_PUBLIC_URL").rstrip("/")
# Optional HTTP basic auth – used only when both are set.
ORTHANC_USER = env("ORTHANC_USER")
ORTHANC_PASSWORD = env("ORTHANC_PASSWORD")

MLFLOW_TRACKING_URI = env("MLFLOW_TRACKING_URI").rstrip("/")

CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_TASK_ROUTES = {
    "segmentation.correction_to_dicom_seg": {"queue": "segmentation-convert"},
    "segmentation.*": {"queue": "segmentation"},
    "extraction.*": {"queue": "extraction"},
    "training.*": {"queue": "training"},
}
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
