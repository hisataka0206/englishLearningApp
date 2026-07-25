-- 使用量ログに「課金単位」を持たせる（family-edition-spec.md §5.1）
--
-- 背景: usage_logs は Gemini のトークン数を前提にした列構成だった。
--       Azure Speech の発音評価は【音声の長さ】で課金されるため、
--       input_tokens / output_tokens では原価が測れない（常に0で記録される）。
--       評価期間の実測データが取れないと GO/NO-GO 条件C を判定できない。

alter table usage_logs
  add column if not exists audio_seconds numeric not null default 0,
  add column if not exists calls int not null default 1;

comment on column usage_logs.audio_seconds is
  'Azure Speech の課金単位。kind=''assess'' のときに録音の長さ（秒）を入れる';
comment on column usage_logs.calls is
  '1行あたりの外部API呼び出し回数。中国語の発音評価は「採点＋参照なし認識」で2回呼ぶ';
comment on column usage_logs.model is
  '実際に呼んだモデル／サービス名（例: gemini-2.5-flash-lite, azure-speech-f0）';

-- 月次の集計を軽くする
create index if not exists usage_logs_kind_month
  on usage_logs (kind, created_at desc);

-- ── keepalive 用の ping ────────────────────────────────────────────
-- Supabase Free は1週間無操作で一時停止する。GitHub Actions が週1回叩く。
--
-- テーブルを直接 SELECT する方式にしていたが、RLSポリシーの変更で
-- 結果が変わりうる（実際 "family read" を廃止した）。
-- security definer の関数にして、**RLSから独立**させる。
create or replace function public.ping()
returns timestamptz
language sql
security definer set search_path = public
as $$ select now(); $$;

revoke all on function public.ping() from public;
grant execute on function public.ping() to anon, authenticated;

comment on function public.ping() is
  'keepalive 専用。DBに必ず到達させるためだけの関数。情報は返さない';
