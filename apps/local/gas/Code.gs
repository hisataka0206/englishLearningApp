/**
 * English Learning App — Google Apps Script バックエンド（探検ラリーと同方式）
 *
 * 指定のDriveフォルダにデータファイル(JSON/Markdown)を保存・取得する。
 * サーバー(server.py)から HTTP POST で呼び出される。
 *
 * デプロイ方法（探検ラリーのときと同じ）:
 *   1. script.google.com で新規プロジェクトを作成
 *   2. このコードを貼り付ける（SHARED_SECRETは自由な文字列に変更可）
 *   3. 「デプロイ」→「新しいデプロイ」→ 種類: ウェブアプリ
 *   4. 実行ユーザー: 自分 / アクセスできるユーザー: 全員
 *   5. デプロイURLとSHARED_SECRETを config.json の storage.drive_gas に設定
 */

// ===== 設定 =====
// 保存先 Drive フォルダ（https://drive.google.com/drive/folders/<ID>）
const ROOT_FOLDER_ID = '1Ti5_KbmpML5NAfUxUW6OM3OZcSG6dQjb';
const SHARED_SECRET = 'english-learning-app-2026'; // config.json と合わせること

// ===== エントリポイント =====
function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.secret !== SHARED_SECRET) {
      return out_({ ok: false, error: 'invalid secret' });
    }
    const folder = DriveApp.getFolderById(ROOT_FOLDER_ID);
    if (body.action === 'putFile') {
      return out_(putFile_(folder, body.name, body.content, body.mime));
    }
    if (body.action === 'getFile') {
      return out_(getFile_(folder, body.name));
    }
    return out_({ ok: false, error: 'unknown action: ' + body.action });
  } catch (err) {
    return out_({ ok: false, error: String(err) });
  }
}

function putFile_(folder, name, content, mime) {
  const files = folder.getFilesByName(name);
  if (files.hasNext()) {
    const f = files.next();
    f.setContent(content);
    // 同名の重複ファイルがあればゴミ箱へ（過去の競合で生じた二重ファイルを整理）
    while (files.hasNext()) files.next().setTrashed(true);
    return { ok: true, id: f.getId(), updated: true };
  }
  const f = folder.createFile(name, content, mime || 'text/plain');
  return { ok: true, id: f.getId(), updated: false };
}

function getFile_(folder, name) {
  const files = folder.getFilesByName(name);
  if (!files.hasNext()) return { ok: true, content: null };
  const f = files.next();
  return { ok: true, content: f.getBlob().getDataAsString('UTF-8') };
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
