import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function upstreamBaseUrl(): string {
  return (
    process.env.INTERNAL_API_URL?.trim()
    || process.env.NEXT_PUBLIC_API_URL?.trim()
    || "http://localhost:8000"
  ).replace(/\/+$/, "");
}

async function proxy(
  request: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const requestUrl = new URL(request.url);
  const upstreamUrl = `${upstreamBaseUrl()}/${params.path.join("/")}${requestUrl.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");

  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.arrayBuffer();
  }

  let response: Response;
  try {
    response = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "upstream request failed";
    return Response.json({ detail }, { status: 502 });
  }

  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete("content-length");
  return new Response(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
