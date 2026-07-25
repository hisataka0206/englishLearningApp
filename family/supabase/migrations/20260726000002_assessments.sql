-- 発音評価の記録（現行 assessments.json 相当）
-- ※ 棚卸し表に記載が漏れていたが、本アプリの中核機能のため家族版に含める

create table if not exists assessments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  lang text not null default 'zh',            -- 'en' | 'zh'
  text text not null,                          -- 読み上げた文（正解）
  heard text,                                  -- 実際に聞こえた文（zhのみ・分類に使う）
  source text not null default '',             -- 'compose' 等
  scores jsonb not null default '{}'::jsonb,   -- {pron, accuracy, fluency, completeness, prosody}
  words jsonb not null default '[]'::jsonb,    -- [{w,s,e,wp,ws,k,kc,hd,hc,ep,ph}]
  created_at timestamptz not null default now()
);
create index if not exists assessments_user_lang_time_idx
  on assessments (user_id, lang, created_at desc);

alter table assessments enable row level security;

drop policy if exists "own rows" on assessments;
create policy "own rows" on assessments for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- 発音チェックも「利用した」とみなして最終利用日を更新
create or replace function public.touch_last_active_assess()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  update public.profiles set last_active_at = now() where id = new.user_id;
  return new;
end;
$$;

drop trigger if exists assessments_touch_last_active on assessments;
create trigger assessments_touch_last_active
  after insert on assessments
  for each row execute function public.touch_last_active_assess();
