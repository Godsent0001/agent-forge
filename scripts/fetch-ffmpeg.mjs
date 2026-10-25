#!/usr/bin/env node
// Download pinned LGPL static ffmpeg + ffprobe builds for the packaging target
// into build/ffmpeg/, verifying SHA-256 before anything is unpacked.
// electron-builder ships that folder as resources/ffmpeg and Electron puts it
// first on the sidecar's PATH, so video/audio tools work without a system ffmpeg.
//
// Builds: BtbN/FFmpeg-Builds "lgpl" variant (no GPL-only parts such as libx264;
// H.264 comes from openh264). BtbN keeps the last build of each month for two
// years, so the pin below is a month-end build. There is no maintained LGPL
// macOS build, so macOS packages fall back to an ffmpeg on the user's PATH.
//
// Usage: node scripts/fetch-ffmpeg.mjs [platform] [arch]
//   Defaults to the current platform/arch. Set AGENTFORGE_SKIP_FFMPEG=1 to skip.
import { spawnSync } from "child_process";
import { createHash } from "crypto";
import fs from "fs";
import os from "os";
import path from "path";
import { fileURLToPath } from "url";

const TAG = "autobuild-2026-09-30-13-08";
const VERSION = "n8.1.3-9-g29e619e767";
const RELEASE = `https://github.com/BtbN/FFmpeg-Builds/releases/download/${TAG}`;
const TARGETS = {
  "linux-x64": { build: "linux64", ext: ".tar.xz", sha256: "dfa863a00ca81f1bdf58a372b18cff4820f0017e55de32778de8ecd8ed92a02e" },
  "linux-arm64": { build: "linuxarm64", ext: ".tar.xz", sha256: "8463881ca7a25015ca6e00f5c91dd2f1637eb73d33c8230413cb74db760a86b3" },
  "win32-x64": { build: "win64", ext: ".zip", sha256: "4a7642b2264c03e8a0ce8a3825b933ee5580656f45695a086fe7e294045ffc0a" },
};
const NOTICE = `AgentForge runs these programs as separate executables; it does not link them.

ffmpeg and ffprobe ${VERSION} (LGPL static build) from
https://github.com/BtbN/FFmpeg-Builds, release ${TAG}.
They are licensed under the GNU LGPL v3 (built with --enable-version3); see LICENSE.txt.
Corresponding source code: https://github.com/FFmpeg/FFmpeg/tree/${VERSION.split("-g").pop()}
and the build scripts at https://github.com/BtbN/FFmpeg-Builds/tree/master/scripts.d
H.264 encoding uses Cisco's openh264 library compiled into this build.
`;

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} failed (exit ${result.status ?? result.error})`);
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
  const spec = TARGETS[target];
  const stamp = `${target}:${VERSION}`;

  if (fs.existsSync(marker) && fs.readFileSync(marker, "utf8") === stamp) {
    console.log(`[ffmpeg] build/ffmpeg already holds ${stamp}.`);
    return;
  }
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });

  if (!spec) {
    // electron-builder still needs the folder; the app then uses a system ffmpeg.
    fs.writeFileSync(path.join(outDir, "NOTICE.txt"),
      `No ffmpeg is bundled for ${target}. Install ffmpeg (for example with Homebrew) and ensure it is on PATH.\n`);
    fs.writeFileSync(marker, stamp);
    console.warn(`[ffmpeg] No pinned LGPL build for ${target}; the packaged app will use ffmpeg from PATH.`);
    return;
  }

  const name = `ffmpeg-${VERSION}-${spec.build}-lgpl-8.1`;
  const archiveName = name + spec.ext;
  const response = await fetch(`${RELEASE}/${archiveName}`);
  if (!response.ok) throw new Error(`Download of ${archiveName} failed: HTTP ${response.status}`);
  const data = Buffer.from(await response.arrayBuffer());
  const actual = createHash("sha256").update(data).digest("hex");
  if (actual !== spec.sha256) throw new Error(`Checksum mismatch for ${archiveName}: expected ${spec.sha256}, got ${actual}`);

  const work = fs.mkdtempSync(path.join(os.tmpdir(), "agentforge-ffmpeg-"));
  try {
    const archive = path.join(work, archiveName);
    fs.writeFileSync(archive, data);
    const exe = platform === "win32" ? ".exe" : "";
    const members = [`${name}/bin/ffmpeg${exe}`, `${name}/bin/ffprobe${exe}`, `${name}/LICENSE.txt`];
    // tar handles .tar.xz everywhere and .zip on Windows (bsdtar); use unzip for .zip elsewhere.
    if (spec.ext === ".zip" && process.platform !== "win32") run("unzip", ["-q", archive, ...members, "-d", work]);
    else run("tar", ["-xf", archive, "-C", work, ...members]);
    for (const member of members) {
      const destination = path.join(outDir, path.basename(member));
      fs.copyFileSync(path.join(work, member), destination);
      if (!member.endsWith(".txt")) fs.chmodSync(destination, 0o755);
      console.log(`[ffmpeg] ${path.basename(member)} (${(fs.statSync(destination).size / 1e6).toFixed(1)} MB)`);
    }
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
  fs.writeFileSync(path.join(outDir, "NOTICE.txt"), NOTICE);
  fs.writeFileSync(marker, stamp);
}

main().catch((error) => {
  console.error(`[ffmpeg] ${error.message}`);
  process.exit(1);
});
