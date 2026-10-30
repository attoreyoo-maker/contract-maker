-- Supabase Storage 의 docs 버킷에 화면(로그인 없이 공개용 키로 접속)에서
-- 문서를 올리고, 올라온 목록을 볼 수 있게 허용한다.
-- 몇 번을 다시 실행해도 오류가 나지 않는다.

begin;

-- 1. docs 버킷이 없으면 만든다 (이미 있으면 설정을 건드리지 않는다)
--    문서는 주소만으로 아무나 열지 못하게 비공개로 만든다. 화면에서는 잠시 쓰는 주소로 연다
insert into storage.buckets (id, name, public)
values ('docs', 'docs', false)
on conflict (id) do nothing;

-- 2. 예전에 넣은 같은 이름의 허용을 지우고 새로 넣는다
drop policy if exists "docs_select" on storage.objects;
drop policy if exists "docs_insert" on storage.objects;

-- 올라온 목록 보기: docs 버킷 안의 파일만
create policy "docs_select" on storage.objects
  for select to anon, authenticated
  using (bucket_id = 'docs');

-- 문서 올리기: docs 버킷 안에만
create policy "docs_insert" on storage.objects
  for insert to anon, authenticated
  with check (bucket_id = 'docs');

commit;

-- 3. 확인: 아래처럼 두 줄이 나오면 허용이 들어간 것이다
--    docs_insert | INSERT | {anon,authenticated} | true
--    docs_select | SELECT | {anon,authenticated} | true
select policyname, cmd, roles,
       exists (select 1 from storage.buckets where id = 'docs') as docs_bucket_exists
from pg_policies
where schemaname = 'storage' and tablename = 'objects' and policyname like 'docs_%'
order by policyname;
