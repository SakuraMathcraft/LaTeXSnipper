import { createReadStream, readFileSync, readdirSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, loadEnv, type Plugin } from "vite";

const projectRoot = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(projectRoot, "../..");
const applicationRoot = resolve(projectRoot, "src");
const mathLiveRoot = resolve(repositoryRoot, "src/assets/mathlive/vendor");
const mathLiveFontsRoot = resolve(mathLiveRoot, "fonts");
const mathLiveModulePath = resolve(mathLiveRoot, "mathlive.min.mjs");
const mathJaxRoot = resolve(repositoryRoot, "src/assets/MathJax-3.2.2");
const taskpaneAssetsRoot = resolve(applicationRoot, "assets");

interface BundledAsset {
  readonly route: string;
  readonly sourcePath: string;
  readonly contentType: string;
}

function bundledAssetsPlugins(): Plugin[] {
  const fontAssets = readdirSync(mathLiveFontsRoot)
    .filter((name) => name.endsWith(".woff2"))
    .sort()
    .map<BundledAsset>((name) => ({
      route: `/assets/mathlive/fonts/${name}`,
      sourcePath: resolve(mathLiveFontsRoot, name),
      contentType: "font/woff2",
    }));

  const legalAssets: BundledAsset[] = [
    {
      route: "/assets/licenses/mathlive.LICENSE.txt",
      sourcePath: resolve(mathLiveRoot, "mathlive.LICENSE.txt"),
      contentType: "text/plain; charset=utf-8",
    },
    {
      route: "/assets/licenses/mathjax.LICENSE.txt",
      sourcePath: resolve(mathJaxRoot, "LICENSE"),
      contentType: "text/plain; charset=utf-8",
    },
  ];

  const mathJaxAssets: BundledAsset[] = [
    {
      route: "/assets/mathjax/es5/tex-mml-svg.js",
      sourcePath: resolve(mathJaxRoot, "es5/tex-mml-svg.js"),
      contentType: "text/javascript; charset=utf-8",
    },
    {
      route: "/assets/mathjax/es5/output/svg/fonts/tex.js",
      sourcePath: resolve(mathJaxRoot, "es5/output/svg/fonts/tex.js"),
      contentType: "text/javascript; charset=utf-8",
    },
    {
      route: "/assets/mathjax/es5/input/tex/extensions/bbox.js",
      sourcePath: resolve(mathJaxRoot, "es5/input/tex/extensions/bbox.js"),
      contentType: "text/javascript; charset=utf-8",
    },
  ];

  const manifestOnlyIcons: BundledAsset[] = ["icon-16.png", "icon-64.png"].map(
    (name) => ({
      route: `/assets/${name}`,
      sourcePath: resolve(taskpaneAssetsRoot, name),
      contentType: "image/png",
    }),
  );

  const assets = [...fontAssets, ...mathJaxAssets, ...manifestOnlyIcons, ...legalAssets];
  const routes = new Map(assets.map((asset) => [asset.route, asset]));

  const servePlugin: Plugin = {
    name: "latexsnipper-bundled-assets-serve",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url ?? "/", "https://localhost").pathname;
        const asset = routes.get(pathname);
        if (!asset) {
          next();
          return;
        }

        if (request.method !== "GET" && request.method !== "HEAD") {
          response.statusCode = 405;
          response.setHeader("Allow", "GET, HEAD");
          response.end();
          return;
        }

        response.statusCode = 200;
        response.setHeader("Content-Type", asset.contentType);
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("X-Content-Type-Options", "nosniff");
        if (request.method === "HEAD") {
          response.end();
          return;
        }
        createReadStream(asset.sourcePath).pipe(response);
      });
    },
  };

  const buildPlugin: Plugin = {
    name: "latexsnipper-bundled-assets-build",
    apply: "build",
    buildStart() {
      for (const asset of assets) {
        this.emitFile({
          type: "asset",
          fileName: asset.route.slice(1),
          source: readFileSync(asset.sourcePath),
        });
      }
    },
  };

  return [servePlugin, buildPlugin];
}

function mathLiveRuntimePolicyPlugin(): Plugin {
  const remoteComputeEngineHint =
    'import "https://esm.run/@cortex-js/' + "compute" + '-engine"';

  return {
    name: "latexsnipper-mathlive-runtime-policy",
    enforce: "pre",
    transform(source, id) {
      if (id.split("?", 1)[0] !== mathLiveModulePath) {
        return null;
      }
      return {
        code: source.replaceAll(
          remoteComputeEngineHint,
          "Compute Engine is intentionally unavailable in this add-in.",
        ),
        map: null,
      };
    },
  };
}

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, projectRoot, "");
  const agentOrigin = environment.LATEXSNIPPER_AGENT_ORIGIN?.trim();

  if (agentOrigin) {
    const parsedOrigin = new URL(agentOrigin);
    if (parsedOrigin.protocol !== "https:" || parsedOrigin.hostname !== "localhost") {
      throw new Error("LATEXSNIPPER_AGENT_ORIGIN must use trusted https://localhost.");
    }
  }

  return {
    root: applicationRoot,
    publicDir: false,
    base: "./",
    plugins: [mathLiveRuntimePolicyPlugin(), ...bundledAssetsPlugins()],
    server: {
      host: "localhost",
      port: 3000,
      strictPort: true,
      fs: {
        allow: [repositoryRoot],
      },
      headers: {
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
      },
      ...(agentOrigin
        ? {
            proxy: {
              "/v1": {
                target: agentOrigin,
                changeOrigin: false,
                secure: true,
              },
            },
          }
        : {}),
    },
    build: {
      outDir: resolve(projectRoot, ".dev/taskpane"),
      emptyOutDir: true,
      minify: false,
      sourcemap: true,
      rollupOptions: {
        input: {
          taskpane: resolve(applicationRoot, "taskpane.html"),
          support: resolve(applicationRoot, "support.html"),
        },
        output: {
          assetFileNames(assetInfo) {
            const originalName = basename(assetInfo.originalFileNames[0] ?? "");
            if (/^icon-(32|80)\.png$/.test(originalName)) {
              return `assets/${originalName}`;
            }
            return "assets/[name]-[hash][extname]";
          },
        },
      },
    },
  };
});
