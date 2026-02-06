from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
import os


def _truthy_env(name: str, default: str = "0") -> bool:
    """Parse boolean-ish env vars, tolerating accidental surrounding quotes."""
    val = os.getenv(name, default)
    if val is None:
        return False
    val = str(val).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        val = val[1:-1].strip()
    return val.lower() in {"1", "true", "yes", "y", "on"}


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("portal.urls")),
    path("leave/", include("leave.urls")),
]

# In production, user-uploaded media should be served from object storage (S3/Cloudinary).
# For small demos (Railway/etc), allow opt-in media serving via Django by setting SERVE_MEDIA=1.
# We also auto-enable this on Railway so profile photos work out-of-the-box.
IS_RAILWAY = any(k.startswith("RAILWAY_") for k in os.environ)
if settings.DEBUG or _truthy_env("SERVE_MEDIA", "0") or IS_RAILWAY:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
