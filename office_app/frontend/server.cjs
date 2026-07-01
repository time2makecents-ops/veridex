const fs = require("fs");
const https = require("https");
const path = require("path");

const next = require("next");

const port = Number(process.env.PORT || 3078);
const host = process.env.HOST || "0.0.0.0";
const appDir = __dirname;
const keyPath = path.join(appDir, "localhost+2-key.pem");
const certPath = path.join(appDir, "localhost+2.pem");

if (!fs.existsSync(keyPath) || !fs.existsSync(certPath)) {
  console.error(`Missing HTTPS cert files. Expected:\n- ${keyPath}\n- ${certPath}`);
  process.exit(1);
}

const app = next({ dev: false, dir: appDir });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  https
    .createServer(
      {
        key: fs.readFileSync(keyPath),
        cert: fs.readFileSync(certPath),
      },
      (req, res) => {
        handle(req, res);
      },
    )
    .listen(port, host, () => {
      console.log(`Veridex frontend HTTPS server listening on https://${host}:${port}`);
    });
});
