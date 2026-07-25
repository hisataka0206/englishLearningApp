// データアクセス層（family-edition-spec.md §7.2）
// 現行の api(path, opts) シグネチャを維持したまま、中身を Supabase に差し替える。
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { CONFIG } from "./config.js";

export const sb = createClient(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_ANON_KEY);

let cachedUser = null;

export async function currentUser() {
  if (cachedUser) return cachedUser;
  const { data } = await sb.auth.getSession();
  cachedUser = data.session?.user ?? null;
  return cachedUser;
}

export function onAuthChange(cb) {
  sb.auth.onAuthStateChange((_e, session) => {
    cachedUser = session?.user ?? null;
    cb(cachedUser);
  });
}

export async function signIn(email, password) {
  const { data, error } = await sb.auth.signInWithPassword({ email, password });
  if (error) throw new Error(loginMessage(error.message));
  cachedUser = data.user;
  return data.user;
}

export async function signOut() {
  await sb.auth.signOut();
  cachedUser = null;
}

function loginMessage(msg) {
  if (/invalid login credentials/i.test(msg)) return "メールアドレスかパスワードが違います";
  if (/email not confirmed/i.test(msg)) return "メールが未確認です（管理者に連絡してください）";
  return msg;
}

function qs(path) {
  const [p, q] = path.split("?");
  return [p, new URLSearchParams(q || "")];
}

async function uid() {
  const u = await currentUser();
  if (!u) throw new Error("ログインが必要です");
  return u.id;
}

/** Edge Function 呼び出し（{ok,data} エンベロープを解く） */
async function invoke(name, body) {
  const { data, error } = await sb.functions.invoke(name, { body });
  if (error) {
    // Edge Function が非2xxを返した場合、本文のerrorを取り出す
    let msg = error.message || "接続できません";
    try {
      const ctx = await error.context?.json?.();
      if (ctx?.error) msg = ctx.error;
      if (error.context?.status === 401) { await signOut(); location.hash = "#/login"; }
    } catch { /* noop */ }
    throw new Error(msg);
  }
  if (data && data.ok === false) throw new Error(data.error || "エラーが発生しました");
  return data?.data ?? data;
}

/**
 * 現行APIと同じパスで呼べる薄いラッパ。
 *   api("/api/sentences?lang=en")            → 一覧
 *   api("/api/translate", {japanese, lang})  → Edge Function
 */
export async function api(path, opts) {
  const [p, params] = qs(path);
  const lang = opts?.lang ?? params.get("lang") ?? "en";

  switch (p) {
    // ---------------------------------------------------------------- LLM
    case "/api/translate":
      return invoke("translate", { japanese: opts.japanese, lang });

    case "/api/keywords":
      return invoke("keywords", { target: opts.target ?? opts.english, japanese: opts.japanese, lang });

    // ---------------------------------------------------------------- 文
    case "/api/sentences": {
      if (!opts) {                       // GET: 一覧
        const { data, error } = await sb
          .from("sentences")
          .select("id, lang, japanese, target, marked, pinyin, created_at, fails(count), practices(id, occurred_at)")
          .eq("lang", lang)
          .order("created_at", { ascending: false })
          .limit(200);
        if (error) throw new Error(error.message);
        return (data ?? []).map((s) => {
          const pr = (s.practices ?? []).map((x) => x.occurred_at).sort();
          return {
            id: s.id, english: s.target, japanese: s.japanese,
            marked: s.marked || s.target, pinyin: s.pinyin || "",
            created: (s.created_at || "").slice(0, 10),
            fail_count: s.fails?.[0]?.count ?? 0,
            practice_count: pr.length,
            last_practiced: pr.length ? pr[pr.length - 1].slice(0, 10) : "",
          };
        });
      }
      const row = {                      // POST: 新規 or 上書き
        user_id: await uid(), lang,
        japanese: opts.japanese ?? "", target: opts.english,
        marked: opts.marked || opts.english, pinyin: opts.pinyin || null,
      };
      if (opts.id) {
        const { error } = await sb.from("sentences").update(row).eq("id", opts.id);
        if (error) throw new Error(error.message);
        return { id: opts.id, updated: true };
      }
      const { data, error } = await sb.from("sentences").insert(row).select("id").single();
      if (error) throw new Error(error.message);
      return { id: data.id };
    }

    case "/api/delete": {
      const { error } = await sb.from("sentences").delete().eq("id", opts.id);
      if (error) throw new Error(error.message);
      return { deleted: opts.id };
    }

    // ---------------------------------------------------------------- 単語
    case "/api/words": {
      if (!opts) {
        const { data, error } = await sb
          .from("words")
          .select("id, word, meaning, example, pinyin, created_at")
          .eq("lang", lang)
          .order("created_at", { ascending: false })
          .limit(500);
        if (error) throw new Error(error.message);
        return (data ?? []).map((w) => ({
          id: w.id, word: w.word, meaning: w.meaning, example: w.example,
          pinyin: w.pinyin || "", created: (w.created_at || "").slice(0, 10),
        }));
      }
      const { data, error } = await sb.from("words").insert({
        user_id: await uid(), lang, word: opts.word,
        meaning: opts.meaning ?? "", example: opts.example ?? "",
        pinyin: opts.pinyin || null, source_id: opts.source_id || null,
      }).select("id").single();
      if (error) throw new Error(error.message);
      return { id: data.id };
    }

    case "/api/words/delete": {
      const { error } = await sb.from("words").delete().eq("id", opts.id);
      if (error) throw new Error(error.message);
      return { deleted: opts.id };
    }

    // ---------------------------------------------------------------- 履歴記録
    case "/api/fail": {
      const { error } = await sb.from("fails").insert({
        user_id: await uid(), sentence_id: opts.id, label: opts.label ?? "Fail",
      });
      if (error) throw new Error(error.message);
      const { count } = await sb.from("fails")
        .select("id", { count: "exact", head: true }).eq("sentence_id", opts.id);
      return { fail_count: count ?? 0 };
    }

    case "/api/practice": {
      const { error } = await sb.from("practices").insert({
        user_id: await uid(), sentence_id: opts.id,
      });
      if (error) throw new Error(error.message);
      const { count } = await sb.from("practices")
        .select("id", { count: "exact", head: true }).eq("sentence_id", opts.id);
      return { practice_count: count ?? 0, last_practiced: new Date().toISOString().slice(0, 10) };
    }

    // ---------------------------------------------------------------- プロフィール
    case "/api/profile": {
      if (!opts) {
        const { data, error } = await sb.from("profiles")
          .select("id, display_name, default_lang, default_rate, default_split_mode, last_active_at");
        if (error) throw new Error(error.message);
        const me = await uid();
        return {
          me: data.find((p) => p.id === me) ?? null,
          family: data.filter((p) => p.id !== me)
            .map((p) => ({ name: p.display_name, last: (p.last_active_at || "").slice(0, 10) })),
        };
      }
      const { error } = await sb.from("profiles").update(opts).eq("id", await uid());
      if (error) throw new Error(error.message);
      return { ok: true };
    }

    default:
      throw new Error("unknown api path: " + p);
  }
}
