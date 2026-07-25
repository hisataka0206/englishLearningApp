// 発音評価（録音 → Azure採点 → ミス種類の分類 → 記録）
// 分類（R/V/T/N/F）はここで行う。pinyin-pro がクライアントにあるため。
import { pinyin } from "https://esm.sh/pinyin-pro@3";
import { sb, api, jstDate } from "./data-api.js";

export const REC_LIMIT_SEC = 55;
const KIND_LABEL = { F: "発音", R: "声母(子音)", V: "韻母(母音)", T: "声調", N: "数字2" };
const RETROFLEX = new Set(["zh", "ch", "sh", "r"]);
const FLAT = new Set(["z", "c", "s"]);
const INITIALS = ["zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l",
                  "g", "k", "h", "j", "q", "x", "r", "z", "c", "s", "y", "w"];

// ============================================================ 分類
function splitPy(py) {           // 拼音(数字表記) → [声母, 韻母, 声調]
  const m = /^([a-zü]+?)([1-5]?)$/i.exec(py || "");
  if (!m) return ["", "", ""];
  const body = m[1].toLowerCase(), tone = m[2];
  for (const ini of INITIALS) if (body.startsWith(ini)) return [ini, body.slice(ini.length), tone];
  return ["", body, tone];
}

function pyList(text) {          // 漢字だけを [文字, 拼音(数字)] に
  const chars = Array.from(text || "").filter((c) => /[一-鿿]/.test(c));
  if (!chars.length) return [];
  try {
    const arr = pinyin(chars.join(""), { toneType: "num", type: "array" });
    return chars.map((c, i) => [c, (arr[i] || "").toLowerCase()]);
  } catch { return []; }
}

/** 正解と実際の発音を突き合わせ、文字indexごとに種類を判定 */
export function classify(expectedText, heardText) {
  const exp = pyList(expectedText), heard = pyList(heardText);
  if (!exp.length || !heard.length) return {};
  const out = {};
  // 素朴なアライメント（LCSベースの差分）
  const a = exp.map((x) => x[1]), b = heard.map((x) => x[1]);
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  let i = 0, j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (dp[i + 1][j] >= dp[i][j + 1]) {          // 置換とみなす
      const [ec, ep] = exp[i], [hc, hp] = heard[j];
      const [ei, ef, et] = splitPy(ep), [hi, hf, ht] = splitPy(hp);
      let kind = "F";
      if ((ec === "两" || ec === "二" || hc === "两" || hc === "二") && ec !== hc) kind = "N";
      else if (ei === hi && ef === hf && et !== ht) kind = "T";
      else if (ei !== hi && ef === hf) kind = "R";
      else if (ei === hi && ef !== hf) kind = "V";
      out[i] = {
        kind, label: KIND_LABEL[kind], char: ec, expected: ep, heard: hp, heard_char: hc,
        retroflex: kind === "R" && ((RETROFLEX.has(ei) && FLAT.has(hi)) || (FLAT.has(ei) && RETROFLEX.has(hi))),
      };
      i++; j++;
    } else i++;
  }
  return out;
}

/** summarize結果の words に、文字単位の判定を割り当てる */
export function attachKinds(words, expectedText, heardText) {
  const marks = classify(expectedText, heardText);
  if (!Object.keys(marks).length) return words;
  let idx = 0;
  for (const w of words) {
    const n = Array.from(w.word || "").filter((c) => /[一-鿿]/.test(c)).length;
    const found = [];
    for (let k = idx; k < idx + n; k++) if (marks[k]) found.push(marks[k]);
    idx += n;
    if (found.length && w.error !== "Omission") {
      Object.assign(w, {
        kind: found[0].kind, kind_label: found[0].label, kind_char: found[0].char,
        heard: found[0].heard, heard_char: found[0].heard_char, expected_py: found[0].expected,
      });
    }
  }
  return words;
}

// ============================================================ 録音
let mediaRec = null, chunks = [], timer = null, startAt = 0;
let recUrl = null, recAudio = null, recText = "";
export let lastAssess = null;

export async function toggleRecord(getText, lang, ui) {
  if (mediaRec && mediaRec.state === "recording") return stopRecord(ui);
  const text = getText();
  if (!text) { alert("先に発音する文を表示してください"); return; }
  if (!navigator.mediaDevices?.getUserMedia) {
    alert("録音にはHTTPS接続が必要です");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: {
      channelCount: 1, sampleRate: 16000,
      echoCancellation: false, noiseSuppression: false, autoGainControl: false,
    }});
    chunks = [];
    mediaRec = new MediaRecorder(stream);
    mediaRec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    mediaRec.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: mediaRec.mimeType || "audio/webm" });
      setRecording(blob, text, ui);
      try {
        const wav = await toWav16k(blob);              // webmのままだとAzureの時間軸が壊れる
        await sendAssess(wav, text, lang, ui);
      } catch (e) { ui.showError(e.message); }
    };
    mediaRec.start();
    startAt = Date.now();
    ui.recording(true);
    clearInterval(timer);
    timer = setInterval(() => {
      const sec = Math.floor((Date.now() - startAt) / 1000);
      ui.tick(sec);
      if (sec >= REC_LIMIT_SEC) stopRecord(ui);
    }, 250);
  } catch (e) { alert("マイクを使用できません: " + e.message); }
}

export function stopRecord(ui) {
  clearInterval(timer);
  if (mediaRec && mediaRec.state === "recording") mediaRec.stop();
  ui.recording(false);
}

/** 録音（webm/opus等）を 16kHz mono WAV に変換し、音量を正規化 */
export async function toWav16k(blob) {
  const buf = await blob.arrayBuffer();
  const AC = window.AudioContext || window.webkitAudioContext;
  const decoded = await new AC().decodeAudioData(buf);
  const rate = 16000;
  const off = new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(
    1, Math.ceil(decoded.duration * rate), rate);
  const src = off.createBufferSource();
  src.buffer = decoded; src.connect(off.destination); src.start();
  const pcm = (await off.startRendering()).getChannelData(0);
  let peak = 0;
  for (let i = 0; i < pcm.length; i++) { const a = Math.abs(pcm[i]); if (a > peak) peak = a; }
  const gain = peak > 0.001 ? Math.min(0.7 / peak, 8) : 1;
  const dv = new DataView(new ArrayBuffer(44 + pcm.length * 2));
  const w = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); dv.setUint32(4, 36 + pcm.length * 2, true); w(8, "WAVEfmt ");
  dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
  dv.setUint32(24, rate, true); dv.setUint32(28, rate * 2, true);
  dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
  w(36, "data"); dv.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) {
    const v = Math.max(-1, Math.min(1, pcm[i] * gain));
    dv.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7FFF, true);
  }
  return new Blob([dv.buffer], { type: "audio/wav" });
}

function setRecording(blob, text, ui) {
  if (recUrl) URL.revokeObjectURL(recUrl);
  recUrl = URL.createObjectURL(blob);
  recText = text;
  recAudio = new Audio(recUrl);
  ui.playbackReady(true);
}

export function playMyRec() { if (recAudio) { speechSynthesis.cancel(); recAudio.currentTime = 0; recAudio.play().catch(() => {}); } }
export function modelText() { return recText; }
export function clearRecording(ui) {
  if (recUrl) { URL.revokeObjectURL(recUrl); recUrl = null; }
  recAudio = null; recText = ""; lastAssess = null;
  ui.playbackReady(false); ui.clearResult();
}

async function sendAssess(wav, text, lang, ui) {
  ui.pending();
  const fd = new FormData();
  fd.append("audio", wav, "rec.wav");
  fd.append("text", text);
  fd.append("lang", lang);
  const { data, error } = await sb.functions.invoke("assess", { body: fd });
  if (error) {
    // Azure F0 は同時リクエスト1件。家族が同時に録音すると 429 が返る。
    // サーバー側で2回まで再試行済みなので、ここまで来たら待ってもらう。
    let msg = error.message || "判定できませんでした";
    try {
      const ctx = await error.context?.json?.();
      if (ctx?.error) msg = ctx.error;
    } catch { /* noop */ }
    ui.showError(msg);
    return;
  }
  if (data?.ok === false) { ui.showError(data.error); return; }
  const d = data.data ?? data;
  if (lang === "zh" && d.heard) attachKinds(d.words, text, d.heard);
  lastAssess = d;
  ui.render(d);
  saveAssessment(lang, text, d).catch(() => {});
}

async function saveAssessment(lang, text, d) {
  await api("/api/assessments", {
    lang, text, heard: d.heard || null, scores: d.scores,
    words: d.words.map((w) => ({
      w: w.word, s: w.score, e: w.error,
      wp: w.worst?.name ?? "", ws: w.worst?.score ?? null,
      k: w.kind ?? "", kc: w.kind_char ?? "", hd: w.heard ?? "",
      hc: w.heard_char ?? "", ep: w.expected_py ?? "",
    })),
  });
}

// ============================================================ 集計（記録タブ）
export function aggregateWeak(rows, days = 30) {
  const since = jstDate(new Date(Date.now() - days * 864e5));
  const stat = {};
  rows.filter((a) => jstDate(a.created_at) >= since).forEach((a) => {
    (a.words || []).forEach((w) => {
      if (w.e === "Omission") return;
      const s = stat[w.w] ??= { word: w.w, tries: 0, miss: 0, sum: 0, last: "", kinds: {}, weak: {} };
      s.tries++; s.sum += w.s ?? 0;
      if ((w.e && w.e !== "None") || (w.s ?? 100) < 60) {
        s.miss++;
        if (w.wp) { const d = s.weak[w.wp] ??= { n: 0, sum: 0 }; d.n++; d.sum += w.ws ?? 0; }
        if (w.k) {
          s.kinds[w.k] = (s.kinds[w.k] || 0) + 1;
          s.kind_char = w.kc || s.kind_char; s.heard = w.hd || s.heard; s.expected_py = w.ep || s.expected_py;
        }
      }
      s.last = jstDate(a.created_at);
    });
  });
  return Object.values(stat).filter((s) => s.miss).map((s) => {
    s.avg = Math.round(s.sum / s.tries);
    s.rate = Math.round(100 * s.miss / s.tries);
    const wp = Object.entries(s.weak).sort((x, y) => y[1].n - x[1].n)[0];
    if (wp) s.weakSound = { name: wp[0], score: Math.round(wp[1].sum / wp[1].n) };
    const kd = Object.entries(s.kinds).sort((x, y) => y[1] - x[1])[0];
    if (kd) s.kind = { code: kd[0], label: KIND_LABEL[kd[0]] ?? kd[0], n: kd[1] };
    delete s.sum; delete s.weak; delete s.kinds;
    return s;
  }).sort((x, y) => (y.miss - x.miss) || (y.rate - x.rate));
}
