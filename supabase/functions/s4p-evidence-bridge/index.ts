import { createClient } from "npm:@supabase/supabase-js@2.78.0";

// Private service-to-service bridge. The signing key lives ONLY on Render;
// this public Ed25519 verification key cannot authorize operations on its own.
const PUBLIC_KEY_B64 = "vESU6HRr1NmdsxuWoWsyryu0J51XXXKNMrEoU6eskDY=";
const BUCKET = "s4p-evidence-private";
const MAX_BYTES = 25 * 1024 * 1024;
const ALLOWED = new Set(["application/pdf","image/jpeg","image/png","image/webp","image/heic","image/heif"]);
const ENCODER = new TextEncoder();
const json = (obj: unknown, status = 200) => Response.json(obj, {
  status, headers: {"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"},
});
function hex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)].map(v=>v.toString(16).padStart(2,"0")).join("");
}
function validKey(key: string): boolean {
  const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
  const businessKey = new RegExp("^"+uuid+"/"+uuid+"-[^/\\x00-\\x1f]{1,255}$","i");
  return businessKey.test(key) || /^__s4p_storage_smoke__\/[0-9a-f]{32}\.pdf$/.test(key);
}
const publicBytes = Uint8Array.from(atob(PUBLIC_KEY_B64), c=>c.charCodeAt(0));
const verificationKey = await crypto.subtle.importKey(
  "raw", publicBytes, {name:"Ed25519"}, false, ["verify"]);
Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({error:"unauthorized"}, 401);
  const tsRaw = req.headers.get("x-s4p-ts") || "";
  const nonce = req.headers.get("x-s4p-nonce") || "";
  const signature = req.headers.get("x-s4p-signature") || "";
  const op = req.headers.get("x-s4p-op") || "";
  const key = req.headers.get("x-s4p-key") || "";
  const mime = req.headers.get("x-s4p-mime") || "";
  const seconds = Number(tsRaw);
  if (!/^\d{10}$/.test(tsRaw) || Math.abs(Date.now()/1000-seconds)>90 ||
      !/^[0-9a-f]{32}$/.test(nonce) ||
      !/^[A-Za-z0-9_-]{80,100}$/.test(signature) ||
      !["health","exists","upload","download","remove"].includes(op) ||
      (op!=="health" && !validKey(key)) ||
      (op==="health" && key!=="") ||
      (op==="upload" && !ALLOWED.has(mime)) ||
      (op!=="upload" && mime!=="")) {
    return json({error:"unauthorized"}, 401);
  }
  const length = Number(req.headers.get("content-length") || "0");
  if (!Number.isFinite(length) || length<0 || length>MAX_BYTES) return json({error:"size"},413);
  let data: Uint8Array;
  try { data = new Uint8Array(await req.arrayBuffer()); }
  catch { return json({error:"body"},400); }
  if (data.byteLength>MAX_BYTES || (op!=="upload" && data.byteLength!==0)) {
    return json({error:"body"},413);
  }
  const digest = hex(await crypto.subtle.digest("SHA-256",data));
  const canonical = [tsRaw,nonce,op,key,mime,digest].join("\n");
  let sig: Uint8Array;
  try { sig = Uint8Array.from(atob(signature.replace(/-/g,"+").replace(/_/g,"/")), c=>c.charCodeAt(0)); }
  catch { return json({error:"unauthorized"},401); }
  const verified = await crypto.subtle.verify("Ed25519", verificationKey, sig, ENCODER.encode(canonical));
  if (!verified) return json({error:"unauthorized"},401);
  const url = Deno.env.get("SUPABASE_URL") || "";
  const configuredKeys = Deno.env.get("SUPABASE_SECRET_KEYS");
  let adminKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (configuredKeys) {
    try { adminKey = JSON.parse(configuredKeys).default || adminKey; } catch { /* fallback legacy */ }
  }
  if (!url.startsWith("https://") || !adminKey) return json({error:"unavailable"},503);
  const supabase = createClient(url,adminKey,{auth:{persistSession:false,autoRefreshToken:false}});
  const {data: bucket,error: bucketError} = await supabase.storage.getBucket(BUCKET);
  if (bucketError || !bucket || bucket.public) return json({error:"bucket unavailable"},503);
  const storage = supabase.storage.from(BUCKET);
  try {
    if (op==="health") return json({ok:true,private:true});
    if (op==="exists") {
      const {data: found,error} = await storage.exists(key);
      if (error) return json({error:"storage"},503);
      return json({exists:found});
    }
    if (op==="upload") {
      const {error} = await storage.upload(key,data,{contentType:mime,upsert:false,cacheControl:"0"});
      if (error) return json({error:/exist/i.test(error.message)? "exists":"storage"},/exist/i.test(error.message)?409:503);
      return json({ok:true},201);
    }
    if (op==="download") {
      const {data: blob,error} = await storage.download(key);
      if (error || !blob) return json({error:"not found"},404);
      return new Response(blob,{status:200,headers:{"Content-Type":"application/octet-stream","Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"}});
    }
    if (op==="remove") {
      const {error} = await storage.remove([key]);
      if (error) return json({error:"storage"},503);
      return json({ok:true});
    }
  } catch { return json({error:"storage"},503); }
  return json({error:"operation"},400);
});