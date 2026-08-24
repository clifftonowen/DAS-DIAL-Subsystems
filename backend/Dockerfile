FROM python:3.11-slim

# Unbuffered so uvicorn's startup errors reach the platform log before the process dies —
# a config failure from Settings.verify() is otherwise swallowed by stdout buffering and the
# container just looks like it exited for no reason.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies in their own layer, before the source copy, so editing app/ does not re-run
# pip install on every deploy.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Non-root. Nothing in the request path writes to the image — PDF export and assessment parsing
# are both in-memory (pdf_renderer._to_pdf uses io.BytesIO, assessment_parser reads the upload
# into memory) — so appuser needs no write access to /app.
#
# /tmp DOES need to stay writable: Starlette spools an UploadFile over ~1MB to a
# SpooledTemporaryFile on disk, so a fully read-only filesystem would 500 on a large assessment
# PDF. That is the one exception; do not add `--read-only` without a tmpfs mount.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Hits the same endpoint the platform's own probe uses. urllib rather than curl because
# python:3.11-slim ships no curl and adding one just for this is a wasted layer.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# One worker. The app is stateless and holds no per-process cache worth warming, so scaling is
# the platform's job (add instances), not uvicorn's.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
