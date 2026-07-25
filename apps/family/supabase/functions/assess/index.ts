// POST /functions/v1/assess — Azure 発音評価のプロキシ
// クライアントから 16kHz mono WAV を受け取り、Azure Speech で採点する。
// Azureキーはここにのみ存在する（クライアントには出さない）。
//
// 中国語では「実際に何と発音したか」を得るため、参照なし認識も1回行う。
// R/V/T/N の分類はクライアント側（pinyin-pro を持っている）で行う。
import { CORS, ok, fail, getUser, admin, checkQuota, logUsage } from "../_shared/common.ts";

const REGION = Deno.env.get("AZURE_SPEECH_REGION") ?? "japaneast";
const KEY = Deno.env.get("AZURE_SPEECH_KEY") ?? "";
const WAV_CT = "audio/wav; codecs=audio/pcm; samplerate=16000";

async function azureAssess(audio: ArrayBuffer, refText: string, locale: string) {
  const params = {
    ReferenceText: refText,
    GradingSystem: "HundredMark",
    Granularity: "Phoneme",
    Dimension: "Comprehensive",
    EnableProsodyAssessment: true,
  };
  const hdr = btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(params))));
  const url = `https://${REGION}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=${locale}`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Ocp-Apim-Subscription-Key": KEY,
      "Pronunciation-Assessment": hdr,
      "Content-Type": WAV_CT,
      "Accept": "application/json",
    },
    body: audio,
  });
  if (!r.ok) {
    console.error("[azure assess]", r.status, (await r.text()).slice(0, 200));
    return null;
  }
  return await r.json();
}

/** 参照テキストなしの認識（実際の発音を得る） */
async function azureRecognize(audio: ArrayBuffer, locale: string) {
  const url = `https://${REGION}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=${locale}`;
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: {
        "Ocp-Apim-Subscription-Key": KEY,
        "Content-Type": WAV_CT,
        "Accept": "application/json",
      },
      body: audio,
    });
    if (!r.ok) return "";
    const j = await r.json();
    return j?.DisplayText ?? "";
  } catch { return ""; }
}

/** Azureの生レスポンスを整形（現行 azure_speech.summarize の移植） */
function summarize(res: Record<string, any>) {
  const nb = res?.NBest?.[0];
  if (!nb) return null;
  const pa = nb.PronunciationAssessment ?? nb;   // RESTは NBest 直下
  const words = (nb.Words ?? []).map((w: Record<string, any>) => {
    const wpa = w.PronunciationAssessment ?? w;
    const ph: Array<[string, number]> = (w.Phonemes ?? [])
      .map((p: Record<string, any>) => [p.Phoneme ?? "", Math.round(p.AccuracyScore ?? 0)]);
    const worst = ph.length ? ph.reduce((a, b) => (b[1] < a[1] ? b : a)) : null;
    return {
      word: w.Word ?? "",
      score: Math.round(wpa.AccuracyScore ?? 0),
      error: wpa.ErrorType ?? "None",
      phoneme_scores: ph,
      worst: worst ? { name: worst[0], score: worst[1] } : null,
    };
  });
  return {
    recognized: nb.Display ?? "",
    scores: {
      pron: Math.round(pa.PronScore ?? 0),
      accuracy: Math.round(pa.AccuracyScore ?? 0),
      fluency: Math.round(pa.FluencyScore ?? 0),
      completeness: Math.round(pa.CompletenessScore ?? 0),
      prosody: pa.ProsodyScore ? Math.round(pa.ProsodyScore) : null,
    },
    words,
  };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return fail("POST only", 400);
  if (!KEY) return fail("発音評価が未設定です（AZURE_SPEECH_KEY）", 502);

  const user = await getUser(req);
  if (!user) return fail("ログインが必要です", 401);

  let form: FormData;
  try { form = await req.formData(); } catch { return fail("bad form-data", 400); }

  const text = String(form.get("text") ?? "").trim();
  const lang = String(form.get("lang") ?? "zh");
  const file = form.get("audio");
  if (!text) return fail("text is required", 400);
  if (!(file instanceof File)) return fail("audio is required", 400);
  if (file.size > 8 * 1024 * 1024) return fail("録音が長すぎます", 413);

  const sb = admin();
  const quota = await checkQuota(sb, user.id, "assess");
  if (!quota.allowed) return fail("今月の上限に達しました", 402);

  const audio = await file.arrayBuffer();
  const locale = lang === "zh" ? "zh-CN" : "en-US";

  const raw = await azureAssess(audio, text, locale);
  if (!raw) return fail("発音評価サービスに接続できません", 502);
  const data = summarize(raw);
  if (!data) return fail("認識できませんでした（もう一度録音してください）", 200);

  // 中国語のみ、実際に聞こえた文も返す（R/V/T/N分類はクライアントで行う）
  const heard = lang === "zh" ? await azureRecognize(audio, locale) : "";

  await logUsage(sb, user.id, "assess", undefined);
  return ok({ ...data, heard });
});
