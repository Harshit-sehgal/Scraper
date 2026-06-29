#!/usr/bin/env node
/**
 * DataForge frontend build script.
 *
 * F-FRONTEND-001: introduces esbuild as a minimal bundler with code
 * splitting and CSS tree-shaking so first-paint payloads are smaller
 * and contributors have a single `npm run build` entry point.
 *
 * Behaviour:
 *   - Bundles frontend/app.js → frontend/dist/app.js (main chunk +
 *     dynamic-import chunks under dist/chunks/)
 *   - Bundles styles.css → frontend/dist/styles.css (single minified
 *     HTTP request; replaces the seven @import cascade sources
 *     with one tree-shaken bundle)
 *   - Generates dist/manifest.json mapping source paths → output paths
 *   - Verifies F-FRONTEND-001 acceptance: first-paint CSS < 200 KB
 */

import { build, context } from "esbuild";
import { writeFileSync, mkdirSync } from "fs";
import { resolve, relative } from "path";

const FRONTEND_DIR = resolve(import.meta.dirname);
const DIST_DIR = resolve(FRONTEND_DIR, "dist");
const IS_WATCH = process.argv.includes("--watch");

const BASE = {
  bundle: true,
  format: "esm",
  target: ["es2020"],
  sourcemap: true,
  minify: true,
  logLevel: "info",
  absWorkingDir: FRONTEND_DIR,
};

async function buildFrontend() {
  mkdirSync(DIST_DIR, { recursive: true });

  // 1. JS — main entry with code splitting for dynamic imports
  const jsResult = await build({
    ...BASE,
    entryPoints: [resolve(FRONTEND_DIR, "app.js")],
    splitting: true,
    loader: { ".js": "js", ".mjs": "js" },
    chunkNames: "chunks/[name]-[hash]",
    outdir: DIST_DIR,
    metafile: true,
  });

  // 2. CSS — bundle the @import cascade into one minified file
  const cssResult = await build({
    ...BASE,
    entryPoints: [resolve(FRONTEND_DIR, "styles.css")],
    loader: {
      ".css": "css",
      ".woff": "file",
      ".woff2": "file",
      ".ttf": "file",
      ".otf": "file",
      ".eot": "file",
      ".svg": "file",
      ".png": "file",
      ".jpg": "file",
      ".gif": "file",
    },
    entryNames: "[name]",
    outdir: DIST_DIR,
    metafile: true,
  });

  // 3. Manifest
  const manifest = {
    ...buildManifest(jsResult),
    ...buildManifest(cssResult),
  };
  writeFileSync(resolve(DIST_DIR, "manifest.json"), JSON.stringify(manifest, null, 2));

  // 4. Acceptance check
  reportSizes(jsResult, cssResult);
}

function buildManifest(esbuildResult) {
  const manifest = {};
  for (const [outPath, entry] of Object.entries(esbuildResult.metafile.outputs)) {
    const rel = relative(FRONTEND_DIR, outPath);
    if (entry.entryPoint) {
      const srcRel = relative(FRONTEND_DIR, entry.entryPoint);
      manifest[srcRel] = rel;
    }
    manifest[rel] = rel;
  }
  return manifest;
}

function reportSizes(jsResult, cssResult) {
  const outputs = { ...jsResult.metafile.outputs, ...cssResult.metafile.outputs };
  console.log("\n── Bundle sizes ──");
  let cssBytes = 0;
  for (const [outPath, entry] of Object.entries(outputs)) {
    const kb = (entry.bytes / 1024).toFixed(1);
    const label = relative(FRONTEND_DIR, outPath);
    console.log(`  ${label}: ${kb} KB`);
    if (label.endsWith("/styles.css") && !label.endsWith(".map")) {
      cssBytes = entry.bytes;
    }
  }
  console.log("");
  if (cssBytes > 0) {
    const cssKb = cssBytes / 1024;
    if (cssKb < 200) {
      console.log(`  ✅ First-paint CSS: ${cssKb.toFixed(1)} KB < 200 KB (F-FRONTEND-001 met)`);
    } else {
      console.warn(`  ⚠️  First-paint CSS: ${cssKb.toFixed(1)} KB ≥ 200 KB (F-FRONTEND-001 acceptance NOT met)`);
    }
  }
}

async function watchFrontend() {
  mkdirSync(DIST_DIR, { recursive: true });
  const ctx = await context({
    ...BASE,
    entryPoints: [resolve(FRONTEND_DIR, "app.js"), resolve(FRONTEND_DIR, "styles.css")],
    splitting: true,
    loader: { ".js": "js", ".mjs": "js", ".css": "css" },
    chunkNames: "chunks/[name]-[hash]",
    outdir: DIST_DIR,
  });
  await ctx.watch();
  console.log("👀 Watching frontend files for changes...");
}

if (IS_WATCH) {
  watchFrontend().catch((err) => {
    console.error(err);
    process.exit(1);
  });
} else {
  buildFrontend().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
