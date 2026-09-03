"""DAS D.I.A.L API entrypoint. Run: uvicorn app.main:app --reload"""
import hashlib
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.routers import (auth, learners, profiles, activities,
                         assessments, reviews, share, dashboard)

# Fail at boot, not per request. The embedding provider and the vector column it ranks
# against must agree, and a mismatch is invisible at every other layer — see Settings.verify.
settings.verify()


# Startup fingerprint of the credentials this process ACTUALLY received. Added after five
# successive theories about why the deployed container got "400 API key not valid" from Gemini
# while the identical key worked locally and the stored Azure secret tested clean — clobbered env
# vars, a stale secret binding, trailing whitespace, command ordering, and a failed restart were
# each proposed and each wrong. None of them could be settled by inspecting Azure from outside,
# because every one of those explanations produces the same symptom.
#
# Length and a TRUNCATED SHA-256, never any characters of the credential itself. An earlier
# version logged the last four characters, which is common practice but still copies key material
# out of the secret store and into a log system with different access control and retention —
# especially wrong for SUPABASE_KEY, which is a service-role JWT.
#
# The hash is as diagnostic and leaks nothing: compare it against a locally computed
# `sha256(known_good).hexdigest()[:8]` to prove same-or-different without either side revealing
# the value. 8 hex characters is far too short to attack, and a preimage would need the key
# already. Goes to the platform log, not to /health, which is public.
def _fingerprint(name: str, value: str) -> str:
    if not value:
        return f"{name}=MISSING/EMPTY"
    digest = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"{name}=len:{len(value)} sha256:{digest} stripped_len:{len(value.strip())}"


print(
    "[startup] "
    + "  ".join([
        _fingerprint("GEMINI_API_KEY", settings.gemini_api_key),
        _fingerprint("SUPABASE_KEY", settings.supabase_key),
        f"embedding_provider={settings.embedding_provider}",
        f"embedding_model={settings.gemini_embedding_model}",
        f"use_embedding_alt={settings.use_embedding_alt}",
        f"min_similarity={settings.min_similarity}",
    ]),
    flush=True,
)

app = FastAPI(title=settings.app_name)


# WHY THIS EXISTS: an unhandled exception is turned into "500 Internal Server Error" by
# Starlette's ServerErrorMiddleware, which sits OUTSIDE the middleware stack — so CORSMiddleware
# never sees that response and cannot put `access-control-allow-origin` on it. The browser then
# rejects it as a CORS failure, and `fetch` throws "Failed to fetch" with no status and no body.
#
# The cost is that every server-side bug reaches the UI disguised as a network error. A dead
# Gemini key surfaced in production as "Failed to fetch" on Generate Activity, pointing at the
# network instead of at the 500 the API was actually returning.
#
# Catching here, INSIDE the CORS layer, means the response goes back out through CORSMiddleware
# and keeps its headers, so the browser can read the status and `api.js` can show `detail`.
#
# ORDER IS LOAD-BEARING: `add_middleware` inserts at the front, so the LAST one added is the
# outermost. CORSMiddleware must therefore be added AFTER this to wrap it.
@app.middleware("http")
async def keep_cors_headers_on_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        # Logged in full, returned in summary: the traceback belongs in the platform log, not in
        # a response body on a public deployment.
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"detail": "The server hit an unexpected error. Please try again."},
        )


app.add_middleware(
    CORSMiddleware,
    # strip() so "a, b" in .env works — an origin with a stray space silently fails
    # to match, and a blocked origin looks like a network error, not a config error.
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, learners, profiles, activities, assessments, reviews, share, dashboard):
    app.include_router(r.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
