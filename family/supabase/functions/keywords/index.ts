// POST /functions/v1/keywords  （family-edition-spec.md §6.4）
import { CORS, ok, fail, getUser, admin, checkQuota, logUsage, callGemini, validate }
  from "../_shared/common.ts";

const PROMPT = (lang: string) => {
  const L = lang === "zh" ? "Chinese" : "English";
  return `From the ${L} sentence below, pick up to 3 keywords/phrases
worth memorizing for a Japanese learner.
Rules:
- "word" MUST be ${L}, copied exactly from the ${L} sentence.
- "meaning" MUST be Japanese, copied from the original Japanese text below
  (the expression that corresponds to the word). Do NOT invent a new translation.
Respond ONLY with JSON: {"keywords": [{"word": "...", "meaning": "..."}]}
`;
};

// 現行 §7.1 の入替補正（移植必須）
const HAS_JAPANESE = /[぀-ヿ㐀-鿿]/;   // かな＋漢字
const HAS_KANA = /[぀-ゟ゠-ヿ]/;       // かなのみ

function fixPairs(list: Array<{ word?: string; meaning?: string }>, lang: string) {
  const bad = (s: string) => (lang === "zh" ? HAS_KANA : HAS_JAPANESE).test(s ?? "");
  const out: Array<{ word: string; meaning: string }> = [];
  for (const k of list ?? []) {
    let w = (k?.word ?? "").trim();
    let m = (k?.meaning ?? "").trim();
    if (!w) continue;
    if (bad(w) && !bad(m)) { const t = w; w = m; m = t; }   // 逆なら入れ替え
    if (bad(w) || !w) continue;                             // それでも不正なら除外
    out.push({ word: w, meaning: m });
  }
  return out.slice(0, 3);
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return fail("POST only", 400);

  const user = await getUser(req);
  if (!user) return fail("ログインが必要です", 401);

  let body: { target?: string; japanese?: string; lang?: string };
  try { body = await req.json(); } catch { return fail("bad json", 400); }

  const target = (body.target ?? "").trim();
  const japanese = (body.japanese ?? "").trim();
  const lang = body.lang ?? "en";
  if (!target) return fail("target is required", 400);
  const bad = validate(japanese || "-", lang);
  if (bad) return bad;

  const sb = admin();
  const quota = await checkQuota(sb, user.id, "keywords");
  if (!quota.allowed) return fail("今月の上限に達しました", 402);

  const label = lang === "zh" ? "Chinese" : "English";
  const prompt = `${PROMPT(lang)}
${label} sentence:
${target}

Original Japanese text:
${japanese}
`;
  const { text, usage, status } = await callGemini(prompt, true);
  if (status === 429) return fail("少し待ってから再試行してください", 429);
  if (status === 504) return fail("時間内に応答がありませんでした", 504);

  let parsed: { keywords?: Array<{ word?: string; meaning?: string }> } = {};
  try {
    parsed = JSON.parse(text);
  } catch {
    const m = text.match(/\{[\s\S]*\}/);      // JSON修復（現行 §41）
    if (m) { try { parsed = JSON.parse(m[0]); } catch { /* noop */ } }
  }

  const keywords = fixPairs(parsed.keywords ?? [], lang);
  await logUsage(sb, user.id, "keywords", usage);
  return ok({ keywords });   // ピンインはクライアントで計算する
});
