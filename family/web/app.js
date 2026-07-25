// 家族版 クライアント本体（現行 index.html のコア機能を移植）
import { api, sb, signIn, signOut, currentUser } from "./data-api.js";
import { pinyin } from "https://esm.sh/pinyin-pro@3";
import * as assess from "./assess.js";

// ============================================================ 言語ラベル
const LABELS = {
  en: {
    toBtn: "英語にする", transHead: "英訳 ✏️", sentTab: "英文のみ",
    sentCol: "英文 / 日本語", unit: "英文", delConfirm: "この英文を削除しますか？",
    restudy: "保存済みの英文を再学習中（区切りを編集して保存すると上書きされます）",
    sample: "This is the speaking speed.", ttsLang: "en-US", voicePref: "en", voiceRe: /Samantha/,
  },
  zh: {
    toBtn: "中国語にする", transHead: "中国語訳 ✏️", sentTab: "中国語のみ",
    sentCol: "中国語 / 日本語", unit: "文", delConfirm: "この文を削除しますか？",
    restudy: "保存済みの文を再学習中（区切りを編集して保存すると上書きされます）",
    sample: "这是朗读的速度。", ttsLang: "zh-CN", voicePref: "zh", voiceRe: /Ting|Tingting|Meijia|Sinji/,
  },
};
const FAIL_LABELS = ["Fail"];        // 現行 config.json の fail_labels をクライアント定数へ
const MAX_INPUT = 300;

let lang = "en";
let current = { japanese: "", english: "", marked: "", keywords: [], pageId: null, _breaks: null };
let sentCache = {}, allS = [], allW = [], histTab = "date", sub = "compose";
let explicitBreaks = false, mainBreakMode = false;
let profile = null;

const L = () => LABELS[lang] || LABELS.en;
const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");

function msg(id, text, ok) {
  const el = $(id); if (!el) return;
  el.textContent = text; el.className = "msg " + (ok ? "ok" : "ng");
}

// ============================================================ ピンイン（ローカル計算）
const isHan = (ch) => /[一-鿿]/.test(ch);
const DIGIT_PY = { "0": "líng", "1": "yī", "2": "èr", "3": "sān", "4": "sì",
                   "5": "wǔ", "6": "liù", "7": "qī", "8": "bā", "9": "jiǔ" };

function pinyinOf(text) {
  if (!text) return "";
  try { return pinyin(text, { toneType: "symbol", type: "string" }); } catch { return ""; }
}

function pinyinPairs(text) {
  return Array.from(text || "").map((ch) => {
    if (isHan(ch)) { try { return [ch, pinyin(ch, { toneType: "symbol", type: "string" })]; } catch { return [ch, ""]; } }
    return [ch, DIGIT_PY[ch] || ""];
  });
}

function zhWords(text) {
  try { return pinyin(text, { type: "all" }).map((x) => x.origin); } catch { return []; }
}

// ============================================================ 発音（Web Speech API）
function makeUtter(text) {
  const u = new SpeechSynthesisUtterance(text);
  u.lang = L().ttsLang;
  u.rate = parseFloat($("rate").value);
  const v = speechSynthesis.getVoices().filter((x) => x.lang.startsWith(L().voicePref));
  if (v.length) u.voice = v.find((x) => L().voiceRe.test(x.name)) || v[0];
  return u;
}

function speak(text) { playerStop(); speechSynthesis.cancel(); speechSynthesis.speak(makeUtter(text)); }

function rateChanged(v) {
  $("rateVal").textContent = parseFloat(v).toFixed(2).replace(/0$/, "");
  saveSetting({ default_rate: parseFloat(v) });
}
function setRate(v) { $("rate").value = v; rateChanged(v); speak(L().sample); }

// ============================================================ フレーズ分割
const ENG_BREAK = /\s+(?=(?:and|but|or|nor|so|yet|because|although|though|while|when|whenever|whereas|if|unless|until|since|that|which|who|whose|whom|where|after|before|to|in|on|at|with|for|from|of|about|into|onto|over|under|through|during|between|among|against|without|within)\b)/i;

function autoSplit(text, mode) {
  if (mode === "sentence") return (text.match(/[^.!?]+[.!?]*/g) || [text]).map((s) => s.trim()).filter(Boolean);
  const clauses = text.match(/[^,;:.!?]+[,;:.!?]*/g) || [text];
  const out = [];
  clauses.forEach((c) => {
    c = c.trim(); if (!c) return;
    if (mode !== "fine") { out.push(c); return; }
    const parts = c.split(ENG_BREAK).map((s) => s.trim()).filter(Boolean);
    const merged = [];
    parts.forEach((p) => {
      if (merged.length && p.split(/\s+/).length <= 1) merged[merged.length - 1] += " " + p;
      else merged.push(p);
    });
    if (merged.length > 1 && merged[0].split(/\s+/).length <= 1) merged.splice(0, 2, merged[0] + " " + merged[1]);
    (merged.length ? merged : [c]).forEach((m) => out.push(m));
  });
  return out.length ? out : [text];
}

function zhPunct(text, mode) {
  const re = mode === "sentence" ? /[^。！？]+[。！？]*/g : /[^，。！？、；：]+[，。！？、；：]*/g;
  return (text.match(re) || [text]).map((s) => s.trim()).filter(Boolean);
}

function zhSplit(text, mode) {
  const clean = text.replace(/[/|｜／\s]/g, "");
  if (mode === "sentence") return zhPunct(clean, "sentence");
  if (mode !== "fine") return zhPunct(clean, mode);
  const words = zhWords(clean);
  if (!words.length) return zhPunct(clean, mode);
  const out = [];
  words.forEach((w) => {
    if (/^[，。！？、；：,.!?%（）()]+$/.test(w) && out.length) out[out.length - 1] += w;
    else out.push(w);
  });
  return out.length ? out : [text];
}

function splitPhrases(text, mode) {
  mode = mode || $("splitMode").value;
  if (explicitBreaks) return text.split(/[/|｜／]+/).map((s) => s.trim()).filter(Boolean);
  const segments = text.split(/[/|｜／]+/).map((s) => s.trim()).filter(Boolean);
  const out = [];
  const auto = lang === "zh" ? zhSplit : autoSplit;
  (segments.length ? segments : [text]).forEach((seg) => out.push(...auto(seg, mode)));
  return out.length ? out : [text];
}

// ============================================================ プレイヤー
const player = { text: "", phrases: [], idx: 0, playing: false, gen: 0 };

function playerSetText(text) {
  if (player.text && player.text !== text) assess.clearRecording(assessUI);   // 別の文なら録音を破棄
  player.text = text;
  player.phrases = splitPhrases(text);
  player.idx = 0;
  const box = $("phrases");
  box.innerHTML = "";
  const pairs = lang === "zh" ? player.phrases.map((p) => pinyinPairs(p)) : null;
  player.phrases.forEach((p, i) => {
    const c = document.createElement("span");
    c.className = "chip";
    if (pairs) {
      const py = pairs[i].map((x) => x[1]).filter(Boolean).join(" ");
      c.innerHTML = `${esc(p)}${py ? `<div class="cpy">${esc(py)}</div>` : ""}`;
    } else c.textContent = p;
    c.onclick = () => playerPlayOne(i);
    box.appendChild(c);
  });
  $("player").style.display = "block";
  playerUpdatePad();
}

function playerUpdatePad() {
  document.body.style.paddingBottom = ($("player").offsetHeight + 20) + "px";
}

function playerLoad(text) { speechSynthesis.cancel(); playerSetText(text); playerPlay(); }

function playerRender() {
  document.querySelectorAll("#phrases .chip").forEach((c, i) => {
    c.className = "chip" + (i < player.idx ? " done" : i === player.idx ? " active" : "");
    if (i === player.idx) c.scrollIntoView({ block: "nearest" });
  });
  $("btnPlay").textContent = player.playing ? "⏸ 一時停止"
    : (player.idx >= player.phrases.length ? "▶ もう一度" : "▶ 再開");
}

function playerPlay() {
  speechSynthesis.cancel();
  if (player.idx >= player.phrases.length) player.idx = 0;
  player.playing = true;
  const gen = ++player.gen;
  const next = () => {
    if (gen !== player.gen || !player.playing) return;
    if (player.idx >= player.phrases.length) { player.playing = false; playerRender(); return; }
    playerRender();
    const u = makeUtter(player.phrases[player.idx]);
    u.onend = () => { if (gen === player.gen && player.playing) { player.idx++; next(); } };
    speechSynthesis.speak(u);
  };
  next();
}

function playerPlayOne(i) {
  player.playing = false; player.gen++; speechSynthesis.cancel();
  player.idx = i; playerRender();
  speechSynthesis.speak(makeUtter(player.phrases[i]));
}

function playerPause() { player.playing = false; player.gen++; speechSynthesis.cancel(); playerRender(); }
function playerToggle() { player.playing ? playerPause() : playerPlay(); }
function playerRestart() { player.idx = 0; playerPlay(); }
function playerStop() { player.playing = false; player.gen++; }
function playerClose() { playerPause(); $("player").style.display = "none"; document.body.style.paddingBottom = ""; }
function playerSync() {
  if (!current.marked) return;
  player.playing = false; player.gen++; speechSynthesis.cancel();
  playerSetText(current.marked); playerRender();
}

function splitModeChanged() {
  saveSetting({ default_split_mode: $("splitMode").value });
  if (player.text) { playerPause(); playerSetText(player.text); playerRender(); }
}

// ============================================================ 区切り編集
function resetMainBreak() {
  mainBreakMode = false; current._breaks = null;
  explicitBreaks = /[/|｜／]/.test(current.marked || "");
  $("btnMainBreak")?.classList.remove("active");
  $("english").style.display = ""; $("pinyin").style.display = "";
  $("breakGrid").style.display = "none";
}

function toggleMainBreakEdit() {
  mainBreakMode = !mainBreakMode;
  $("btnMainBreak").classList.toggle("active", mainBreakMode);
  $("english").style.display = mainBreakMode ? "none" : "";
  $("pinyin").style.display = mainBreakMode ? "none" : "";
  $("breakGrid").style.display = mainBreakMode ? "" : "none";
  if (mainBreakMode) {
    if (!current._breaks) current._breaks = deriveMainBreaks();
    explicitBreaks = true;
    current.marked = buildMainMarked();
    renderMainBreakGrid();
    playerClose();
  } else { current.marked = buildMainMarked(); playerSync(); }
}

const mainTokens = () => (lang === "zh" ? Array.from(current.english || "")
  : (current.english || "").split(/\s+/).filter(Boolean));

function deriveMainBreaks() {
  const phrases = splitPhrases(current.marked || current.english);
  const br = new Set(); let idx = 0;
  for (let s = 0; s < phrases.length - 1; s++) {
    const toks = lang === "zh" ? Array.from(phrases[s].replace(/[/|｜／\s]/g, ""))
      : phrases[s].split(/\s+/).filter(Boolean);
    idx += toks.length; br.add(idx - 1);
  }
  return br;
}

function buildMainMarked() {
  let out = "";
  mainTokens().forEach((tk, i) => {
    out += tk + (lang === "zh" ? "" : " ");
    if (current._breaks?.has(i)) out += "/ ";
  });
  return out.replace(/\s+/g, " ").trim();
}

function renderMainBreakGrid() {
  const toks = mainTokens();
  const pairs = lang === "zh" ? pinyinPairs(current.english) : null;
  let h = '<div class="cgrid editbreaks">';
  toks.forEach((tk, i) => {
    if (i > 0) h += `<span class="cgap${current._breaks.has(i - 1) ? " brk" : ""}" data-pos="${i - 1}"></span>`;
    const py = pairs?.[i]?.[1] || "";
    const sz = lang === "zh" ? "" : ' style="font-size:16px;padding:0 3px"';
    h += `<span class="cchar"><span class="py">${esc(py)}</span><span class="hz"${sz}>${esc(tk)}</span></span>`;
  });
  $("breakGrid").innerHTML = h + "</div>";
  $("breakGrid").querySelectorAll(".cgap").forEach((g) =>
    g.onclick = () => toggleMainBreak(+g.dataset.pos));
}

function toggleMainBreak(pos) {
  if (current._breaks.has(pos)) current._breaks.delete(pos); else current._breaks.add(pos);
  current.marked = buildMainMarked();
  renderMainBreakGrid();
  playerSync();
}

// ============================================================ 作文
async function doTranslate() {
  const ja = $("ja").value.trim();
  if (!ja) return;
  if (ja.length > MAX_INPUT) { msg("msgTr", `入力が長すぎます（${MAX_INPUT}文字まで）`, false); return; }
  const btn = $("btnTr"); btn.disabled = true;
  msg("msgTr", "翻訳中…", true);
  try {
    const d = await api("/api/translate", { japanese: ja, lang });
    current = { japanese: ja, english: d.target, marked: d.target, keywords: [], pageId: null, _breaks: null };
    resetMainBreak();
    $("resultCard").style.display = "";
    $("english").textContent = d.target;
    $("pinyin").textContent = lang === "zh" ? pinyinOf(d.target) : "";
    $("kwBox").innerHTML = "<span class='sub'>キーワード抽出中…</span>";
    $("kwActions").style.display = "none";
    msg("msgTr", "", true); msg("msgSave", "", true);
    $("btnSave").disabled = false;
    playerLoad(d.target);
    api("/api/keywords", { target: d.target, japanese: ja, lang }).then((k) => {
      if (current.english !== d.target) return;
      current.keywords = k.keywords || [];
      renderKeywords();
    }).catch(() => { $("kwBox").innerHTML = ""; });
  } catch (e) { msg("msgTr", e.message, false); }
  btn.disabled = false;
}

function renderKeywords() {
  const box = $("kwBox"); box.innerHTML = "";
  $("kwActions").style.display = current.keywords.length ? "" : "none";
  current.keywords.forEach((k, i) => {
    const py = lang === "zh" ? pinyinOf(k.word) : "";
    const d = document.createElement("div");
    d.className = "kw";
    d.innerHTML = `<input type="checkbox" id="kw${i}" checked>
      <label for="kw${i}"><b>${esc(k.word)}</b> <span class="m">${py ? esc(py) + " / " : ""}${esc(k.meaning)}</span></label>
      <button class="small ghost" data-say="${esc(k.word)}">🔊</button>`;
    box.appendChild(d);
  });
  box.querySelectorAll("[data-say]").forEach((b) => b.onclick = () => speak(b.dataset.say));
}

function englishEdited(el) {
  current.marked = el.textContent.replace(/\s+/g, " ").trim();
  current.english = current.marked.replace(/\s*[/|｜／]+\s*/g, " ").replace(/\s+/g, " ").trim();
  current._breaks = null;
  explicitBreaks = /[/|｜／]/.test(current.marked);
  $("btnSave").disabled = false;
  playerSync();
  if (lang === "zh") $("pinyin").textContent = pinyinOf(current.english);
}

async function saveSentence() {
  const btn = $("btnSave"); btn.disabled = true;
  msg("msgSave", "保存中…", true);
  try {
    const payload = {
      japanese: current.japanese, english: current.english,
      marked: current.marked, lang,
      pinyin: lang === "zh" ? pinyinOf(current.english) : null,
    };
    if (current.pageId) payload.id = current.pageId;
    const d = await api("/api/sentences", payload);
    current.pageId = d.id;
    msg("msgSave", d.updated ? "上書き保存しました" : "保存しました", true);
    loadHistory();
  } catch (e) { msg("msgSave", e.message, false); btn.disabled = false; }
}

async function saveWords() {
  const picked = current.keywords.filter((_, i) => $("kw" + i).checked);
  if (!picked.length) return;
  if (!current.pageId) await saveSentence();
  msg("msgSave", "単語を登録中…", true);
  try {
    for (const k of picked) {
      await api("/api/words", {
        word: k.word, meaning: k.meaning, example: current.english,
        source_id: current.pageId, lang,
        pinyin: lang === "zh" ? pinyinOf(k.word) : null,
      });
    }
    msg("msgSave", `${picked.length}語を登録しました`, true);
    loadHistory();
  } catch (e) { msg("msgSave", e.message, false); }
}

// ============================================================ 履歴
async function loadHistory() {
  try {
    [allS, allW] = await Promise.all([api(`/api/sentences?lang=${lang}`), api(`/api/words?lang=${lang}`)]);
    sentCache = {};
    allS.forEach((s) => sentCache[s.id] = s);
    renderHistory();
  } catch (e) { $("history").textContent = e.message; }
}

function setTab(t) {
  histTab = t;
  ["date", "sent", "word"].forEach((x) => $("tab_" + x).classList.toggle("active", x === t));
  renderHistory();
}

function sentTable(list, withDate) {
  if (!list.length) return "";
  let h = `<table class="htable"><tr>${withDate ? "<th>日付</th>" : ""}<th>${L().sentCol}</th><th>実施</th><th>fail</th><th>操作</th></tr>`;
  list.forEach((s) => {
    const fails = FAIL_LABELS.map((l) => `<button class="small ghost" data-fail="${s.id}" data-label="${l}">${l}</button>`).join("");
    h += `<tr>${withDate ? `<td class="sub">${s.created}</td>` : ""}
      <td>${esc(s.english)}${s.pinyin ? `<div class="sub">${esc(s.pinyin)}</div>` : ""}<div class="sub">${esc(s.japanese)}</div></td>
      <td class="sub pr">${s.practice_count ? s.practice_count + "回<br>" + s.last_practiced : "未"}</td>
      <td><span class="badge failc">${s.fail_count}</span><div>${fails}</div></td>
      <td style="white-space:nowrap"><button class="icon" data-study="${s.id}">🔊</button>
      <button class="icon" data-del="${s.id}">🗑</button></td></tr>`;
  });
  return h + "</table>";
}

function wordTable(list, withDate) {
  if (!list.length) return "";
  let h = `<table class="htable"><tr>${withDate ? "<th>日付</th>" : ""}<th>単語</th><th>意味</th><th>操作</th></tr>`;
  list.forEach((w) => {
    h += `<tr>${withDate ? `<td class="sub">${w.created}</td>` : ""}
      <td><b>${esc(w.word)}</b>${w.pinyin ? ` <span class="sub">${esc(w.pinyin)}</span>` : ""}<div class="sub">${esc(w.example)}</div></td>
      <td>${esc(w.meaning)}</td>
      <td style="white-space:nowrap"><button class="icon" data-say="${esc(w.word)}">🔊</button>
      <button class="icon" data-delw="${w.id}">🗑</button></td></tr>`;
  });
  return h + "</table>";
}

function renderHistory() {
  const q = ($("hFilter").value || "").toLowerCase();
  const fs = allS.filter((s) => !q || (s.english + " " + s.japanese).toLowerCase().includes(q));
  const fw = allW.filter((w) => !q || (w.word + " " + w.meaning + " " + w.example).toLowerCase().includes(q));
  let h = "";
  if (histTab === "sent") h = sentTable(fs, true) || "該当なし";
  else if (histTab === "word") h = wordTable(fw, true) || "該当なし";
  else {
    const dates = [...new Set([...fs.map((s) => s.created), ...fw.map((w) => w.created)])].sort().reverse();
    dates.forEach((d) => {
      const ds = fs.filter((s) => s.created === d), dw = fw.filter((w) => w.created === d);
      h += `<div class="dateh">${d}</div>`;
      if (ds.length) h += `<div class="seclabel">${L().unit} ${ds.length}件</div>` + sentTable(ds, false);
      if (dw.length) h += `<div class="seclabel">単語 ${dw.length}語</div>` + wordTable(dw, false);
    });
    h = h || "該当なし";
  }
  const box = $("history");
  box.innerHTML = h;
  box.querySelectorAll("[data-study]").forEach((b) => b.onclick = () => study(b.dataset.study));
  box.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => delSentence(b.dataset.del));
  box.querySelectorAll("[data-delw]").forEach((b) => b.onclick = () => delWord(b.dataset.delw));
  box.querySelectorAll("[data-say]").forEach((b) => b.onclick = () => speak(b.dataset.say));
  box.querySelectorAll("[data-fail]").forEach((b) =>
    b.onclick = () => recFail(b, b.dataset.fail, b.dataset.label));
}

async function study(id) {
  const s = sentCache[id]; if (!s) return;
  go("/"); setSub("compose");
  $("ja").value = s.japanese;
  current = { japanese: s.japanese, english: s.english, marked: s.marked || s.english,
              keywords: [], pageId: id, _breaks: null };
  resetMainBreak();
  $("resultCard").style.display = "";
  $("english").textContent = current.marked;
  $("pinyin").textContent = s.pinyin || (lang === "zh" ? pinyinOf(s.english) : "");
  $("btnSave").disabled = true;
  msg("msgSave", L().restudy, true);
  $("kwBox").innerHTML = "<span class='sub'>キーワード抽出中…</span>";
  $("kwActions").style.display = "none";
  window.scrollTo({ top: 0, behavior: "smooth" });
  playerLoad(current.marked);
  api("/api/practice", { id }).then(loadHistory).catch(() => {});
  api("/api/keywords", { target: s.english, japanese: s.japanese, lang })
    .then((k) => { current.keywords = k.keywords || []; renderKeywords(); })
    .catch(() => { $("kwBox").innerHTML = ""; });
}

async function delSentence(id) {
  if (!confirm(L().delConfirm)) return;
  try { await api("/api/delete", { id }); loadHistory(); } catch (e) { alert(e.message); }
}

async function delWord(id) {
  if (!confirm("この単語を削除しますか？")) return;
  try { await api("/api/words/delete", { id }); loadHistory(); } catch (e) { alert(e.message); }
}

async function recFail(btn, id, label) {
  btn.disabled = true;
  try {
    const d = await api("/api/fail", { id, label });
    const c = btn.closest("tr").querySelector(".failc");
    if (c) c.textContent = d.fail_count;
  } catch (e) { alert(e.message); }
  btn.disabled = false;
}

// ============================================================ 設定・言語
async function setLang(l) {
  lang = LABELS[l] ? l : "en";
  localStorage.setItem("targetLang", lang);
  $("lang_en").classList.toggle("active", lang === "en");
  $("lang_zh").classList.toggle("active", lang === "zh");
  $("btnTr").textContent = L().toBtn;
  $("transHead").textContent = L().transHead;
  $("tab_sent").textContent = L().sentTab;
  $("resultCard").style.display = "none";
  resetMainBreak(); playerClose();
  saveSetting({ default_lang: lang });
  loadHistory();
}

function setSub(s) {
  sub = s;
  $("subCompose").style.display = s === "compose" ? "" : "none";
  $("subHistory").style.display = s === "history" ? "" : "none";
  $("sub_compose").classList.toggle("active", s === "compose");
  $("sub_history").classList.toggle("active", s === "history");
  if (s === "history") loadHistory();
}

let settingTimer = null;
function saveSetting(patch) {   // DBが正、localStorageはキャッシュ（spec §7.5）
  if (!profile) return;
  Object.assign(profile, patch);
  clearTimeout(settingTimer);
  settingTimer = setTimeout(() => api("/api/profile", patch).catch(() => {}), 600);
}

async function loadProfile() {
  const p = await api("/api/profile");
  profile = p.me || {};
  lang = profile.default_lang || localStorage.getItem("targetLang") || "en";
  $("rate").value = profile.default_rate ?? 0.9;
  $("rateVal").textContent = String(profile.default_rate ?? 0.9);
  $("splitMode").value = profile.default_split_mode || "fine";
  $("who").textContent = profile.display_name || "";
  // 設定画面
  $("setName").value = profile.display_name || "";
  $("setLang").value = lang;
  $("setRate").value = profile.default_rate ?? 0.9;
  $("setSplit").value = profile.default_split_mode || "fine";
  $("family").innerHTML = p.family.length
    ? p.family.map((f) => `<div class="sub">${esc(f.name || "(名前未設定)")} — 最終利用 ${f.last || "なし"}</div>`).join("")
    : "<div class='sub'>他のメンバーはいません</div>";
}

// ============================================================ エクスポート
function exportMarkdown() {
  const lines = [`# 学習データ（${lang === "zh" ? "中国語" : "英語"}）`, ""];
  allS.forEach((s) => {
    lines.push(`## ${s.english}`);
    if (s.pinyin) lines.push(`- 拼音: ${s.pinyin}`);
    lines.push(`- 日本語: ${s.japanese}`);
    lines.push(`- 登録日: ${s.created} / 実施: ${s.practice_count}回 / fail: ${s.fail_count}`, "");
  });
  lines.push("", "# 単語帳", "", "| 語 | 意味 | 例文 | 登録日 |", "|---|---|---|---|");
  allW.forEach((w) => lines.push(`| **${w.word}**${w.pinyin ? ` (${w.pinyin})` : ""} | ${w.meaning} | ${w.example} | ${w.created} |`));
  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `learning-${lang}-${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ============================================================ 発音評価
const scoreColor = (s) => (s >= 80 ? "var(--ok)" : s >= 60 ? "#e0a100" : "var(--ng)");

const assessUI = {
  recording(on) {
    const b = $("btnRec");
    b.textContent = on ? "⏹ 停止 0s" : "🎙 録音";
    b.classList.toggle("recording", on);
    if (on) { $("assessBox").style.display = "none"; }
  },
  tick(sec) { $("btnRec").textContent = `⏹ 停止 ${sec}s`; },
  playbackReady(on) {
    $("btnPlayRec").style.display = on ? "" : "none";
    $("btnPlayModel").style.display = on ? "" : "none";
  },
  pending() { const b = $("assessBox"); b.style.display = ""; b.innerHTML = "<span class='sub'>発音を判定中…</span>"; },
  showError(m) { const b = $("assessBox"); b.style.display = ""; b.innerHTML = `<span class="msg ng">${esc(m)}</span>`; },
  clearResult() { const b = $("assessBox"); b.style.display = "none"; b.innerHTML = ""; },
  render(d) { renderAssess(d); },
};

function renderAssess(d) {
  const box = $("assessBox"); const sc = d.scores;
  const omitted = d.words.filter((w) => w.error === "Omission").length;
  let h = `<div style="font-size:13px;margin-bottom:4px">総合 <b style="color:${scoreColor(sc.pron)}">${sc.pron}</b>
    <span class="sub">｜発音 ${sc.accuracy}／なめらかさ ${sc.fluency}／読めた割合 ${sc.completeness}%${sc.prosody ? "／抑揚 " + sc.prosody : ""}</span></div>`;
  if (sc.completeness < 50 || sc.fluency === 0)
    h += `<div class="msg ng" style="margin:0 0 4px">⚠️ ${omitted}語が聞き取れませんでした</div>`;
  h += `<div style="display:flex;flex-wrap:wrap;gap:4px">`;
  d.words.forEach((w, i) => {
    const miss = w.error === "Omission";
    const bad = (w.error !== "None" && !miss) || (w.score < 60 && !miss);
    h += `<span class="aw" data-i="${i}" style="padding:3px 7px;border-radius:8px;font-size:16px;cursor:pointer;
      background:${miss ? "#eef1f8" : bad ? "#fdecec" : "#eaf7ef"};color:${miss ? "var(--muted)" : scoreColor(w.score)}">${esc(w.word)}</span>`;
  });
  h += "</div>";
  const wrong = d.words.filter((w) => w.error !== "Omission" && (w.error !== "None" || w.score < 60));
  h += wrong.length
    ? `<div class="sub" style="margin-top:4px">直したい: ${wrong.map((w) => esc(w.word) + (w.worst ? `（${esc(w.worst.name)}）` : "")).join("、")}</div>`
    : (sc.completeness >= 50 ? `<div class="sub" style="margin-top:4px">よくできました！</div>` : "");
  box.style.display = ""; box.innerHTML = h;
  box.querySelectorAll(".aw").forEach((el) => {
    el.oncontextmenu = (ev) => { ev.preventDefault(); showWordDetail(+el.dataset.i); return false; };
    let t = null;
    el.addEventListener("touchstart", () => { t = setTimeout(() => { t = null; showWordDetail(+el.dataset.i); }, 450); }, { passive: true });
    const cancel = () => { if (t) { clearTimeout(t); t = null; } };
    el.addEventListener("touchend", cancel); el.addEventListener("touchmove", cancel);
  });
}

function showWordDetail(i) {
  const w = assess.lastAssess?.words[i]; if (!w) return;
  let m = `「${w.word}」\n\n`;
  if (w.error === "Omission") m += "⬜ グレー＝この単語が聞き取れませんでした。";
  else {
    m += `発音スコア: ${w.score} 点\n`;
    m += w.score >= 80 ? "🟩 緑＝よくできています（80点以上）\n"
      : w.score >= 60 ? "🟨 黄＝おしい（60〜79点）\n" : "🟥 赤＝お手本と違って聞こえます（60点未満）\n";
    if (w.error === "Mispronunciation") m += "\n判定: 発音まちがい\n";
    if (w.kind_label) {
      m += `\nミスの種類: ${w.kind}（${w.kind_label}）\n`;
      if (w.kind_char) m += `間違えた字: ${w.kind_char}\n`;
      if (w.expected_py && w.heard) m += `正しい読み: ${w.expected_py} → 実際: ${w.heard}${w.heard_char ? `（${w.heard_char}に聞こえた）` : ""}\n`;
    }
    if (w.phoneme_scores?.length) {
      m += "\n音ごとの点数（正しい読み）:\n";
      w.phoneme_scores.forEach((p) => { m += `  ${p[0]} … ${p[1]}点\n`; });
    }
  }
  alert(m);
}

// ============================================================ 記録タブ
let recLang = "zh", recTab = "weak", recRows = [];

async function loadRecord() {
  $("rlang_en").classList.toggle("active", recLang === "en");
  $("rlang_zh").classList.toggle("active", recLang === "zh");
  $("rtab_weak").classList.toggle("active", recTab === "weak");
  $("rtab_hist").classList.toggle("active", recTab === "hist");
  const box = $("recordBody");
  try {
    recRows = await api(`/api/assessments?lang=${recLang}`);
    if (!recRows.length) { box.innerHTML = "まだ記録がありません（発音チェックをすると貯まります）"; return; }
    box.innerHTML = recTab === "weak" ? weakTable(assess.aggregateWeak(recRows)) : histTable(recRows);
    box.querySelectorAll("[data-say]").forEach((b) => b.onclick = () => speak(b.dataset.say));
  } catch (e) { box.textContent = e.message; }
}

function rubyHTML(word) {
  return Array.from(word).map((ch) => {
    const py = /[一-鿿]/.test(ch) ? pinyinOf(ch) : "";
    return py ? `<ruby>${esc(ch)}<rt>${esc(py)}</rt></ruby>` : esc(ch);
  }).join("");
}

function weakTable(list) {
  if (!list.length) return "直近30日でミスした語はありません";
  let h = `<table class="htable"><tr><th>語</th><th>ミスの種類</th><th>ミス(30日)</th><th>最終</th></tr>`;
  list.forEach((w) => {
    const label = recLang === "zh" ? rubyHTML(w.word) : esc(w.word);
    let kind = "-";
    if (w.kind) {
      const detail = w.expected_py && w.heard
        ? `<div class="sub">${w.kind_char ? esc(w.kind_char) + " " : ""}${esc(w.expected_py)} → ${esc(w.heard)}</div>` : "";
      kind = `<b>${esc(w.kind.code)}</b> ${esc(w.kind.label)}${detail}`;
    } else if (w.weakSound) kind = `<span class="sub">${esc(w.weakSound.name)} ${w.weakSound.score}点</span>`;
    h += `<tr><td style="font-size:20px;line-height:1.6">${label}
        <button class="icon" data-say="${esc(w.word)}">🔊</button></td>
      <td>${kind}</td>
      <td style="white-space:nowrap"><b style="color:${w.rate >= 50 ? "var(--ng)" : "inherit"}">${w.miss}</b><span class="sub">/${w.tries}</span></td>
      <td class="sub" style="white-space:nowrap">${(w.last || "").slice(5)}</td></tr>`;
  });
  return h + "</table>";
}

function histTable(rows) {
  let h = `<table class="htable"><tr><th>日時</th><th>文</th><th>総合</th></tr>`;
  rows.slice(0, 50).forEach((a) => {
    const ng = (a.words || []).filter((w) => (w.e && w.e !== "None" && w.e !== "Omission") || (w.s ?? 100) < 60).map((w) => w.w);
    h += `<tr><td class="sub" style="white-space:nowrap">${(a.created_at || "").slice(5, 16).replace("T", " ")}</td>
      <td>${esc((a.text || "").slice(0, 40))}${ng.length ? `<div class="sub" style="color:var(--ng)">${ng.map(esc).join("、")}</div>` : ""}</td>
      <td style="color:${scoreColor(a.scores?.pron ?? 0)};font-weight:700">${a.scores?.pron ?? "-"}</td></tr>`;
  });
  return h + "</table>";
}

async function clearRecords() {
  if (!confirm(`${recLang === "zh" ? "中国語" : "英語"}の発音記録をすべて削除しますか？`)) return;
  try { await api("/api/assessments/clear", { lang: recLang }); loadRecord(); } catch (e) { alert(e.message); }
}

// ============================================================ ルーティング
const ROUTES = ["/", "/history", "/record", "/settings", "/login"];

function go(path, push = true) {
  if (push) history.pushState({}, "", path);
  render(path);
}

function render(path) {
  const authed = !!window.__user;
  if (!authed && path !== "/login") return go("/login", true);
  if (authed && path === "/login") return go("/", true);
  $("viewLogin").style.display = path === "/login" ? "" : "none";
  $("viewMain").style.display = (path === "/" || path === "/history") ? "" : "none";
  $("viewRecord").style.display = path === "/record" ? "" : "none";
  $("viewSettings").style.display = path === "/settings" ? "" : "none";
  $("appHeader").style.display = path === "/login" ? "none" : "";
  if (path === "/history") setSub("history");
  else if (path === "/") setSub("compose");
  else if (path === "/record") { recLang = lang; loadRecord(); }
  window.scrollTo(0, 0);
}

// ============================================================ 起動
async function boot() {
  // イベント配線
  $("btnTr").onclick = doTranslate;
  $("lang_en").onclick = () => setLang("en");
  $("lang_zh").onclick = () => setLang("zh");
  $("sub_compose").onclick = () => go("/");
  $("sub_history").onclick = () => go("/history");
  $("english").oninput = (e) => englishEdited(e.target);
  $("btnSpeak").onclick = () => playerLoad(current.marked || current.english);
  $("btnMainBreak").onclick = toggleMainBreakEdit;
  $("btnSave").onclick = saveSentence;
  $("btnWords").onclick = saveWords;
  $("hFilter").oninput = renderHistory;
  ["date", "sent", "word"].forEach((t) => $("tab_" + t).onclick = () => setTab(t));
  $("btnPlay").onclick = playerToggle;
  $("btnRestart").onclick = playerRestart;
  $("btnCloseP").onclick = playerClose;
  $("rate").oninput = (e) => rateChanged(e.target.value);
  $("splitMode").onchange = splitModeChanged;
  document.querySelectorAll("[data-rate]").forEach((b) => b.onclick = () => setRate(+b.dataset.rate));
  $("navHistory").onclick = () => go("/history");
  $("navRecord").onclick = () => go("/record");
  $("navSettings").onclick = () => go("/settings");
  // 発音チェック
  $("btnRec").onclick = () => assess.toggleRecord(
    () => (player.text || "").replace(/[/|｜／]/g, "").trim(), lang, assessUI);
  $("btnPlayRec").onclick = assess.playMyRec;
  $("btnPlayModel").onclick = () => { const t = assess.modelText(); if (t) speak(t); };
  $("rlang_en").onclick = () => { recLang = "en"; loadRecord(); };
  $("rlang_zh").onclick = () => { recLang = "zh"; loadRecord(); };
  $("rtab_weak").onclick = () => { recTab = "weak"; loadRecord(); };
  $("rtab_hist").onclick = () => { recTab = "hist"; loadRecord(); };
  $("btnClearRec").onclick = clearRecords;
  $("navReload").onclick = () => location.reload();
  $("btnBackMain").onclick = () => go("/");
  $("btnExport").onclick = exportMarkdown;
  $("btnLogout").onclick = async () => { await signOut(); window.__user = null; go("/login"); };
  $("loginForm").onsubmit = async (e) => {
    e.preventDefault();
    msg("msgLogin", "ログイン中…", true);
    try {
      window.__user = await signIn($("email").value.trim(), $("password").value);
      await afterLogin();
      go("/");
    } catch (err) { msg("msgLogin", err.message, false); }
  };
  $("setName").onchange = (e) => saveSetting({ display_name: e.target.value.trim() });
  $("setLang").onchange = (e) => setLang(e.target.value);
  $("setRate").onchange = (e) => { $("rate").value = e.target.value; rateChanged(e.target.value); };
  $("setSplit").onchange = (e) => { $("splitMode").value = e.target.value; splitModeChanged(); };

  window.addEventListener("popstate", () => render(location.pathname));
  speechSynthesis.getVoices();

  const { data } = await sb.auth.getSession();
  window.__user = data.session?.user ?? null;
  if (window.__user) await afterLogin();
  render(location.pathname);
}

async function afterLogin() {
  await loadProfile();
  await setLang(lang);
}

boot();
