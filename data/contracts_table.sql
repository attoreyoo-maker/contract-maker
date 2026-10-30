-- 앱(app.py)에서 "만들기"로 만든 계약서를 쌓아 두는 Supabase 의 contracts 표를 만든다.
-- 이미 표가 있으면 그대로 두므로, 여러 번 실행해도 쌓인 계약서는 지워지지 않는다.

begin;

-- 1. 표 만들기
create table if not exists public.contracts (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  form       text not null default '',  -- 고른 양식 이름 (화면 1 에서 양식별로 묶을 때 쓴다)
  partner    text not null,
  amount     text not null,
  date       text not null,             -- 화면에 넣은 글 그대로 (예: 2026.09.17)
  content    text not null
);

-- 2. 화면(로그인 없이 anon 키로 접속)에서 읽기·넣기만 허용
alter table public.contracts enable row level security;

drop policy if exists "contracts_select" on public.contracts;
create policy "contracts_select" on public.contracts
  for select to anon, authenticated using (true);

drop policy if exists "contracts_insert" on public.contracts;
create policy "contracts_insert" on public.contracts
  for insert to anon, authenticated with check (true);

grant select, insert on public.contracts to anon, authenticated;

commit;
