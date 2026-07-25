// Edge Function 共通処理（family-edition-spec.md §6.1〜6.5）
import { createClient, SupabaseClient } from "jsr:@supabase/supabase-js@2";

export const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

export const MAX_INPUT_CHARS = Number(Deno.env.get("MAX_INPUT_CHARS") ?? 300);
export const MODEL = Deno.env.get("GEMINI_MODEL") ?? "gemini-2.5-flash-lite";

export function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data }), {
    status: 200, headers: { ...CORS, "Content-Type": "application/json" },
  });
}

export function fail(message: string, status = 400) {
  return new Response(JSON.stringify({ ok: false, error: message }), {
    status, headers: { ...CORS, "Content-Type": "application/json" },
  });
}

/** JWTを検証して user_id を返す。無効なら null */
export async function getUser(req: Request): Promise<{ id: string } | null> {
  const auth = req.headers.get("Authorization") ?? "";
  const token = auth.replace(/^Bearer\s+/i, "");
  if (!token) return null;
  const sb = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
    { global: { headers: { Authorization: auth } } },
  );
  const { data, error } = await sb.auth.getUser(token);
  if (error || !data.user) return null;
  return { id: data.user.id };
}

/** サービスロールのクライアント（usage_logs 書き込み・profiles更新用） */
export function admin(): SupabaseClient {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } },
  );
}

/**
 * クォータ判定。家族版では 'family' を無条件に通す。
 * 事業版ではここに月次上限の判定を足す（コードパスだけ先に用意する）。
 */
export async function checkQuota(sb: SupabaseClient, userId: string, _kind: string) {
  const { data } = await sb.from("subscriptions").select("plan, status")
    .eq("user_id", userId).maybeSingle();
  const plan = data?.plan ?? "family";
  if (plan === "family") return { allowed: true, plan };
  return { allowed: true, plan };  // 事業版でここを実装
}

/** 使用量の記録と最終利用日の更新（失敗しても本処理は止めない） */
export async function logUsage(
  sb: SupabaseClient, userId: string, kind: string, usage: Record<string, number> | undefined,
) {
  try {
    await sb.from("usage_logs").insert({
      user_id: userId, kind, model: MODEL,
      input_tokens: usage?.promptTokenCount ?? 0,
      output_tokens: usage?.candidatesTokenCount ?? 0,
    });
    await sb.from("profiles").update({ last_active_at: new Date().toISOString() })
      .eq("id", userId);
  } catch (e) {
    console.error("[logUsage]", e);
  }
}

/** Gemini 呼び出し。戻り値は本文とトークン使用量 */
export async function callGemini(prompt: string, jsonMode = false) {
  const key = Deno.env.get("GEMINI_API_KEY");
  if (!key) throw new Response("LLM未設定", { status: 502 });
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${key}`;
  const body: Record<string, unknown> = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: 0.3,   // 現行と同じ
      ...(jsonMode ? { responseMimeType: "application/json" } : {}),
    },
  };
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);   // 30秒（spec §6.1）
  try {
    const r = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: ctrl.signal,
    });
    if (!r.ok) {
      const t = await r.text();
      console.error("[gemini]", r.status, t.slice(0, 300));
      return { text: "", usage: undefined, status: r.status === 429 ? 429 : 502 };
    }
    const j = await r.json();
    const text = j?.candidates?.[0]?.content?.parts?.map((p: { text?: string }) => p.text ?? "").join("") ?? "";
    return { text, usage: j?.usageMetadata, status: 200 };
  } catch (e) {
    console.error("[gemini]", e);
    return { text: "", usage: undefined, status: (e as Error).name === "AbortError" ? 504 : 502 };
  } finally {
    clearTimeout(timer);
  }
}

/** 前後の引用符などを除去（現行 _clean 相当） */
export function clean(text: string) {
  return (text ?? "").replace(/<think>[\s\S]*?(<\/think>|$)/g, "").trim()
    .replace(/^["'「『]+|["'」』]+$/g, "").trim();
}

/** 入力の共通バリデーション */
export function validate(japanese: string, lang: string) {
  if (!japanese?.trim()) return fail("japanese is required", 400);
  if (!["en", "zh"].includes(lang)) return fail("lang must be en or zh", 400);
  if (japanese.length > MAX_INPUT_CHARS) return fail("入力が長すぎます", 413);
  return null;
}
