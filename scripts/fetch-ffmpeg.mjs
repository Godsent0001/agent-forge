#!/usr/bin/env node
// Download pinned static ffmpeg + ffprobe builds for the packaging target into
// build/ffmpeg/, verifying SHA-256 before anything is written. electron-builder
// ships that folder as resources/ffmpeg and Electron puts it first on the
// sidecar's PATH, so video/audio tools work without a system ffmpeg.
//
// Usage: node scripts/fetch-ffmpeg.mjs [platform] [arch]
//   Defaults to the current platform/arch. Set AGENTFORGE_SKIP_FFMPEG=1 to skip.
import { createHash } from "crypto";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { gunzipSync } from "zlib";

const RELEASE = "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0";
const SHA256 = {
  "ffmpeg-darwin-arm64.gz": "6be74d6f449889c2e87a75873894f8520cad56c08ac76f2a628d85b0519daaca",
  "ffmpeg-darwin-x64.gz": "a12354fce7eb62361473bbe10d53a1893695babd35869ec8e92e5dfea8d0440b",
  "ffmpeg-linux-arm64.gz": "2b708b2d15041d2a192c1db24c7a8a1d24f645a8242dce1c744ff2392b86ada1",
  "ffmpeg-linux-x64.gz": "17c1ae10b52ac499180679fe6ba77e17642390c4eedb0f1e3b0ac045da55128f",
  "ffmpeg-win32-x64.gz": "450d66226c79405c724e821f291cab0911e934bfa9fa2231adcab587f3e07b50",
  "ffprobe-darwin-arm64.gz": "a4db76bafdb8529312e138fb55aaf143cad21b6d672e2634c9dd07ae83c6a310",
  "ffprobe-darwin-x64.gz": "b75d816c5658bd417a2a05e174957963e2f9f85be3eb731b2a04467545a665dc",
  "ffprobe-linux-arm64.gz": "dede9087c8ac8dfe48457f1aa33eab560a1c66c91a6a6a540c3bd6cfc5f9abc4",
  "ffprobe-linux-x64.gz": "88ca6818d82a70e87de2bb6166026ad411528c72eda0e4e11ed25d185116ee17",
  "ffprobe-win32-x64.gz": "3f33adbad509f324e6f72449a5e8428fd655fb2b2eebf1d782c7ef23c44eed6a",
  "darwin-arm64.LICENSE": "cb48bf09a11f5fb576cddb0431c8f5ed0a60157a9ec942adffc13907cbe083f2",
  "darwin-x64.LICENSE": "cb48bf09a11f5fb576cddb0431c8f5ed0a60157a9ec942adffc13907cbe083f2",
  "linux-arm64.LICENSE": "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903",
  "linux-x64.LICENSE": "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903",
  "win32-x64.LICENSE": "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903",
};
const NOTICE = `AgentForge invokes these programs as separate executables; it does not link them.

ffmpeg and ffprobe 6.0 static builds from https://github.com/eugeneware/ffmpeg-static
(release b6.0). They are licensed under the GNU GPL v3; see LICENSE in this folder.
Corresponding source code: https://ffmpeg.org/releases/ffmpeg-6.0.tar.xz and the build
recipes linked from https://github.com/eugeneware/ffmpeg-static#sources-of-the-binaries
`;

async function download(name) {
  const expected = SHA256[name];
  if (!expected) throw new Error(`No pinned checksum for ${name}; this platform is not supported.`);
  const response = await fetch(`${RELEASE}/${name}`);
  if (!response.ok) throw new Error(`Download of ${name} failed: HTTP ${response.status}`);
  const data = Buffer.from(await response.arrayBuffer());
  const actual = createHash("sha256").update(data).digest("hex");
  if (actual !== expected) throw new Error(`Checksum mismatch for ${name}: expected ${expected}, got ${actual}`);
  return data;
}

async function main() {
  if (process.env.AGENTFORGE_SKIP_FFMPEG === "1") {
    console.log("[ffmpeg] AGENTFORGE_SKIP_FFMPEG=1; not bundling ffmpeg.");
    return;
  }
  const platform = process.argv[2] || process.platform;
  const arch = process.argv[3] || process.arch;
  const target = `${platform}-${arch}`;
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const outDir = path.join(root, "build", "ffmpeg");
  const marker = path.join(outDir, ".target");
  const ext = platform === "win32" ? ".exe" : "";

  if (fs.existsSync(marker) && fs.readFileSync(marker, "utf8") === target) {
    console.log(`[ffmpeg] build/ffmpeg already holds ${target}.`);
    return;
  }
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });
  for (const tool of ["ffmpeg", "ffprobe"]) {
    const binary = gunzipSync(await download(`${tool}-${target}.gz`));
    const file = path.join(outDir, tool + ext);
    fs.writeFileSync(file, binary, { mode: 0o755 });
    console.log(`[ffmpeg] ${tool}${ext} (${(binary.length / 1e6).toFixed(1)} MB)`);
  }
  fs.writeFileSync(path.join(outDir, "LICENSE"), await download(`${target}.LICENSE`));
  fs.writeFileSync(path.join(outDir, "NOTICE.txt"), NOTICE);
  fs.writeFileSync(marker, target);
}

main().catch((error) => {
  console.error(`[ffmpeg] ${error.message}`);
  process.exit(1);
});
