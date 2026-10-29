import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const destination = path.join(root, "python-runtime", "python-interpreter");

function runUv(args) {
  const result = spawnSync("uv", args, { cwd: root, encoding: "utf8", windowsHide: true });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`uv ${args.join(" ")} failed: ${(result.stderr || result.stdout || "").trim()}`);
  }
  return (result.stdout || "").trim();
}

// The PyInstaller backend is an application executable, not a reusable Python
// interpreter. Bundle the same pinned major/minor interpreter used for the build
// so project .venv creation never depends on Python being installed on the user's PC.
runUv(["python", "install", "3.11"]);
const executable = runUv(["python", "find", "3.11"]);
const home = process.platform === "win32"
  ? path.dirname(executable)
  : path.dirname(path.dirname(executable));

if (!fs.existsSync(executable)) throw new Error(`uv returned a missing Python interpreter: ${executable}`);
fs.rmSync(destination, { recursive: true, force: true });
fs.mkdirSync(path.dirname(destination), { recursive: true });
fs.cpSync(home, destination, {
  recursive: true,
  dereference: false,
  filter: (source) => !source.split(path.sep).includes("__pycache__") && !source.endsWith(".pyc"),
});
console.log(`Bundled Python interpreter from ${home} into ${destination}`);
