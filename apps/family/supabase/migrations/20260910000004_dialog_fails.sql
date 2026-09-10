-- 会話練習（ロールプレイ）のミス記録
-- 記事本編と同じく「1文字ごと」に記録する（scope は dialog_id + turn_idx + ci）。
-- 実行方法: supabase db push  もしくは ダッシュボードのSQL Editorに貼り付け

create table if not exists dialog_fails (
  id bigserial primary key,
  user_id uuid not null references auth.users on delete cascade,
  dialog_id text not null,                       -- dialogs_zh.json の id（airport など）
  turn_idx int not null,                         -- ターン番号（1始まり）
  ci int not null,                               -- ターン内の文字位置（0始まり）
  char text not null,
  syllable text not null default '',
  label text not null default 'Fail',
  occurred_at timestamptz not null default now(),
  unique (user_id, dialog_id, turn_idx, ci)
);
create index if not exists dialog_fails_user_idx on dialog_fails (user_id, dialog_id);
create index if not exists dialog_fails_time_idx on dialog_fails (user_id, occurred_at desc);

alter table dialog_fails enable row level security;

drop policy if exists "own rows" on dialog_fails;
create policy "own rows" on dialog_fails for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
