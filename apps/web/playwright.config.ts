import { defineConfig, devices } from "@playwright/test";
import chromium, { inflate } from "@sparticuz/chromium";
import { fileURLToPath, URL } from "node:url";

chromium.setGraphicsMode = false;
const executablePath = await inflate(
  fileURLToPath(new URL("./node_modules/@sparticuz/chromium/bin/chromium.br", import.meta.url)),
);
const browserArgs = chromium.args.filter(
  (argument) =>
    !["--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--in-process-gpu"].includes(
      argument,
    ),
);

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath,
      args: [...browserArgs, "--disable-gpu", "--disable-software-rasterizer", "--use-gl=disabled"],
      env: {
        ...process.env,
        HOME: "/tmp",
        XDG_CACHE_HOME: "/tmp/.cache",
        FONTCONFIG_PATH: "/etc/fonts",
      },
    },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "npm run build && npm run start -- --hostname 127.0.0.1",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
