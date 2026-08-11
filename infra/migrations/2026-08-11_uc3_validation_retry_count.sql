-- UC3: record how many regenerations the validate loop needed before it settled.
--
-- ActivityGraph now runs GenerativeAgent -> ValidativeAgent and reprompts with the reviewer's
-- notes until the draft passes or the retries run out. Before this, `status` was written as a
-- hardcoded 'GENERATED' on every row, so the two other values the column already allowed
-- (VALIDATED / FLAGGED) were unreachable and the dashboard's flagged counter was structurally 0.
--
-- WHY THE COUNT IS STORED AND NOT JUST RETURNED. "Validated on the third attempt" is a claim
-- about how hard this activity was to ground, and it is the signal that tells you a band's
-- corpus is thin before the therapist complains. It is gone the moment the response is, and no
-- other column implies it: a VALIDATED row that needed two rewrites and one that passed straight
-- away are otherwise identical.
--
-- 0 is the right default for existing rows. Every one of them was written by the pre-loop code
-- path, which made exactly one generation call, and one attempt is zero retries.

alter table public.learning_activities
  add column if not exists retry_count integer not null default 0;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'learning_activities_retry_count_check'
      and conrelid = 'public.learning_activities'::regclass
  ) then
    alter table public.learning_activities
      add constraint learning_activities_retry_count_check
      check (retry_count >= 0);
  end if;
end $$;

notify pgrst, 'reload schema';
