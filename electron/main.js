import { app, BrowserWindow, ipcMain, safeStorage } from "electron";
import path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process";
import fs from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow = null;
let pythonProcess = null;
let backendPort = null;
let portResolver = null;

// Initialize port promise
const portPromise = new Promise((resolve) => {
  portResolver = resolve;
});

// Key storage file path
const getKeysFilePath = () => path.join(app.getPath("userData"), "stored_keys.json");

function readStoredEncryptedKeys() {
  try {
    const keysFilePath = getKeysFilePath();
    if (fs.existsSync(keysFilePath)) {
      const raw = fs.readFileSync(keysFilePath, "utf8");
      return JSON.parse(raw);
    }
  } catch (err) {
    console.error("[main] Error reading stored keys file:", err);
  }
  return {};
}

function writeStoredEncryptedKeys(keys) {
  try {
    const keysFilePath = getKeysFilePath();
    fs.writeFileSync(keysFilePath, JSON.stringify(keys, null, 2), "utf8");
  } catch (err) {
    console.error("[main] Error writing stored keys file:", err);
  }
}

function saveApiKey(provider, key) {
  const store = readStoredEncryptedKeys();
  if (!key) {
    delete store[provider];
  } else if (safeStorage && safeStorage.isEncryptionAvailable()) {
    const encrypted = safeStorage.encryptString(key);
    store[provider] = encrypted.toString("base64");
  } else {
    // Fallback unencrypted if safeStorage not available on system
    store[provider] = Buffer.from(key, "utf8").toString("base64");
  }
  writeStoredEncryptedKeys(store);
  return true;
}

function getApiKey(provider) {
  const store = readStoredEncryptedKeys();
  const rawVal = store[provider];
  if (!rawVal) return null;

  try {
    const buf = Buffer.from(rawVal, "base64");
    if (safeStorage && safeStorage.isEncryptionAvailable()) {
      return safeStorage.decryptString(buf);
    } else {
      return buf.toString("utf8");
    }
  } catch (err) {
    console.error(`[main] Failed to decrypt key for ${provider}:`, err);
    return null;
  }
}

function deleteApiKey(provider) {
  const store = readStoredEncryptedKeys();
  delete store[provider];
  writeStoredEncryptedKeys(store);
  return true;
}

function startPythonBackend() {
  const isDev = process.env.NODE_ENV === "development" || !app.isPackaged;
  const projectRoot = path.resolve(__dirname, "..");

  let executable;
  let args = [];
  let cwd;

  if (isDev) {
    // In development mode, run python script directly in python-runtime directory
    cwd = path.join(projectRoot, "python-runtime");
    executable = process.platform === "win32" ? "python" : "python3";
    args = ["main.py"];
  } else {
    // In production mode, spawn standalone executable if present, or run python with main.py in resources
    cwd = path.join(process.resourcesPath, "python-runtime");
    const binaryName = process.platform === "win32" ? "python-runtime.exe" : "python-runtime";
    const binaryPath = path.join(cwd, binaryName);

    if (fs.existsSync(binaryPath)) {
      executable = binaryPath;
      args = [];
    } else {
      executable = process.platform === "win32" ? "python" : "python3";
      args = ["main.py"];
    }
  }

  console.log(`[main] Spawning Python runtime: ${executable} ${args.join(" ")} (cwd: ${cwd})`);

  try {
    pythonProcess = spawn(executable, args, {
      cwd,
      env: { ...process.env },
      shell: false,
    });

    const handleOutput = (data) => {
      const text = data.toString("utf8");
      console.log(`[python-runtime] ${text.trim()}`);

      if (text.includes("AGENTFORGE_READY:")) {
        const match = text.match(/AGENTFORGE_READY:(\d+)/);
        if (match && match[1]) {
          const port = parseInt(match[1], 10);
          if (!isNaN(port) && port > 0) {
            backendPort = port;
            console.log(`[main] Captured Python runtime dynamic port: ${backendPort}`);
            if (portResolver) {
              portResolver(backendPort);
              portResolver = null;
            }
          }
        }
      }
    };

    if (pythonProcess.stdout) {
      pythonProcess.stdout.on("data", handleOutput);
    }
    if (pythonProcess.stderr) {
      pythonProcess.stderr.on("data", handleOutput);
    }

    pythonProcess.on("error", (err) => {
      console.error("[main] Python process spawn error:", err);
    });

    pythonProcess.on("exit", (code, signal) => {
      console.log(`[main] Python runtime exited with code ${code}, signal ${signal}`);
      pythonProcess = null;
    });
  } catch (err) {
    console.error("[main] Failed to spawn Python process:", err);
  }
}

function stopPythonBackend() {
  if (pythonProcess) {
    console.log("[main] Terminating Python process...");
    pythonProcess.kill("SIGTERM");
    setTimeout(() => {
      if (pythonProcess) {
        pythonProcess.kill("SIGKILL");
        pythonProcess = null;
      }
    }, 2000);
  }
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
    },
  });

  const isDev = process.env.NODE_ENV === "development" || !app.isPackaged;
  if (isDev) {
    const devServerUrl = process.env.VITE_DEV_SERVER_URL || "http://localhost:5173";
    await mainWindow.loadURL(devServerUrl);
  } else {
    await mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// IPC handlers
ipcMain.handle("get-backend-port", async () => {
  if (backendPort !== null) {
    return backendPort;
  }
  const timeoutPromise = new Promise((_, reject) => {
    setTimeout(() => reject(new Error("Timeout waiting for AgentForge Python backend to start.")), 15000);
  });
  return Promise.race([portPromise, timeoutPromise]);
});

ipcMain.handle("save-api-key", (_event, provider, key) => {
  return saveApiKey(provider, key);
});

ipcMain.handle("get-api-key", (_event, provider) => {
  return getApiKey(provider);
});

ipcMain.handle("delete-api-key", (_event, provider) => {
  return deleteApiKey(provider);
});

app.whenReady().then(() => {
  startPythonBackend();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", () => {
  stopPythonBackend();
});

app.on("window-all-closed", () => {
  stopPythonBackend();
  if (process.platform !== "darwin") {
    app.quit();
  }
});
