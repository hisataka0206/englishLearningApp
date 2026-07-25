-- 家族版 初期スキーマ（family-edition-spec.md §5.1）
-- 実行方法: supabase db push  もしくは ダッシュボードのSQL Editorに貼り付け

-- ============================================================ tables
create table if not exists profiles (
  id uuid primary key references auth.users on delete cascade,
  display_name text not null default '',
  default_lang text not null default 'en',          -- 'en' | 'zh'
  default_rate numeric not null default 0.9,        -- 0.4〜1.5
  default_split_mode text not null default 'fine',  -- 'normal'|'fine'|'sentence'
  last_active_at timestamptz,                       -- 家族間で共有する唯一の情報
  created_at timestamptz not null default now()
);

create table if not exists sentences (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  lang text not null default 'en',
  japanese text not null,
  target text not null,        -- 旧 english
  marked text,                 -- 区切り「/」込み。null なら target と同じ
  pinyin text,
  memo text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists sentences_user_lang_created_idx
  on sentences (user_id, lang, created_at desc);

create table if not exists words (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  lang text not null default 'en',
  word text not null,
  meaning text not null default '',
  example text not null default '',
  pinyin text,
  source_id uuid references sentences on delete set null,
  created_at timestamptz not null default now()
);
create index if not exists words_user_lang_created_idx
  on words (user_id, lang, created_at desc);

create table if not exists fails (
  id bigserial primary key,
  user_id uuid not null references auth.users on delete cascade,
  sentence_id uuid not null references sentences on delete cascade,
  label text not null default 'Fail',
  occurred_at timestamptz not null default now()
);
create index if not exists fails_sentence_idx on fails (sentence_id);
create index if not exists fails_user_time_idx on fails (user_id, occurred_at desc);

create table if not exists practices (
  id bigserial primary key,
  user_id uuid not null references auth.users on delete cascade,
  sentence_id uuid not null references sentences on delete cascade,
  occurred_at timestamptz not null default now()
);
create index if not exists practices_sentence_idx on practices (sentence_id);
create index if not exists practices_user_time_idx on practices (user_id, occurred_at desc);

-- 家族版では全員 'family'。事業版への布石
create table if not exists subscriptions (
  user_id uuid primary key references auth.users on delete cascade,
  plan text not null default 'family',
  status text not null default 'active',
  updated_at timestamptz not null default now()
);

-- 使用量ログ（原価の実測が目的）
create table if not exists usage_logs (
  id bigserial primary key,
  user_id uuid references auth.users on delete cascade,
  kind text not null,            -- 'translate' | 'keywords'
  model text not null,
  input_tokens int not null default 0,
  output_tokens int not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists usage_logs_user_time_idx on usage_logs (user_id, created_at desc);
create index if not exists usage_logs_kind_time_idx on usage_logs (kind, created_at desc);

-- ============================================================ RLS
alter table profiles      enable row level security;
alter table sentences     enable row level security;
alter table words         enable row level security;
alter table fails         enable row level security;
alter table practices     enable row level security;
alter table subscriptions enable row level security;
alter table usage_logs    enable row level security;

drop policy if exists "own rows" on sentences;
create policy "own rows" on sentences for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own rows" on words;
create policy "own rows" on words for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own rows" on fails;
create policy "own rows" on fails for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own rows" on practices;
create policy "own rows" on practices for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- profiles: 自分の行だけ。他人のプロフィールは一切見せない
drop policy if exists "own profile" on profiles;
create policy "own profile" on profiles for all
  using (auth.uid() = id) with check (auth.uid() = id);

-- ★ かつて "family read"（for select using (true)）で家族の最終利用日を共有していたが廃止した。
--   理由: ①評価に必要な利用状況は practices テーブルからSQLで取れる（exit-plan §6）
--         ②公開URL運用では anon キー保持者に全プロフィールが読めてしまう
--         ③事業版で削除必須の負債を、必要のない機能のために先に作ることになる
--   復活させないこと。
drop policy if exists "family read" on profiles;

-- subscriptions / usage_logs: 本人が読むだけ。書き込みはサービスロール限定
drop policy if exists "own read" on subscriptions;
create policy "own read" on subscriptions for select using (auth.uid() = user_id);

drop policy if exists "own read" on usage_logs;
create policy "own read" on usage_logs for select using (auth.uid() = user_id);

-- ============================================================ triggers
-- auth.users 作成時に profiles と subscriptions を自動作成
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1)))
  on conflict (id) do nothing;

  insert into public.subscriptions (user_id, plan, status)
  values (new.id, 'family', 'active')
  on conflict (user_id) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- sentences.updated_at 自動更新
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists sentences_touch_updated_at on sentences;
create trigger sentences_touch_updated_at
  before update on sentences
  for each row execute function public.touch_updated_at();

-- 実施記録が入ったら last_active_at を更新（spec §5.3）
create or replace function public.touch_last_active()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  update public.profiles set last_active_at = now() where id = new.user_id;
  return new;
end;
$$;

drop trigger if exists practices_touch_last_active on practices;
create trigger practices_touch_last_active
  after insert on practices
  for each row execute function public.touch_last_active();
