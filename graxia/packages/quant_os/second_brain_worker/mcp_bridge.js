#!/usr/bin/env node
// Minimal stdio MCP server bridging to the deployed second-brain-worker (Cloudflare
// Workers AI + Vectorize + D1). No external npm dependencies — uses Node's built-in
// readline and fetch only, since the previously configured "workers-ai-mcp" package
// does not exist on npm.

import readline from "readline";

const WORKER_URL = process.env.SECOND_BRAIN_WORKER_URL || "https://second-brain-worker.quantos-secondbrain.workers.dev";
const API_KEY = process.env.SECOND_BRAIN_API_KEY;

const rl = readline.createInterface({ input: process.stdin, terminal: false });

function send(msg) {
  process.stdout.write(JSON.stringify(msg) + "\n");
}

async function callWorker(path, body) {
  const res = await fetch(WORKER_URL + path, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      "Content-Type": "application/json",
      "User-Agent": "second-brain-mcp-bridge/1.0",
    },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

const TOOLS = [
  {
    name: "save_memory",
    description: "Save a piece of text to Second Brain long-term memory (Cloudflare D1 + Vectorize).",
    inputSchema: {
      type: "object",
      properties: {
        content: { type: "string", description: "The text content to remember." },
        metadata: { type: "object", description: "Optional metadata to attach." },
      },
      required: ["content"],
    },
  },
  {
    name: "search_memory",
    description: "Semantic search over Second Brain memory.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query." },
        topK: { type: "number", description: "Number of results to return (default 5)." },
      },
      required: ["query"],
    },
  },
];

rl.on("line", async (line) => {
  if (!line.trim()) return;
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }

  const { id, method, params } = msg;

  if (method === "initialize") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "second-brain-mcp-bridge", version: "1.0.0" },
      },
    });
    return;
  }

  if (method === "notifications/initialized") {
    return;
  }

  if (method === "tools/list") {
    send({ jsonrpc: "2.0", id, result: { tools: TOOLS } });
    return;
  }

  if (method === "tools/call") {
    const { name, arguments: args } = params || {};
    try {
      let result;
      if (name === "save_memory") {
        result = await callWorker("/save", { content: args.content, metadata: args.metadata });
      } else if (name === "search_memory") {
        result = await callWorker("/search", { query: args.query, topK: args.topK });
      } else {
        send({ jsonrpc: "2.0", id, error: { code: -32601, message: `Unknown tool: ${name}` } });
        return;
      }
      send({
        jsonrpc: "2.0",
        id,
        result: { content: [{ type: "text", text: JSON.stringify(result) }] },
      });
    } catch (err) {
      send({ jsonrpc: "2.0", id, error: { code: -32000, message: String(err) } });
    }
    return;
  }

  if (id !== undefined) {
    send({ jsonrpc: "2.0", id, error: { code: -32601, message: `Unknown method: ${method}` } });
  }
});
