import http from "node:http";
import { WebSocket, WebSocketServer } from "ws";

const mothPort = Number(process.env.MOTH_PORT ?? 8287);

type StreamState = {
  mime: string | null;
  publishers: Set<import("ws").WebSocket>;
  subscribers: Set<import("ws").WebSocket>;
};

const streams = new Map<string, StreamState>();

const getKey = (url: URL) => {
  const channel = url.searchParams.get("channel");
  if (!channel) {
    throw new Error("missing required query param: channel");
  }

  const name = url.searchParams.get("name") ?? "";
  const source = url.searchParams.get("source") ?? "base";
  const track = url.searchParams.get("track") ?? "data";
  return `${channel}:${name}:${source}:${track}`;
};

const ensureStream = (key: string) => {
  const existing = streams.get(key);
  if (existing) {
    return existing;
  }

  const created: StreamState = {
    mime: null,
    publishers: new Set(),
    subscribers: new Set(),
  };
  streams.set(key, created);
  return created;
};

const maybeCleanupStream = (key: string) => {
  const stream = streams.get(key);
  if (!stream) {
    return;
  }

  if (stream.publishers.size === 0 && stream.subscribers.size === 0) {
    streams.delete(key);
  }
};

const server = http.createServer((_request, response) => {
  response.writeHead(200, { "content-type": "application/json" });
  response.end(
    JSON.stringify({
      service: "local-moth-bridge",
      streams: streams.size,
      endpoints: ["/pang/ws/pub", "/pang/ws/sub"],
    }),
  );
});

const publisherWss = new WebSocketServer({ noServer: true });
const subscriberWss = new WebSocketServer({ noServer: true });

publisherWss.on("connection", (socket, request) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
  const key = getKey(url);
  const stream = ensureStream(key);
  stream.publishers.add(socket);

  console.log("[moth] publisher connected", key);

  socket.on("message", (data, isBinary) => {
    if (!isBinary) {
      stream.mime = data.toString();
      for (const subscriber of stream.subscribers) {
        if (subscriber.readyState === WebSocket.OPEN) {
          subscriber.send(stream.mime);
        }
      }
      return;
    }

    if (!stream.mime) {
      socket.close(1008, "MIME required before binary payload");
      return;
    }

    for (const subscriber of stream.subscribers) {
      if (subscriber.readyState === WebSocket.OPEN) {
        subscriber.send(data, { binary: true });
      }
    }
  });

  socket.on("close", () => {
    stream.publishers.delete(socket);
    maybeCleanupStream(key);
    console.log("[moth] publisher disconnected", key);
  });
});

subscriberWss.on("connection", (socket, request) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
  const key = getKey(url);
  const stream = ensureStream(key);
  stream.subscribers.add(socket);

  console.log("[moth] subscriber connected", key);

  if (stream.mime) {
    socket.send(stream.mime);
  }

  socket.on("close", () => {
    stream.subscribers.delete(socket);
    maybeCleanupStream(key);
    console.log("[moth] subscriber disconnected", key);
  });
});

server.on("upgrade", (request, socket, head) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);

  const handleError = (message: string) => {
    socket.write(`HTTP/1.1 400 Bad Request\r\n\r\n${message}`);
    socket.destroy();
  };

  try {
    getKey(url);
  } catch (error) {
    handleError(error instanceof Error ? error.message : "invalid query");
    return;
  }

  if (url.pathname === "/pang/ws/pub") {
    publisherWss.handleUpgrade(request, socket, head, (ws) => {
      publisherWss.emit("connection", ws, request);
    });
    return;
  }

  if (url.pathname === "/pang/ws/sub") {
    subscriberWss.handleUpgrade(request, socket, head, (ws) => {
      subscriberWss.emit("connection", ws, request);
    });
    return;
  }

  handleError("unsupported endpoint");
});

server.listen(mothPort, "0.0.0.0", () => {
  console.log(`[moth] listening on ws://127.0.0.1:${mothPort}`);
});
