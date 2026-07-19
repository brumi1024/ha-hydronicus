import { build } from "esbuild";
import { readFile, writeFile } from "node:fs/promises";

const manifest = JSON.parse(
  await readFile("../custom_components/hydronicus/manifest.json", "utf8"),
);
const result = await build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  format: "esm",
  target: "es2022",
  minify: true,
  legalComments: "none",
  define: { HYDRONICUS_FRONTEND_VERSION: JSON.stringify(manifest.version) },
  outfile: "../custom_components/hydronicus/frontend/hydronicus-plant-card.js",
  write: false,
});
await writeFile(
  "../custom_components/hydronicus/frontend/hydronicus-plant-card.js",
  result.outputFiles[0].text.replace(/[ \t]+$/gm, ""),
);
