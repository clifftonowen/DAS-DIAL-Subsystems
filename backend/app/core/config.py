"""Central configuration loaded from environment (.env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""          # service-role key, backend only
    supabase_jwt_secret: str = ""   # used to verify auth tokens

    # LLM — completion and embedding are selected SEPARATELY, so the generator can move between
    # vendors freely while the embedder (the expensive one to change) stays put.
    #
    # What changing the EMBEDDING provider actually costs, now that Matryoshka models can output
    # 768 dims to match curriculum_chunks: not a migration, but still a full re-embed AND a
    # re-derived `min_similarity` below — every model has its own score band, and a gate tuned to
    # one model's band silently refuses (or admits) the wrong things on another's.
    llm_provider: str = "ollama"          # completion: "ollama" | "gemini" | "claude" | "openai"
    embedding_provider: str = "ollama"    # embeddings: "ollama" | "gemini" | "openai"

    # Which vector column retrieval ranks against: False => `embedding` (nomic-embed-text,
    # the incumbent), True => `embedding_alt` (gemini-embedding-001, the challenger). See
    # infra/migrations/2026-08-10_curriculum_embedding_alt.sql for why two columns exist.
    #
    # THIS MUST AGREE WITH `embedding_provider`, and the failure mode when it does not is the
    # reason it is a setting rather than a per-call argument. Embedding a query with one model
    # and ranking it against another model's vectors is not an error — cosine similarity is
    # perfectly happy to compare two unrelated spaces and return confident nonsense. Nothing
    # raises, nothing logs, the activity just gets grounded in the wrong chunks. `verify()`
    # below refuses to boot on a mismatch so that a half-flipped .env fails loudly instead.
    #
    # Deploying on Gemini therefore means BOTH `EMBEDDING_PROVIDER=gemini` and
    # `USE_EMBEDDING_ALT=true` — plus a re-derived `min_similarity`, since the gate is
    # per-model (see below).
    use_embedding_alt: bool = False

    # Retrieval gate: top-chunk cosine similarity below this => refuse without calling the LLM.
    # PROVIDER-SPECIFIC, which is why it is a setting and not a constant — two people evaluating
    # two embedders need two values at once. Derive it with scripts/calibrate_gate.py; never guess.
    #
    # 0.67 is nomic-embed-text's CALIBRATED gate, not a guess: measured junk_max 0.66857 against
    # real_min 0.67046 over the golden set (docs/MODEL_EVALUATION.md §4). It replaces a hand-picked
    # 0.50 that admitted 2 of the 7 junk queries outright — junk_maths_lookalike scored 0.6686 and
    # junk_football 0.5458, and Guardrail 2 (model self-refusal) catches only ~1 in 8, so the gate
    # was the only thing standing between an off-topic request and a fabricated activity.
    #
    # THE MARGIN IS 0.0019. That is real but thin: one unlucky in-domain query scoring at the
    # bottom of its band gets refused. Do not treat this number as settled — the experiment that
    # would widen it is nomic WITH its task prefixes (see ollama_use_task_prefixes below), and
    # gemini-embedding-001 already separates 21x better (window 0.041, gate 0.71) if the ranking
    # trade-off is ever judged worth it.
    # MEASURED 2026-09-03, and it complicates everything above: the golden set is NOT
    # representative of the queries this app actually sends. calibrate_gate derives its numbers
    # from hand-written natural queries ("adverb ly suffix practice"), but the production query
    # builder emits a thin, generic string with a mark fraction in it —
    # "literacy activity targeting phonics 3.8/10" — which embeds to a noticeably weaker vector.
    #
    # Across 9 seeded learners those production queries score 0.6666-0.7359, against a worst junk
    # probe (junk_maths_lookalike) of 0.6859. The distributions OVERLAP: two real learners score
    # BELOW that junk query, so no threshold both admits every learner and refuses every probe.
    # calibrate_gate would report "no safe threshold" if it were fed these queries.
    #
    # The deployed value is 0.60 (set in the deploy job), chosen knowingly: 9/9 learners at the
    # cost of admitting that one near-miss probe. 0.70 would be 7/9 with nothing admitted.
    #
    # THE GATE IS NOT THE BUG. Fix the query builder to emit concept and stage language matching
    # the corpus rather than a mark fraction, then re-derive this against production-shaped
    # queries and tighten it again.
    min_similarity: float = 0.50

    # Gemini backend — generation and embedding are separate classes with separate models.
    gemini_api_key: str = ""
    # gemini-2.5-pro is listed by the models endpoint but 404s on generateContent for keys
    # issued after it closed to new users — pick a model, then verify it actually answers.
    gemini_model: str = "gemini-3.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_temperature: float = 0.0

    # NOT gemini-embedding-2, despite it being the newer model. Measured on this corpus
    # (240 probes, backend/eval/): -001 scores MRR 0.697 / recall@1 0.533 against -2's
    # 0.613 / 0.429, and separates junk from real queries nearly twice as widely. The cause is
    # concrete, not noise — -2 accepts `taskType` and ignores it (RETRIEVAL_QUERY and
    # RETRIEVAL_DOCUMENT return bit-identical vectors), so it cannot embed a query differently
    # from a document, and this is an asymmetric retrieval task. -2's one advantage, an 8192-token
    # window against -001's 2048, buys nothing here: the largest chunk in the corpus is ~1561.
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dim: int = 768   # Matryoshka truncation; matches vector(768), no migration

    # Anthropic backend (generation only — Anthropic serves no embedding model)
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_version: str = "2023-06-01"
    claude_model: str = "claude-sonnet-5"
    # None => omit the field entirely, which is REQUIRED on the Claude 5 family: they reject
    # `temperature` outright ("`temperature` is deprecated for this model", HTTP 400) rather than
    # ignoring it. Set a float only for an older model that still accepts one. Note this means
    # Claude has no temperature-0 lever at all, so it cannot offer even Gemini's weak determinism.
    claude_temperature: float | None = None
    # REQUIRED by the Messages API — there is no "unlimited". Sized for a full activity with
    # room to spare; a too-small cap truncates mid-step and reads downstream as a short activity,
    # not as an error.
    claude_max_tokens: int = 4096

    # OpenAI backend
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Ollama backend (local; run `ollama serve`)
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.2:latest"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_embedding_dim: int = 768  # nomic-embed-text; matches vector(768) for curriculum_chunks
    # nomic-embed-text is TRAINED to expect "search_query: " / "search_document: " prefixes and
    # retrieval is measurably worse without them — but the stored corpus was embedded without, so
    # turning this on alone pairs prefixed queries against unprefixed documents and makes things
    # WORSE. Flip it and re-embed in the same change, or leave it alone.
    ollama_use_task_prefixes: bool = False

    # Generation sampling. Temperature 0 + fixed seed is reproducible ON OLLAMA ONLY: Gemini
    # treats seed as best-effort and only when explicitly passed, and Claude has no seed at all.
    ollama_temperature: float = 0.0
    ollama_seed: int = 42

    # App
    app_name: str = "DAS D.I.A.L"

    # Whether POST /auth/signup will create accounts. Defaults TRUE so local development and the
    # UC8 sign-up tests behave exactly as before; the public demo deployment sets
    # SIGNUP_ENABLED=false and logs visitors in with a seeded demo therapist instead.
    #
    # Turning this off matters because the app is publicly reachable and every generated activity
    # spends Gemini quota against one shared key — an open sign-up form on a public URL is an
    # open invitation to spend it. Close it in the Supabase dashboard too ("Allow new users to
    # sign up"), but THIS is the flag that counts: the UI posts to AuthController, not to
    # Supabase, so the dashboard toggle alone would leave this route creating accounts.
    signup_enabled: bool = True
    # Comma-separated browser origins allowed to call the API. Since the UI signs in
    # through AuthController rather than talking to Supabase directly, log-in itself
    # is now a cross-origin request, so an origin missing here breaks authentication
    # outright — the browser rejects the response and fetch fails with
    # "Failed to fetch", with no status for the UI to report.
    #
    # An origin is scheme + host + port, and localhost is NOT the same origin as
    # 127.0.0.1, so both spellings of both ports are listed: 5173 is `npm run dev`,
    # 4173 is `npm run preview` (the built app the Selenium system tests drive).
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )

    #smtp for email 
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    def verify(self) -> None:
        """Refuse to start on a configuration that would serve confident nonsense.

        Called from app.main at import. It checks the ONE pairing that fails silently:
        `embedding_provider` decides which model embeds the query, `use_embedding_alt` decides
        which column that vector is ranked against, and every other layer treats a mismatch as
        a perfectly ordinary retrieval. `embedding_alt` holds gemini-embedding-001 vectors, so
        the two agree exactly when the provider is gemini.

        Deliberately NOT validated here: `min_similarity`. It is a float with no wrong value
        that can be detected from config alone — 0.50 is right for one model and far too loose
        for another, and only scripts/calibrate_gate.py can tell them apart.
        """
        wants_alt = self.embedding_provider == "gemini"
        if wants_alt and not self.use_embedding_alt:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=gemini needs USE_EMBEDDING_ALT=true: gemini embeds the "
                "query, but `embedding` holds nomic-embed-text vectors. Ranking one against "
                "the other returns plausible-looking nonsense rather than an error."
            )
        if not wants_alt and self.use_embedding_alt:
            raise RuntimeError(
                f"USE_EMBEDDING_ALT=true needs EMBEDDING_PROVIDER=gemini, not "
                f"'{self.embedding_provider}': `embedding_alt` holds gemini-embedding-001 "
                f"vectors, so ranking another provider's query vector against it is meaningless."
            )


settings = Settings()
