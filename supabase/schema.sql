-- ============================================================
-- MAHLE Production Management System — Supabase Schema
-- Run this entire file in Supabase SQL Editor
-- ============================================================

-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- ============================================================
-- MASTER TABLES
-- ============================================================

create table if not exists lines (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  is_active boolean default true,
  created_at timestamptz default now()
);

create table if not exists models (
  id uuid primary key default uuid_generate_v4(),
  line_id uuid references lines(id) on delete cascade,
  name text not null,
  is_active boolean default true,
  created_at timestamptz default now()
);

create table if not exists product_master (
  id uuid primary key default uuid_generate_v4(),
  model_id uuid references models(id) on delete cascade,
  product_id text not null unique,
  description text,
  hourly_rate numeric(10,2) default 0,
  eq_factor numeric(6,3) default 1,
  no_of_persons integer default 1,
  pitch_time numeric(8,3) default 0,
  te_time numeric(8,3) default 0,
  man_time numeric(8,3) default 0,
  machine_time numeric(8,3) default 0,
  handling_unit integer default 1,
  cost numeric(12,2) default 0,
  product_type text check (product_type in ('type1','type2','type3')),
  cycle_time numeric(8,3) default 0,
  is_active boolean default true,
  created_at timestamptz default now()
);

create table if not exists shifts (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  start_time time not null,
  end_time time not null,
  is_active boolean default true,
  created_at timestamptz default now()
);

create table if not exists downtime_reasons (
  id uuid primary key default uuid_generate_v4(),
  reason text not null,
  category text,
  is_active boolean default true,
  created_at timestamptz default now()
);

-- ============================================================
-- USER ROLES TABLE (links to Supabase Auth)
-- ============================================================

create table if not exists user_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  name text not null,
  email text not null,
  role text not null default 'viewer' check (role in ('admin','operator','viewer')),
  is_active boolean default true,
  created_at timestamptz default now()
);

-- ============================================================
-- PRODUCTION TABLES
-- ============================================================

create table if not exists production_entries (
  id uuid primary key default uuid_generate_v4(),
  date date not null,
  line_id uuid references lines(id),
  model_id uuid references models(id),
  product_id uuid references product_master(id),
  shift_id uuid references shifts(id),
  target integer not null default 0,
  output integer not null default 0,
  manpower integer not null default 0,
  hours_worked numeric(4,2) default 8,
  entered_by uuid references user_profiles(id),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists downtime_entries (
  id uuid primary key default uuid_generate_v4(),
  production_entry_id uuid references production_entries(id) on delete cascade,
  reason_id uuid references downtime_reasons(id),
  duration_minutes integer not null default 0,
  remarks text,
  created_at timestamptz default now()
);

-- ============================================================
-- INDEXES
-- ============================================================

create index if not exists idx_production_date on production_entries(date);
create index if not exists idx_production_line on production_entries(line_id);
create index if not exists idx_production_model on production_entries(model_id);
create index if not exists idx_models_line on models(line_id);
create index if not exists idx_products_model on product_master(model_id);
create index if not exists idx_downtime_entry on downtime_entries(production_entry_id);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

alter table lines enable row level security;
alter table models enable row level security;
alter table product_master enable row level security;
alter table shifts enable row level security;
alter table downtime_reasons enable row level security;
alter table user_profiles enable row level security;
alter table production_entries enable row level security;
alter table downtime_entries enable row level security;

-- Admins can do everything
create policy "admin_all_lines" on lines for all using (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'admin')
);
create policy "admin_all_models" on models for all using (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'admin')
);
create policy "admin_all_products" on product_master for all using (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'admin')
);
create policy "admin_all_shifts" on shifts for all using (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'admin')
);
create policy "admin_all_reasons" on downtime_reasons for all using (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'admin')
);
create policy "admin_all_users" on user_profiles for all using (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'admin')
);
create policy "admin_all_production" on production_entries for all using (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'admin')
);
create policy "admin_all_downtime" on downtime_entries for all using (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'admin')
);

-- Operators: read master, write own production entries
create policy "operator_read_lines" on lines for select using (
  exists (select 1 from user_profiles where id = auth.uid() and role in ('operator','viewer'))
);
create policy "operator_read_models" on models for select using (
  exists (select 1 from user_profiles where id = auth.uid() and role in ('operator','viewer'))
);
create policy "operator_read_products" on product_master for select using (
  exists (select 1 from user_profiles where id = auth.uid() and role in ('operator','viewer'))
);
create policy "operator_read_shifts" on shifts for select using (
  exists (select 1 from user_profiles where id = auth.uid() and role in ('operator','viewer'))
);
create policy "operator_read_reasons" on downtime_reasons for select using (
  exists (select 1 from user_profiles where id = auth.uid() and role in ('operator','viewer'))
);
create policy "operator_own_production" on production_entries for insert with check (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'operator')
  and entered_by = auth.uid()
);
create policy "operator_read_production" on production_entries for select using (
  exists (select 1 from user_profiles where id = auth.uid() and role in ('operator','viewer'))
);
create policy "operator_update_own" on production_entries for update using (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'operator')
  and entered_by = auth.uid()
  and date = current_date
);
create policy "operator_downtime_insert" on downtime_entries for insert with check (
  exists (select 1 from user_profiles where id = auth.uid() and role = 'operator')
);
create policy "operator_downtime_read" on downtime_entries for select using (
  exists (select 1 from user_profiles where id = auth.uid() and role in ('operator','viewer'))
);

-- Self-read for user profile
create policy "self_read_profile" on user_profiles for select using (id = auth.uid());

-- ============================================================
-- SEED DATA
-- ============================================================

insert into lines (name) values
  ('Line 1'), ('Line 2'), ('Line 3'),
  ('Line 4'), ('Line 5'), ('Line 6')
on conflict do nothing;

insert into shifts (name, start_time, end_time) values
  ('Hour 1', '06:00', '07:00'),
  ('Hour 2', '07:00', '08:00'),
  ('Hour 3', '08:00', '09:00'),
  ('Hour 4', '09:00', '10:00'),
  ('Hour 5', '10:00', '11:00'),
  ('Hour 6', '11:00', '12:00'),
  ('Hour 7', '12:00', '13:00'),
  ('Hour 8', '13:00', '14:00')
on conflict do nothing;

insert into downtime_reasons (reason, category) values
  ('Machine Breakdown', 'Machine'),
  ('Material Shortage', 'Material'),
  ('Power Failure', 'Utility'),
  ('Quality Rejection', 'Quality'),
  ('Manpower Absence', 'Manpower'),
  ('Tool Change', 'Machine'),
  ('Planned Maintenance', 'Machine'),
  ('Line Changeover', 'Process')
on conflict do nothing;
