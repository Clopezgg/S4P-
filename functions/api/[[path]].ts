interface Env {
  API_ORIGIN: string
}

export const onRequest: PagesFunction<Env> = async ({ request, env }) => {
  if (!env.API_ORIGIN) {
    return new Response(JSON.stringify({ error: { code: "BACKEND_NOT_CONFIGURED", message: "Backend unavailable" } }), {
      status: 503,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    })
  }

  let backend: URL
  try {
    backend = new URL(env.API_ORIGIN)
    if (backend.protocol !== "https:" || backend.username || backend.password || backend.search || backend.hash || backend.pathname !== "/") {
      throw new Error("Invalid backend origin")
    }
  } catch {
    return new Response("Backend configuration invalid", { status: 503, headers: { "cache-control": "no-store" } })
  }

  const incoming = new URL(request.url)
  const target = new URL(incoming.pathname + incoming.search, backend.origin)
  const headers = new Headers(request.headers)
  headers.delete("host")
  headers.delete("cf-connecting-ip")
  headers.delete("x-forwarded-for")
  headers.delete("x-forwarded-host")
  headers.delete("x-forwarded-proto")
  headers.set("x-forwarded-host", incoming.host)
  headers.set("x-forwarded-proto", "https")

  const upstream = await fetch(new Request(target.toString(), {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    redirect: "manual",
  }))

  const response = new Response(upstream.body, upstream)
  response.headers.set("cache-control", "no-store")
  return response
}
