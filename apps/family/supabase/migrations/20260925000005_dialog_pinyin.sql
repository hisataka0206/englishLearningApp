-- 会話練習の拼音の手修正
-- 多音字は自動生成が外すことがあるので、1文字ごとに人が上書きできるようにする。
-- ターン内の {"文字位置": "読み"} を JSON 文字列で持つ（例: {"3":"háng"}）。
-- 実行方法: supabase db push  もしくは ダッシュボードのSQL Editorに貼り付け

alter table dialog_edits add column if not exists py text not null default '';
