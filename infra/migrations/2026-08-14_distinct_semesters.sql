-- Subsystem 2 — one round trip for the upload form's semester list (UC1).
-- Run in the Supabase SQL editor. No re-ingest needed; this reads what is already there.
--
-- IF IT STILL SEEMS UNAPPLIED, IT IS THE SCHEMA CACHE, NOT THE SQL. PostgREST resolves /rpc/ names
-- from a cached schema and only reloads on NOTIFY. Until it does, the call returns PGRST202 and the
-- repository quietly takes its paged fallback — the endpoint works, just at the old speed, so
-- nothing looks broken. Force it with `notify pgrst, 'reload schema';` or Settings -> API -> Restart.
-- The backend logs a warning naming this file every time the fallback runs; that log is how you
-- tell "migration not applied" from "migration applied and fast".
--
-- WHAT IT REPLACES. `LearnerSittingRepository.distinct_semesters()` needs the ~11 distinct values
-- of one text column. PostgREST has no DISTINCT, so the repository was reading the COLUMN and
-- deduplicating in Python — and because PostgREST caps a response at 1,000 rows and truncates
-- silently, it had to page to stay correct. That is ~23 round trips over ~22,892 rows, every time
-- a therapist opens the upload form, to learn about ten strings.
--
-- The cost is not the scan, it is the wire. One seq scan of a 23k-row table is a few milliseconds
-- server-side; 23 sequential HTTPS requests from the API to Supabase is ~2 seconds from a laptop
-- and worse from a CI runner. That latency is why UC1's browser tests have to wait on the form's
-- served metadata before touching it: until this resolved, the semester select held only a
-- "Loading…" placeholder and `handleSubmit` bailed on its `!semester` guard.
--
-- NO INDEX, DELIBERATELY. `idx_sittings_learner` is (learner_id, semester desc) and leads with the
-- wrong column, so this does a sequential scan. At 23k rows that is not worth a second index to
-- avoid — the win here is 23 network round trips becoming 1, not the scan itself. Revisit if the
-- table grows an order of magnitude.
--
-- `stable`, not `volatile`: it only reads, so Postgres may cache it within a statement.
--
-- NOT APPLIED TO `peer_marks`, which pages this same table. That one needs every row to compute
-- percentiles over a (semester, band_group) population — there is no DISTINCT to push down, and
-- the rows themselves are the answer.

create or replace function distinct_semesters()
returns table (semester text)
language sql
stable
as $$
  -- Table alias is required: an unqualified `semester` is ambiguous against the OUT column of
  -- the same name, and ordering by ordinal sidesteps it a second time.
  select distinct ls.semester
  from learner_sittings ls
  where ls.semester is not null
  order by 1 desc;
$$;
