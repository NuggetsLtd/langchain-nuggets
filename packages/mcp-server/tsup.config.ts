import { defineConfig } from "tsup";

export default defineConfig([
  {
    entry: { index: "src/index.ts" },
    format: ["esm", "cjs"],
    dts: true,
    sourcemap: true,
    clean: true,
    platform: "node",
    outExtension({ format }) {
      return { js: format === "esm" ? ".mjs" : ".cjs" };
    },
  },
  {
    entry: { cli: "src/cli.ts" },
    format: ["esm"],
    sourcemap: true,
    platform: "node",
    banner: { js: "#!/usr/bin/env node" },
    outExtension() {
      return { js: ".mjs" };
    },
  },
  {
    entry: { sse: "src/sse.ts" },
    format: ["esm", "cjs"],
    dts: true,
    sourcemap: true,
    platform: "node",
    outExtension({ format }) {
      return { js: format === "esm" ? ".mjs" : ".cjs" };
    },
  },
]);
