# SWSC Race Results Web Suite

A web-first rewrite of the Stewartby Water Sports Club race entry and scoring tools.
It pairs a FastAPI backend that reuses the club's Portsmouth Yardstick scoring logic
with a modern Next.js front end for race officers.

## Project layout

```
web/
├── backend/      # FastAPI service and shared scoring logic
│   ├── app/      # API entry point
│   ├── data/     # Sample handicap and QE reference files
│   ├── swsc_core/ # Reusable domain models
│   └── tests/    # Pytest coverage for scoring
└── frontend/     # Next.js client application
    └── app/      # App Router pages and components
```

## Prerequisites

- Python 3.11+ (3.12 tested)
- Node.js 18+ (Next.js requirement)
- Git

## Backend

```powershell
cd web\backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --reload
```

### Supabase handicaps

Set these environment variables when you want the API to fetch handicaps from
Supabase instead of the bundled CSV:

- `SUPABASE_URL` – project URL (e.g. `https://<project>.supabase.co`)
- `SUPABASE_SERVICE_ROLE_KEY` *(preferred)* or `SUPABASE_SERVICE_KEY` or `SUPABASE_ANON_KEY`
- `SUPABASE_HANDICAPS_TABLE` *(optional, defaults to `handicaps`)*
- `SUPABASE_SCHEMA` *(optional, defaults to `public`)*
- `SUPABASE_SERIES_TABLE` *(defaults to `series`)*
- `SUPABASE_RACES_TABLE` *(defaults to `races`)*
- `SUPABASE_ENTRIES_TABLE` *(defaults to `entries`)*
- `SUPABASE_SCHEDULE_TABLE` *(defaults to `scheduled_races`)*
- `SUPABASE_PROFILES_TABLE` *(defaults to `profiles`)*

All values can be added to a `.env` file or your deployment configuration. If
the variables are absent the backend continues to read from `data/handicaps.csv`.

### Tests

```powershell
cd web\backend
.venv\Scripts\python -m pytest
```

### Syncing offline changes

If you capture series or scheduled races while Supabase is offline, the backend
stores them in `data/series_local.json` and `data/scheduled_races_local.json`.
After connectivity is restored, push the backlog to Supabase with:

```powershell
cd web\backend
.venv\Scripts\python scripts/sync_local_backlog.py
```

The command exits with a non-zero status if any records fail to sync so you can
retry once the underlying issue is resolved.

## Frontend

Install dependencies and run the development server. The UI expects the API at
`http://localhost:8000` by default; override with `NEXT_PUBLIC_API_BASE_URL` if needed.

```powershell
cd web\frontend
npm install
npm run dev
```

### Race admin area

Race administrators can seed the season plan at `/admin/races`. The page writes to the
`SUPABASE_SCHEDULE_TABLE` and keeps the main scoring form populated with an up-to-date
list of upcoming races.

Series can be created and maintained at `/admin/series`, which persists data to the
`SUPABASE_SERIES_TABLE`. Entries here drive the code/title metadata used across the
site. Grant the service role key access to both tables when hosting on Supabase.

### Member profiles & Supabase auth

Sailors can maintain their personal profile at `/profile`. The page uses Supabase Auth
for registration and relies on a `profiles` table in Supabase to store extra metadata.

Expose these values to the frontend (e.g. copy `frontend/.env.local.example` to `frontend/.env.local` and fill in the values):

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

Create a table to hold the extended profile fields:

```sql
create table if not exists public.profiles (
    id uuid primary key references auth.users on delete cascade,
    date_of_birth date,
    gender text,
    boats jsonb default '[]'::jsonb,
    updated_at timestamptz default now()
);

alter table public.profiles enable row level security;
create policy "Users can manage their profile" on public.profiles
    for all using (auth.uid() = id) with check (auth.uid() = id);
```

The `boats` JSON array stores objects with `className` and `sailNumber` keys so the
frontend can render and edit the fleet information for each sailor. The optional
`date_of_birth` column is captured via the profile form as a calendar input.
Gender is collected through a dropdown and stored as `female` or `male`.

Race sign-on pulls helm and crew suggestions from this table together with the
linked Supabase Auth user record. Ensure each user has a populated
`user_metadata.full_name` (added automatically for Google OAuth or when you set a
display name via the Supabase dashboard) so their name appears in the entry sheet.
Boats saved in the profile are used to prioritise class choices and sail numbers
whenever that sailor is selected as a helm or crew.

If a sailor hasn’t completed their profile yet, the race sheet still lists them by
reading the Supabase Auth user directory via the service role key. Populate the
display name (or at least an email) in Supabase Auth so the fallback entry is
readable.

If you're migrating from an earlier revision that used a `competitors` table with an
integer `age` column, rename the table and swap the field for the new date value:

```sql
alter table public.competitors rename to profiles;
alter table public.profiles drop column if exists age;
alter table public.profiles add column if not exists date_of_birth date;
```

For OAuth sign-in, enable the **Google** provider in Supabase Auth and add
`http://localhost:3000/profile` (plus your production URL) to the **Redirect URLs** list.
No extra backend configuration is required—the frontend calls
`supabase.auth.signInWithOAuth({ provider: "google" })` and Supabase redirects back to
the profile page once authentication completes.

## Deployment

- **Backend (Render / container):** build command `pip install -r requirements.txt`,
  start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- **Frontend (Render static site):** `npm install && npm run build` as build command,
  `npm run start` if deploying as a Node service. Configure `NEXT_PUBLIC_API_BASE_URL`
  to point at the deployed FastAPI endpoint.

## Offline packaging

For an all-in-one desktop bundle, ship the FastAPI backend with an embedded Python
runtime (PyInstaller, Briefcase, or docker-desktop) and serve the production Next.js
build via a local Node or static file server. The web client continues to call the
FastAPI endpoints on `http://127.0.0.1:<port>` for a fully offline workflow.
