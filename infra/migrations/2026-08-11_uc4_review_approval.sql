-- UC4: store the therapist's decision with the review that records it.
--
-- Do not reuse learning_activities.status: GENERATED / VALIDATED / FLAGGED
-- describe UC3's automated generation and validation lifecycle.

alter table public.reviews add column if not exists approval_status text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'reviews_approval_status_check'
      and conrelid = 'public.reviews'::regclass
  ) then
    alter table public.reviews
      add constraint reviews_approval_status_check
      check (approval_status in ('APPROVED', 'REJECTED'));
  end if;
end $$;

notify pgrst, 'reload schema';
