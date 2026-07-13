import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { createServer, loadEnv } from "vite";
import { getHttpsServerOptions } from "office-addin-dev-certs";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const environment = {
  ...loadEnv("development", projectRoot, ""),
  ...process.env,
};

const keyPath = environment.LATEXSNIPPER_DEV_HTTPS_KEY?.trim();
const certificatePath = environment.LATEXSNIPPER_DEV_HTTPS_CERT?.trim();

if ((keyPath && !certificatePath) || (!keyPath && certificatePath)) {
  throw new Error(
    "LATEXSNIPPER_DEV_HTTPS_KEY and LATEXSNIPPER_DEV_HTTPS_CERT must be set together.",
  );
}

const https =
  keyPath && certificatePath
    ? {
        key: await readFile(keyPath),
        cert: await readFile(certificatePath),
      }
    : await getHttpsServerOptions();

const server = await createServer({
  configFile: resolve(projectRoot, "vite.config.ts"),
  mode: "development",
  server: {
    host: "localhost",
    port: 3000,
    strictPort: true,
    https,
  },
});

await server.listen();
server.printUrls();

const close = async () => {
  await server.close();
  process.exit(0);
};
process.once("SIGINT", close);
process.once("SIGTERM", close);
