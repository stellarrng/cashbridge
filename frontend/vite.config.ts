import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import net from "node:net";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const root = (file: string) => fileURLToPath(new URL(file, import.meta.url));
const repoRoot = root("..");

/** Port the dev API listens on. Not 8000, so it never collides with a server you started with `make run`. */
const API_PORT = Number(process.env.CASHBRIDGE_API_PORT ?? 8100);

const isListening = (port: number): Promise<boolean> =>
  new Promise((resolve) => {
    const socket = net.connect({ port, host: "127.0.0.1" });
    socket.once("connect", () => (socket.destroy(), resolve(true)));
    socket.once("error", () => resolve(false));
  });

async function waitFor(port: number, ms: number): Promise<boolean> {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    if (await isListening(port)) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

/** `npm run dev` starts the Python API too, so one command runs the whole app. It stops with the dev server. */
function backend(): Plugin {
  let child: ChildProcess | undefined;
  const stop = () => child?.kill();
  return {
    name: "cashbridge-backend",
    apply: "serve",
    async configureServer(server) {
      const log = server.config.logger;
      if (await isListening(API_PORT)) {
        log.info(`API already running on :${API_PORT}, using it.`);
        return;
      }
      const python = [".venv/bin/python", ".venv/Scripts/python.exe"].map((p) => `${repoRoot}/${p}`).find(existsSync);
      if (!python) log.warn("No .venv found at the repo root: using python3. Run `make install` first if the API fails to start.");
      child = spawn(python ?? "python3", ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(API_PORT)], {
        cwd: repoRoot,
        stdio: ["ignore", "inherit", "inherit"],
      });
      child.on("exit", (code) => code && log.error(`API process exited with code ${code}`));
      process.on("exit", stop);
      server.httpServer?.on("close", stop);
      if (await waitFor(API_PORT, 30000)) log.info(`API ready on :${API_PORT}`);
      else log.error(`API did not start on :${API_PORT} within 30 s`);
    },
  };
}

// Two HTML entry points keep the public URLs of the product: "/" (landing + sign-in) and "/app" (workspaces).
// The FastAPI static handler already serves app.html for "/app", so no server change is needed.
function appRoute(): Plugin {
  return {
    name: "cashbridge-app-route",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url && /^\/app(?:[?#]|$)/.test(req.url)) req.url = req.url.replace(/^\/app/, "/app.html");
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), appRoute(), backend()],
  resolve: { alias: { "@": root("./src") } },
  server: {
    port: 5173,
    proxy: { "/api": `http://127.0.0.1:${API_PORT}`, "/docs": `http://127.0.0.1:${API_PORT}`, "/openapi.json": `http://127.0.0.1:${API_PORT}` },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: { index: root("./index.html"), app: root("./app.html") },
      output: { manualChunks: { "react-vendor": ["react", "react-dom"] } },
    },
  },
});
