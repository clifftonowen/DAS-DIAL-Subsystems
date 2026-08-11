alter table assessment_records
  add column if not exists writing_score float,
  add column if not exists phonics_score float,
  add column if not exists word_reading_score float,
  add column if not exists word_spelling_score float;

alter table assessment_records drop column if exists metric;