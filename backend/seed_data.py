import os
from dotenv import load_dotenv
from supabase import create_client

# Load backend/.env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_KEY missing in backend/.env")
    exit(1)

sb = create_client(url, key)

learners_data = [
    {"id": "11111111-1111-1111-1111-111111111111", "pseudonym": "Aisha Binti Rahman", "band_level": "Band A2", "tier": "Tier 2"},
    {"id": "22222222-2222-2222-2222-222222222222", "pseudonym": "Benjamin Lim Wei", "band_level": "Band A1", "tier": "Tier 1"},
    {"id": "33333333-3333-3333-3333-333333333333", "pseudonym": "Chen Yu Xuan", "band_level": "Band B", "tier": "Tier 2"},
    {"id": "44444444-4444-4444-4444-444444444444", "pseudonym": "Darren Tan Kai", "band_level": "Band A3", "tier": "Tier 3"},
    {"id": "55555555-5555-5555-5555-555555555555", "pseudonym": "Emily Ng Su Lin", "band_level": "Band C", "tier": "Tier 1"},
    {"id": "66666666-6666-6666-6666-666666666666", "pseudonym": "Farhan Bin Ismail", "band_level": "Band A1", "tier": "Tier 2"},
    {"id": "77777777-7777-7777-7777-777777777777", "pseudonym": "Grace Wong Mei", "band_level": "Band B", "tier": "Tier 1"},
    {"id": "88888888-8888-8888-8888-888888888888", "pseudonym": "Hassan Ali Khan", "band_level": "Band A2", "tier": "Tier 3"},
    {"id": "99999999-9999-9999-9999-999999999999", "pseudonym": "Isabelle Lau Xin", "band_level": "Band A1", "tier": "Tier 1"},
    {"id": "00000000-0000-0000-0000-000000000000", "pseudonym": "Jamal Syed Ahmad", "band_level": "Band C", "tier": "Tier 2"},
]

profiles_data = [
    {"learner_id": "11111111-1111-1111-1111-111111111111", "phonological_processing": 0.35, "decoding": 0.55, "spelling": 0.40, "comprehension": 0.72, "working_memory": 0.28, "executive_functioning": 0.60, "visualisation": 0.65},
    {"learner_id": "22222222-2222-2222-2222-222222222222", "phonological_processing": 0.60, "decoding": 0.45, "spelling": 0.52, "comprehension": 0.38, "working_memory": 0.70, "executive_functioning": 0.55, "visualisation": 0.48},
    {"learner_id": "33333333-3333-3333-3333-333333333333", "phonological_processing": 0.78, "decoding": 0.70, "spelling": 0.65, "comprehension": 0.80, "working_memory": 0.45, "executive_functioning": 0.72, "visualisation": 0.58},
    {"learner_id": "44444444-4444-4444-4444-444444444444", "phonological_processing": 0.20, "decoding": 0.30, "spelling": 0.25, "comprehension": 0.45, "working_memory": 0.35, "executive_functioning": 0.40, "visualisation": 0.50},
    {"learner_id": "55555555-5555-5555-5555-555555555555", "phonological_processing": 0.42, "decoding": 0.38, "spelling": 0.30, "comprehension": 0.55, "working_memory": 0.60, "executive_functioning": 0.50, "visualisation": 0.72},
    {"learner_id": "66666666-6666-6666-6666-666666666666", "phonological_processing": 0.55, "decoding": 0.62, "spelling": 0.58, "comprehension": 0.70, "working_memory": 0.40, "executive_functioning": 0.65, "visualisation": 0.45},
    {"learner_id": "77777777-7777-7777-7777-777777777777", "phonological_processing": 0.85, "decoding": 0.78, "spelling": 0.72, "comprehension": 0.90, "working_memory": 0.65, "executive_functioning": 0.80, "visualisation": 0.70},
    {"learner_id": "88888888-8888-8888-8888-888888888888", "phonological_processing": 0.30, "decoding": 0.25, "spelling": 0.20, "comprehension": 0.35, "working_memory": 0.22, "executive_functioning": 0.28, "visualisation": 0.40},
    {"learner_id": "99999999-9999-9999-9999-999999999999", "phonological_processing": 0.68, "decoding": 0.75, "spelling": 0.70, "comprehension": 0.82, "working_memory": 0.58, "executive_functioning": 0.74, "visualisation": 0.62},
    {"learner_id": "00000000-0000-0000-0000-000000000000", "phonological_processing": 0.50, "decoding": 0.48, "spelling": 0.55, "comprehension": 0.60, "working_memory": 0.42, "executive_functioning": 0.52, "visualisation": 0.58},
]

print("1. Seeding learners...")
res_l = sb.table("learners").upsert(learners_data).execute()
print(f"   Done! Seeded {len(res_l.data)} learners.")

print("2. Seeding learner profiles...")
res_p = sb.table("learner_profiles").upsert(profiles_data).execute()
print(f"   Done! Seeded {len(res_p.data)} learner profiles.")

print("\nAll database data seeded successfully!")
