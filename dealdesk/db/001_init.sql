-- Sinder Deal Desk: first Postgres schema (Neon). Applied once by the db-migrate workflow; idempotent.
-- Two kinds of tables: SHARED market data (written by the GitHub pipeline, read by everyone) and WORKSPACE data
-- (one customer's users, profiles, watchlists, projects), always filtered by workspace_id. Row-level security on
-- every workspace table makes a missing filter fail closed instead of leaking another customer's data.

create extension if not exists pg_trgm;

-- ---------- shared market data ----------
create table if not exists opportunities (
  id            text primary key,          -- e.g. TED-741571-2026
  source        text not null,
  stage         text not null default 'tender',   -- tender | planned
  title         text not null,
  title_original text,
  buyer         text,
  country       char(3),
  region        text,
  sector        text,
  commodity_group text,
  hs6           text,
  value_usd     numeric,
  deadline      date,
  access        text,                       -- intl | set-aside | ''
  route         text,                       -- direct | sub-supply | via local partner | needs local partner
  engine_score  smallint,
  decision      text,                       -- Pursue | Watch | Ignore
  link          text,
  contact       text,
  first_seen    timestamptz not null default now(),
  updated       timestamptz not null default now()
);
create index if not exists opp_country on opportunities (country);
create index if not exists opp_sector on opportunities (sector);
create index if not exists opp_deadline on opportunities (deadline);
create index if not exists opp_title_trgm on opportunities using gin (title gin_trgm_ops);

create table if not exists requirements (     -- conditions extracted from tender documents (AI, once per tender)
  opportunity_id text references opportunities(id) on delete cascade,
  kind          text not null,              -- certification | experience | guarantee | turnover | local_presence | other
  value         text not null,
  source_ref    text,
  primary key (opportunity_id, kind, value)
);

create table if not exists buyers (
  id text primary key, name text not null, country char(3), awards_12m int, median_award_usd numeric,
  next_expected date, updated timestamptz default now()
);
create table if not exists suppliers (
  id text primary key, name text not null, country char(3), sector text, groups text[], tier char(1),
  website text, email text, phone text, legal_id text, updated timestamptz default now()
);
create index if not exists sup_name_trgm on suppliers using gin (name gin_trgm_ops);
create table if not exists prices (
  item_id text, as_of date, price numeric, unit text, currency text, source text, primary key (item_id, as_of)
);
create table if not exists market_signals (
  hs6 text, country text, year int, imports_usd numeric, growth_pct numeric, premium_pct numeric,
  signal_score smallint, trend_change_pct numeric, updated timestamptz default now(), primary key (hs6, country)
);
create table if not exists ai_cache (          -- one AI result per item, shared by every user who opens it
  item_key text, kind text, lang char(2), result text not null, cost_usd numeric, created timestamptz default now(),
  primary key (item_key, kind, lang)
);

-- ---------- workspace (customer) data ----------
create table if not exists workspaces (
  id uuid primary key default gen_random_uuid(), name text not null, plan text not null default 'explorer',
  ai_quota_month int not null default 10, active_projects int not null default 0, created timestamptz default now()
);
create table if not exists users (
  email text primary key, workspace_id uuid not null references workspaces(id), name text, role text not null default 'viewer',
  status text not null default 'pending', pass_hash text, via text, created timestamptz default now(),
  approved_by text, approved_at timestamptz, last_login timestamptz
);
create table if not exists profiles (
  email text primary key references users(email) on delete cascade, workspace_id uuid not null references workspaces(id),
  data jsonb not null, updated timestamptz default now()
);
create table if not exists watchlist (
  workspace_id uuid not null references workspaces(id), email text not null, opportunity_id text not null,
  kind text not null default 'saved',        -- saved | hidden
  created timestamptz default now(), primary key (email, opportunity_id, kind)
);
create table if not exists activity (
  id bigserial primary key, workspace_id uuid, email text, role text, action text not null, target text, detail text,
  cost_usd numeric, at timestamptz not null default now()
);
create index if not exists act_ws_at on activity (workspace_id, at desc);
create table if not exists usage_month (
  workspace_id uuid, month char(7), ai_runs int default 0, cost_usd numeric default 0, primary key (workspace_id, month)
);

-- Row-level security: the app sets `set local app.workspace = '<uuid>'` per request.
do $$ declare t text; begin
  foreach t in array array['users','profiles','watchlist','activity','usage_month'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists ws_isolation on %I', t);
    execute format($p$create policy ws_isolation on %I using (workspace_id = nullif(current_setting('app.workspace', true), '')::uuid)$p$, t);
  end loop;
end $$;
