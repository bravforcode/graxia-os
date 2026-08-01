const EMBED_MODEL = "@cf/baai/bge-base-en-v1.5";

function unauthorized() {
  return Response.json({ error: "unauthorized" }, { status: 401 });
}

async function handleSave(request, env) {
  const { content, metadata } = await request.json();
  if (!content || typeof content !== "string") {
    return Response.json({ error: "content (string) required" }, { status: 400 });
  }

  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();

  const embedResp = await env.AI.run(EMBED_MODEL, { text: [content] });
  const vector = embedResp.data[0];

  await env.DB.prepare(
    "INSERT INTO memories (id, content, metadata, created_at) VALUES (?, ?, ?, ?)"
  ).bind(id, content, JSON.stringify(metadata || {}), createdAt).run();

  await env.VECTORIZE.insert([{ id, values: vector, metadata: { created_at: createdAt } }]);

  return Response.json({ id, created_at: createdAt });
}

async function handleSearch(request, env) {
  const { query, topK } = await request.json();
  if (!query || typeof query !== "string") {
    return Response.json({ error: "query (string) required" }, { status: 400 });
  }

  const embedResp = await env.AI.run(EMBED_MODEL, { text: [query] });
  const vector = embedResp.data[0];

  const matches = await env.VECTORIZE.query(vector, { topK: topK || 5 });

  const results = [];
  for (const m of matches.matches) {
    const row = await env.DB.prepare(
      "SELECT content, metadata, created_at FROM memories WHERE id = ?"
    ).bind(m.id).first();
    if (row) {
      results.push({
        id: m.id,
        score: m.score,
        content: row.content,
        metadata: JSON.parse(row.metadata || "{}"),
        created_at: row.created_at,
      });
    }
  }
  return Response.json({ results });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const auth = request.headers.get("Authorization") || "";

    if (url.pathname === "/health" && request.method === "GET") {
      return Response.json({ status: "ok" });
    }

    if (auth !== `Bearer ${env.SECOND_BRAIN_API_KEY}`) {
      return unauthorized();
    }

    try {
      if (url.pathname === "/save" && request.method === "POST") {
        return await handleSave(request, env);
      }
      if (url.pathname === "/search" && request.method === "POST") {
        return await handleSearch(request, env);
      }
    } catch (err) {
      return Response.json({ error: String(err) }, { status: 500 });
    }

    return Response.json({ error: "not found" }, { status: 404 });
  },
};
