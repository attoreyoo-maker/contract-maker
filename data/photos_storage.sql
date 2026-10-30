-- Supabase Storage 의 photos 버킷에 화면(로그인 없이 공개용 키로 접속)에서
-- 그림을 올리고, 올라온 목록을 볼 수 있게 허용한다.
-- 몇 번을 다시 실행해도 오류가 나지 않는다.

begin;

-- 1. photos 버킷이 없으면 만든다 (이미 있으면 설정을 건드리지 않는다)
insert into storage.buckets (id, name, public, allowed_mime_types)
values ('photos', 'photos', true, array['image/png', 'image/jpeg', 'image/gif', 'image/webp'])
on conflict (id) do nothing;

-- 2. 예전에 넣은 같은 이름의 허용을 지우고 새로 넣는다
drop policy if exists "photos_select" on storage.objects;
drop policy if exists "photos_insert" on storage.objects;

-- 올라온 목록 보기: photos 버킷 안의 파일만
create policy "photos_select" on storage.objects
  for select to anon, authenticated
  using (bucket_id = 'photos');

-- 그림 올리기: photos 버킷 안에만
create policy "photos_insert" on storage.objects
  for insert to anon, authenticated
  with check (bucket_id = 'photos');

commit;

-- 3. 확인: 아래처럼 두 줄이 나오면 허용이 들어간 것이다
--    photos_insert | INSERT | {anon,authenticated} | true
--    photos_select | SELECT | {anon,authenticated} | true
select policyname, cmd, roles,
       exists (select 1 from storage.buckets where id = 'photos') as photos_bucket_exists
from pg_policies
where schemaname = 'storage' and tablename = 'objects' and policyname like 'photos_%'
order by policyname;
