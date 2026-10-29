import { createClient } from "npm:@supabase/supabase-js@2.78.0";

// Private backup storage, accessible only via signed requests from FastAPI.
// The decryption secret stays exclusively on Render. This function only sees
// AES-256-GCM ciphertext, not database records or the backup encryption key.
const PUBLIC_KEY_B64 = "vESU6HRr1NmdsxuWoWsyryu0J51XXXKNMrEoU6eskDY=";
const BUCKET = "s4p-db-backups-private";
const MAX_BYTES = 4 * 1024 * 1024;
const MAX_MANIFEST = 64 * 1024;
const encoder = new TextEncoder();
const decoder = new TextDecoder();

const json = (value: unknown, status = 200) =>
  Response.json(value, {status, headers: {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}});

const validBackupKey = (key: string) =>
  /^db-backups\/20\d{6}\/[0-9a-f]{32}\/(?:part-\d{4}\.bin|manifest\.json)$/.test(key);

const keyBytes = Uint8Array.from(atob(PUBLIC_KEY_B64), c => c.charCodeAt(0));
const verifier = await crypto.subtle.importKey("raw", keyBytes, {name: "Ed25519"}, false, ["verify"]);

function toHex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)].map(n => n.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({error: "unauthorized"}, 401);
  const ts = req.headers.get("x-s4p-ts") ?? "";
  const nonce = req.headers.get("x-s4p-nonce") ?? "";
  const signature = req.headers.get("x-s4p-signature") ?? "";
  const op = req.headers.get("x-s4p-op") ?? "";
  const key = req.headers.get("x-s4p-key") ?? "";
  const mime = req.headers.get("x-s4p-mime") ?? "";
  if (
    !/^\d{10}$/.test(ts) ||
    Math.abs(Date.now() / 1000 - Number(ts)) > 90 ||
    !/^[a-f0-9]{32}$/.test(nonce) ||
    !/^[A-Za-z0-9_-]{80,100}$/.test(signature) ||
    !["health", "upload", "download", "status", "publish"].includes(op) ||
    ((op === "upload" || op === "download") && !validBackupKey(key)) ||
    (["health", "status", "publish"].includes(op) && key !== "") ||
    (op === "upload" && !["application/octet-stream", "application/json"].includes(mime)) ||
    (op === "publish" && mime !== "application/json") ||
    (["health", "status", "download"].includes(op) && mime !== "")
  ) return json({error: "unauthorized"}, 401);

  const declaredLength = Number(req.headers.get("content-length") || "0");
  if (!Number.isFinite(declaredLength) || declaredLength < 0 || declaredLength > MAX_BYTES) {
    return json({error: "payload too large"}, 413);
  }
  const data = new Uint8Array(await req.arrayBuffer());
  if (
    data.length > MAX_BYTES ||
    (["health", "download", "status"].includes(op) && data.length !== 0) ||
    (["upload", "publish"].includes(op) && data.length === 0) ||
    ((op === "publish" || key.endsWith("/manifest.json")) && data.length > MAX_MANIFEST)
  ) return json({error: "invalid payload"}, 413);

  const digest = toHex(await crypto.subtle.digest("SHA-256", data));
  const canonical = [ts, nonce, op, key, mime, digest].join("\n");
  let signatureBytes: Uint8Array;
  try {
    const padded = signature.replace(/-/g, "+").replace(/_/g, "/").padEnd(88, "=");
    signatureBytes = Uint8Array.from(atob(padded), c => c.charCodeAt(0));
  } catch { return json({error: "unauthorized"}, 401); }
  if (!(await crypto.subtle.verify("Ed25519", verifier, signatureBytes, encoder.encode(canonical)))) {
    return json({error: "unauthorized"}, 401);
  }

  const url = Deno.env.get("SUPABASE_URL") || "";
  const keyMap = Deno.env.get("SUPABASE_SECRET_KEYS");
  let adminKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (keyMap) {
    try { adminKey = JSON.parse(keyMap).default || adminKey; } catch { /* legacy fallback */ }
  }
  if (!url.startsWith("https://") || !adminKey) return json({error: "storage unavailable"}, 503);

  const supabase = createClient(url, adminKey, {auth: {persistSession: false, autoRefreshToken: false}});
  const {data: bucket, error: bucketError} = await supabase.storage.getBucket(BUCKET);
  if (bucketError || !bucket || bucket.public) return json({error: "private bucket unavailable"}, 503);
  const storage = supabase.storage.from(BUCKET);

  try {
    if (op === "health") return json({ok: true, private: true});
    if (op === "status") {
      const {data: blob, error} = await storage.download("db-backups/latest.json");
      if (error || !blob) return json({available: false});
      const value = JSON.parse(await blob.text());
      if (!value || typeof value.manifestKey !== "string" || !validBackupKey(value.manifestKey)) {
        return json({error: "invalid backup marker"}, 503);
      }
      return json({available: true, ...value});
    }
    if (op === "upload") {
      const {error} = await storage.upload(key, data, {upsert: false, contentType: mime, cacheControl: "0"});
      if (error) {
        const conflict = /exist|already/i.test(error.message);
        return json({error: conflict ? "conflict" : "storage"}, conflict ? 409 : 503);
      }
      return json({ok: true}, 201);
    }
    if (op === "download") {
      const {data: blob, error} = await storage.download(key);
      if (error || !blob) return json({error: "not found"}, 404);
      return new Response(blob, {status: 200, headers: {
        "Content-Type": "application/octet-stream", "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      }});
    }
    if (op === "publish") {
      let value: {manifestKey?: string, createdAt?: string};
      try { value = JSON.parse(decoder.decode(data)); }
      catch { return json({error: "invalid manifest pointer"}, 422); }
      if (
        typeof value.manifestKey !== "string" ||
        !/^db-backups\/20\d{6}\/[0-9a-f]{32}\/manifest\.json$/.test(value.manifestKey) ||
        typeof value.createdAt !== "string" ||
        !/^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value.createdAt)
      ) return json({error: "invalid backup pointer"}, 422);
      const {data: exists, error: existError} = await storage.exists(value.manifestKey);
      if (existError || exists !== true) return json({error: "manifest missing"}, 409);
      const {error} = await storage.upload("db-backups/latest.json", data, {
        contentType: "application/json", upsert: true, cacheControl: "0",
      });
      if (error) return json({error: "storage"}, 503);
      return json({ok: true});
    }
  } catch { return json({error: "storage"}, 503); }
  return json({error: "operation"}, 400);
});
