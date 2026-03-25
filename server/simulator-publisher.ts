import { WebSocket } from "ws";
import { createSimulator } from "../src/lib/simulator";
import {
  AIS_STREAM_MIME,
  DEFAULT_MOTH_PUB_URL,
  serializeFrameBatch,
} from "../src/lib/aisStream";

const publishUrl = process.env.MOTH_PUB_URL ?? DEFAULT_MOTH_PUB_URL;
const simulator = createSimulator();

let currentSocket: WebSocket | null = null;
let publishTimer: NodeJS.Timeout | null = null;
let mimeTimer: NodeJS.Timeout | null = null;

const stopTimers = () => {
  if (publishTimer) {
    clearInterval(publishTimer);
    publishTimer = null;
  }

  if (mimeTimer) {
    clearInterval(mimeTimer);
    mimeTimer = null;
  }
};

const sendSnapshot = (socket: WebSocket, mode: "seed" | "next") => {
  const snapshot = mode === "seed" ? simulator.seed() : simulator.next();
  socket.send(AIS_STREAM_MIME);
  socket.send(serializeFrameBatch(snapshot.lastFrames));
};

const connect = () => {
  console.log("[simulator] connecting to", publishUrl);
  const socket = new WebSocket(publishUrl);
  currentSocket = socket;

  socket.on("open", () => {
    console.log("[simulator] publisher connected");
    sendSnapshot(socket, "seed");

    publishTimer = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        sendSnapshot(socket, "next");
      }
    }, 1000);

    // Repeat MIME periodically for robustness, following the legacy Moth guidance.
    mimeTimer = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(AIS_STREAM_MIME);
      }
    }, 5000);
  });

  socket.on("close", (code, reason) => {
    console.error("[simulator] publisher closed", code, reason.toString());
    stopTimers();
    if (currentSocket === socket) {
      currentSocket = null;
    }
    setTimeout(connect, 1500);
  });

  socket.on("error", (error) => {
    console.error("[simulator] publisher error", error);
  });
};

process.on("SIGINT", () => {
  stopTimers();
  currentSocket?.close();
  process.exit(0);
});

connect();
