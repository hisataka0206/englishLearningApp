// POST /functions/v1/translate  （family-edition-spec.md §6.3）
import { CORS, ok, fail, getUser, admin, checkQuota, logUsage, callGemini, clean, validate }
  from "../_shared/common.ts";

// 現行アプリのプロンプトをそのまま移植（小学生ペルソナは必ず維持）
const PROMPTS: Record<string, string> = {
  en: `Translate the Japanese text into natural, conversational English.
The learner is an elementary-school child, so use simple, friendly words
that a kid would actually say. Keep it short and natural.
Output ONLY the English translation. No explanations, no quotes.

Japanese text:
`,
  zh: `Translate the Japanese text into natural, conversational Chinese
(Simplified characters). The learner is an elementary-school child, so use
simple, friendly words that a kid would actually say. Keep it short and natural.
Output ONLY the Chinese translation. No explanations, no quotes, no pinyin.

Japanese text:
`,
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return fail("POST only", 400);

  const user = await getUser(req);
  if (!user) return fail("ログインが必要です", 401);

  let body: { japanese?: string; lang?: string };
  try { body = await req.json(); } catch { return fail("bad json", 400); }

  const japanese = (body.japanese ?? "").trim();
  const lang = body.lang ?? "en";
  const bad = validate(japanese, lang);
  if (bad) return bad;

  const sb = admin();
  const quota = await checkQuota(sb, user.id, "translate");
  if (!quota.allowed) return fail("今月の上限に達しました", 402);

  const { text, usage, status } = await callGemini(PROMPTS[lang] + japanese);
  if (status === 429) return fail("少し待ってから再試行してください", 429);
  if (status === 504) return fail("時間内に応答がありませんでした", 504);
  const target = clean(text);
  if (!target) return fail("翻訳サービスに接続できません", 502);

  await logUsage(sb, user.id, "translate", usage);
  return ok({ target });   // ピンインはクライアントで計算する
});
