import { app, BrowserWindow, ipcMain, safeStorage, shell } from "electron";
import path from "path";
import { fileURLToPath, pathToFileURL } from "url";
import { spawn, spawnSync } from "child_process";
import fs from "fs";
import crypto from "crypto";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const KEY_SLOTS = new Set(["anthropic", "openai", "google", "deepseek", "mistral", "groq", "xai", "openrouter", "venice"]);
const gotSingleInstanceLock = app.requestSingleInstanceLock();
// Only unpackaged builds are dev builds. An inherited NODE_ENV must never make an
// installed app load (and hand its API token to) whatever serves localhost:5173.
const isDev = !app.isPackaged;

let mainWindow = null;
let pythonProcess = null;
let backendPort = null;
let stoppingBackend = false;
let appQuitting = false;
let restartTimer = null;
const restartHistory = [];
const MAX_RESTARTS = 5;
const RESTART_WINDOW_MS = 5 * 60 * 1000;
const apiToken = crypto.randomBytes(32).toString("hex");
// Callers waiting for the runtime; settled on the next READY line or a fatal failure.
let portWaiters = [];
let fatalBackendError = null;

const getKeysFilePath = () => path.join(app.getPath("userData"), "stored_keys.json");

function readStoredEncryptedKeys() {
  try {
    const file = getKeysFilePath();
    if (!fs.existsSync(file)) return {};
    const value = JSON.parse(fs.readFileSync(file, "utf8"));
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch {
    console.error("[main] Could not read encrypted provider-key store.");
    return {};
  }
}

function writeStoredEncryptedKeys(keys) {
  try {
    const file = getKeysFilePath();
    const dir = path.dirname(file);
    fs.mkdirSync(dir, { recursive: true });
    const temporary = file + ".tmp-" + process.pid;
    fs.writeFileSync(temporary, JSON.stringify(keys, null, 2), { encoding: "utf8", mode: 0o600 });
    try { fs.rmSync(file, { force: true }); } catch {}
    fs.renameSync(temporary, file);
    return true;
  } catch {
    console.error("[main] Could not persist provider keys.");
    return false;
  }
}

function encryptionAvailable() {
  try { return Boolean(safeStorage && safeStorage.isEncryptionAvailable()); }
  catch { return false; }
}

function encodeKey(key) {
  if (encryptionAvailable()) {
    return {
      version: 1, protection: "safeStorage",
      value: safeStorage.encryptString(key).toString("base64"),
      hint: key.slice(-4),
    };
  }
  if (process.env.AGENTFORGE_ALLOW_PLAINTEXT_KEYS === "1") {
    return { version: 1, protection: "plaintext-opt-in", value: key, hint: key.slice(-4) };
  }
  return null;
}

function decodeKey(entry) {
  try {
    if (entry && typeof entry === "object" && typeof entry.value === "string") {
      if (entry.protection === "safeStorage" && encryptionAvailable()) {
        return safeStorage.decryptString(Buffer.from(entry.value, "base64"));
      }
      if (entry.protection === "plaintext-opt-in" && process.env.AGENTFORGE_ALLOW_PLAINTEXT_KEYS === "1") {
        return entry.value;
      }
      return null;
    }
    // Prior releases stored base64-encrypted data or an insecure base64 fallback.
    // Legacy plaintext is only decoded when the user explicitly opts in.
    if (typeof entry === "string") {
      const buffer = Buffer.from(entry, "base64");
      if (encryptionAvailable()) return safeStorage.decryptString(buffer);
      if (process.env.AGENTFORGE_ALLOW_PLAINTEXT_KEYS === "1") return buffer.toString("utf8");
    }
  } catch {
    return null;
  }
  return null;
}

function getApiKeyStatus(provider) {
  if (!KEY_SLOTS.has(provider)) return { saved: false, hint: "" };
  const entry = readStoredEncryptedKeys()[provider];
  if (!entry) return { saved: false, hint: "" };
  if (entry && typeof entry === "object" && typeof entry.hint === "string") {
    return { saved: true, hint: "••••" + entry.hint.slice(-4) };
  }
  const key = decodeKey(entry);
  return key ? { saved: true, hint: "••••" + key.slice(-4) } : { saved: false, hint: "" };
}

function saveApiKey(provider, key) {
  if (!KEY_SLOTS.has(provider) || typeof key !== "string") return { ok: false, reason: "invalid-provider" };
  const trimmed = key.trim();
  if (!trimmed) return deleteApiKey(provider, false);
  const encoded = encodeKey(trimmed);
  if (!encoded) return { ok: false, reason: "encryption-unavailable" };
  const store = readStoredEncryptedKeys();
  store[provider] = encoded;
  if (!writeStoredEncryptedKeys(store)) return { ok: false, reason: "storage-failed" };
  return { ok: true, saved: true, hint: "••••" + trimmed.slice(-4), protection: encoded.protection };
}

function deleteApiKey(provider, shouldSync = true) {
  if (!KEY_SLOTS.has(provider)) return { ok: false, reason: "invalid-provider" };
  const store = readStoredEncryptedKeys();
  delete store[provider];
  if (!writeStoredEncryptedKeys(store)) return { ok: false, reason: "storage-failed" };
  return { ok: true, saved: false, hint: "", applied: shouldSync ? undefined : true };
}

async function waitForBackendPort(timeoutMs = 15000) {
  if (backendPort !== null) return backendPort;
  if (fatalBackendError) throw fatalBackendError;
  let waiter;
  let timer;
  try {
    return await new Promise((resolve, reject) => {
      waiter = { resolve, reject };
      portWaiters.push(waiter);
      timer = setTimeout(() => reject(new Error("Runtime startup timed out")), timeoutMs);
    });
  } finally {
    clearTimeout(timer);
    portWaiters = portWaiters.filter((item) => item !== waiter);
  }
}

async function postRuntimeKeys(payload) {
  const port = await waitForBackendPort();
  const response = await fetch(`http://127.0.0.1:${port}/settings/keys`, {
    method: "POST",
    headers: { "Authorization": "Bearer " + apiToken, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Runtime rejected provider-key update");
  return { status: "ok" };
}

async function syncStoredKeysToBackend() {
  const stored = readStoredEncryptedKeys();
  const payload = {};
  for (const provider of KEY_SLOTS) {
    if (!stored[provider]) continue;
    const key = decodeKey(stored[provider]);
    if (key) payload[provider] = key;
  }
  if (Object.keys(payload).length === 0) return { status: "ok" };
  return postRuntimeKeys(payload);
}

async function saveAndApplyApiKey(provider, key) {
  const result = saveApiKey(provider, key);
  if (!result.ok) return result;
  try {
    await postRuntimeKeys({ [provider]: key.trim() });
    return { ...result, applied: true };
  } catch {
    return { ...result, applied: false };
  }
}

async function removeAndApplyApiKey(provider) {
  const result = deleteApiKey(provider, false);
  if (!result.ok) return result;
  try {
    await postRuntimeKeys({ [provider]: "" });
    return { ...result, applied: true };
  } catch {
    return { ...result, applied: false };
  }
}

function publishBackendPort(port) {
  const restarted = backendPort === null && restartHistory.length > 0;
  backendPort = port;
  fatalBackendError = null;
  const waiters = portWaiters;
  portWaiters = [];
  for (const waiter of waiters) waiter.resolve(port);
  void syncStoredKeysToBackend().catch(() => console.warn("[main] Saved provider keys could not be applied yet."));
  if (restarted && mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("backend-restarted", port);
  }
}

function rejectBackendPort(error) {
  fatalBackendError = error;
  const waiters = portWaiters;
  portWaiters = [];
  for (const waiter of waiters) waiter.reject(error);
}

function scheduleBackendRestart() {
  if (appQuitting || stoppingBackend || restartTimer) return;
  const now = Date.now();
  while (restartHistory.length && now - restartHistory[0] > RESTART_WINDOW_MS) restartHistory.shift();
  if (restartHistory.length >= MAX_RESTARTS) {
    console.error("[main] Local runtime keeps exiting; giving up on automatic restarts.");
    rejectBackendPort(new Error("The local runtime stopped repeatedly. Restart AgentForge."));
    return;
  }
  const delay = Math.min(1000 * 2 ** restartHistory.length, 15000);
  restartHistory.push(now);
  console.warn(`[main] Local runtime exited unexpectedly; restarting in ${delay} ms.`);
  restartTimer = setTimeout(() => {
    restartTimer = null;
    if (!appQuitting) startPythonBackend();
  }, delay);
}

function commandExists(command) {
  const result = spawnSync(process.platform === "win32" ? "where" : "which", [command], { stdio: "ignore", windowsHide: true });
  return result.status === 0;
}

function startPythonBackend() {
  const projectRoot = path.resolve(__dirname, "..");
  const cwd = isDev ? path.join(projectRoot, "python-runtime") : path.join(process.resourcesPath, "python-runtime");
  let executable;
  let args = [];

  if (isDev) {
    if (commandExists("uv")) {
      executable = process.platform === "win32" ? "uv.exe" : "uv";
      args = ["run", "python", "main.py"];
    } else {
      const venvPython = path.join(cwd, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
      executable = fs.existsSync(venvPython) ? venvPython : (process.platform === "win32" ? "python" : "python3");
      args = ["main.py"];
    }
  } else {
    const binaryName = process.platform === "win32" ? "python-runtime.exe" : "python-runtime";
    const binaryPath = path.join(cwd, binaryName);
    if (!fs.existsSync(binaryPath)) {
      rejectBackendPort(new Error("Packaged Python runtime is missing. Rebuild the installer."));
      console.error("[main] Packaged Python runtime is missing.");
      return;
    }
    executable = binaryPath;
  }

  // Bundled ffmpeg/ffprobe (scripts/fetch-ffmpeg.mjs) go first on PATH so every media
  // tool and yt-dlp find them; a system install is still used when none is bundled.
  const env = {
    ...process.env,
    AGENTFORGE_EMBEDDING_CACHE_DIR: isDev
      ? path.join(projectRoot, "python-runtime", "models", "embedding-cache")
      : path.join(process.resourcesPath, "embedding-model-cache"),
  };
  const bundledFfmpeg = isDev ? null : path.join(process.resourcesPath, "ffmpeg");
  if (bundledFfmpeg && fs.existsSync(bundledFfmpeg)) {
    const pathKey = Object.keys(env).find((key) => key.toUpperCase() === "PATH") || "PATH";
    env[pathKey] = bundledFfmpeg + path.delimiter + (env[pathKey] || "");
  }

  console.log(`[main] Starting local Python runtime (${isDev ? "development" : "packaged"}).`);
  try {
    pythonProcess = spawn(executable, args, {
      cwd,
      env: {
        ...env,
        PORT: "0",
        AGENTFORGE_WATCH_PARENT: "1",
        AGENTFORGE_TOKEN: apiToken,
        AGENTFORGE_DATA_DIR: path.join(app.getPath("userData"), "data"),
      },
      shell: false,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });

    let readyBuffer = "";
    const handleOutput = (data) => {
      const output = data.toString("utf8");
      if (!output.includes("AGENTFORGE_READY:")) console.log("[python-runtime] " + output.trim());
      readyBuffer = (readyBuffer + output).slice(-4096);
      const match = readyBuffer.match(/AGENTFORGE_READY:(\d+)/);
      if (match && match[1]) {
        const port = Number.parseInt(match[1], 10);
        if (Number.isInteger(port) && port > 0 && backendPort === null) {
          console.log("[main] Local runtime is ready.");
          publishBackendPort(port);
          readyBuffer = "";
        }
      }
    };

    pythonProcess.stdout?.on("data", handleOutput);
    pythonProcess.stderr?.on("data", handleOutput);
    const child = pythonProcess;
    child.once("error", () => {
      if (pythonProcess === child) pythonProcess = null;
      scheduleBackendRestart();
    });
    child.once("exit", (code) => {
      console.log(`[main] Local runtime exited (${code ?? "unknown"}).`);
      if (pythonProcess === child) pythonProcess = null;
      backendPort = null;
      if (!stoppingBackend && !appQuitting) scheduleBackendRestart();
    });
  } catch {
    console.error("[main] Failed to start local runtime.");
    scheduleBackendRestart();
  }
}

function stopPythonBackend() {
  const child = pythonProcess;
  if (!child || stoppingBackend) return Promise.resolve();
  stoppingBackend = true;
  return new Promise((resolve) => {
    let finished = false;
    let killTimer;
    const finish = () => {
      if (finished) return;
      finished = true;
      clearTimeout(killTimer);
      if (pythonProcess === child) pythonProcess = null;
      stoppingBackend = false;
      resolve();
    };
    child.once("exit", finish);
    try { child.stdin?.end(); } catch {}
    try { child.kill("SIGTERM"); } catch {}
    killTimer = setTimeout(() => {
      if (process.platform === "win32" && child.pid) {
        const treeKill = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], { windowsHide: true, stdio: "ignore" });
        treeKill.once("exit", finish);
        treeKill.once("error", finish);
      } else {
        try { child.kill("SIGKILL"); } catch {}
        finish();
      }
    }, 2000);
    killTimer.unref?.();
  });
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: "AgentForge",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  const devServerUrl = process.env.VITE_DEV_SERVER_URL || "http://localhost:5173";
  const allowedDevOrigin = new URL(devServerUrl).origin;
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    try {
      if (new URL(url).protocol === "https:") void shell.openExternal(url);
    } catch {}
    return { action: "deny" };
  });
  const packagedDocumentPath = path.resolve(__dirname, "../dist/index.html");
  const packagedDocumentUrl = pathToFileURL(packagedDocumentPath);
  mainWindow.webContents.on("will-navigate", (event, url) => {
    const allowed = isDev
      ? (() => { try { return new URL(url).origin === allowedDevOrigin; } catch { return false; } })()
      : (() => {
          try {
            const target = new URL(url);
            const expected = new URL(packagedDocumentUrl.href);
            target.search = "";
            target.hash = "";
            expected.search = "";
            expected.hash = "";
            return target.protocol === "file:" && target.href === expected.href;
          } catch {
            return false;
          }
        })();
    if (!allowed) event.preventDefault();
  });

  if (isDev) await mainWindow.loadURL(devServerUrl);
  else await mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  mainWindow.on("closed", () => { mainWindow = null; });
}

function trustedIpc(event) {
  return mainWindow && event.sender === mainWindow.webContents;
}

if (gotSingleInstanceLock) {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });
}

ipcMain.handle("get-api-token", (event) => trustedIpc(event) ? apiToken : "");
ipcMain.handle("get-backend-port", async (event) => {
  if (!trustedIpc(event)) throw new Error("Untrusted IPC sender");
  return waitForBackendPort();
});
ipcMain.handle("get-api-key-status", (event, provider) => {
  if (!trustedIpc(event)) throw new Error("Untrusted IPC sender");
  return getApiKeyStatus(provider);
});
ipcMain.handle("save-api-key", async (event, provider, key) => {
  if (!trustedIpc(event)) throw new Error("Untrusted IPC sender");
  return saveAndApplyApiKey(provider, key);
});
ipcMain.handle("delete-api-key", async (event, provider) => {
  if (!trustedIpc(event)) throw new Error("Untrusted IPC sender");
  return removeAndApplyApiKey(provider);
});
ipcMain.handle("sync-api-keys", async (event) => {
  if (!trustedIpc(event)) throw new Error("Untrusted IPC sender");
  try { return await syncStoredKeysToBackend(); }
  catch { throw new Error("Saved keys could not be applied to the local runtime"); }
});

app.on("before-quit", (event) => {
  appQuitting = true;
  if (restartTimer) clearTimeout(restartTimer);
  restartTimer = null;
  if (!gotSingleInstanceLock || !pythonProcess || stoppingBackend) return;
  event.preventDefault();
  void stopPythonBackend().finally(() => app.exit(0));
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.whenReady().then(async () => {
    startPythonBackend();
    await createWindow();
    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) void createWindow();
    });
  }).catch(() => {
    console.error("[main] Application startup failed.");
    app.quit();
  });
}
