// Puts a password in front of a built site (preview only). Every HTML page is encrypted (AES-256-GCM, key from the
// password with PBKDF2-SHA256) and replaced by a small page that asks for the password and decrypts in the browser.
// After the first correct entry the key is kept for this browser tab only (sessionStorage), so other pages open
// without asking again. Style sheets, scripts and pictures stay unencrypted (they hold no text of the site).
//
// Usage:  node tools/protect.mjs <file-with-password> <built-site-folder> [more folders]
// Folders protected in one run share one key, so the password is asked only once for all of them.
// The password never goes into this repository. Needs Node 18 or newer, nothing else.

import { webcrypto as crypto } from "node:crypto";
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const [pwFile, ...dirs] = process.argv.slice(2);
if (!pwFile || dirs.length === 0) {
  console.error("Usage: node tools/protect.mjs <file-with-password> <built-site-folder> [more folders]");
  process.exit(1);
}
const password = readFileSync(pwFile, "utf8").trim();
if (password.length < 10) {
  console.error("Password too short (at least 10 characters).");
  process.exit(1);
}

const ITERATIONS = 250000;
const enc = new TextEncoder();
const b64 = (bytes) => Buffer.from(bytes).toString("base64");
const salt = crypto.getRandomValues(new Uint8Array(16));
const base = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
const raw = new Uint8Array(await crypto.subtle.deriveBits({ name: "PBKDF2", salt, iterations: ITERATIONS, hash: "SHA-256" }, base, 256));
const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt"]);

function htmlFiles(folder) {
  const out = [];
  for (const name of readdirSync(folder)) {
    const p = join(folder, name);
    if (statSync(p).isDirectory()) out.push(...htmlFiles(p));
    else if (name.endsWith(".html")) out.push(p);
  }
  return out;
}

const GATE = (iv, data) => `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>ICKM website preview</title>
<style>
:root { color-scheme: light dark; --bg: #f6f5f1; --card: #fff; --text: #182134; --muted: #586174; --line: #dcdfe6; --navy: #06295a; --amber: #dc7d05; }
@media (prefers-color-scheme: dark) { :root { --bg: #0a1022; --card: #101a31; --text: #e4e8ef; --muted: #9ba6b9; --line: #24304a; --navy: #eef2f8; --amber: #f5a13a; } }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 1.25rem; background: var(--bg); color: var(--text);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
main { width: 100%; max-width: 24rem; padding: 2rem; border-radius: 14px; background: var(--card); border: 1px solid var(--line); }
.mark { font-family: "Palatino Linotype", Palatino, Georgia, serif; font-weight: 700; font-size: 1.8rem; letter-spacing: 0.04em; color: var(--navy);
  display: inline-block; padding-bottom: 0.2rem; border-bottom: 3px solid var(--amber); }
p { color: var(--muted); line-height: 1.5; }
label { display: block; font-size: 0.9rem; margin: 1.25rem 0 0.4rem; }
input { width: 100%; font: inherit; padding: 0.7rem 0.8rem; border-radius: 10px; border: 1px solid var(--line); background: transparent; color: inherit; }
input:focus { outline: 3px solid var(--amber); outline-offset: 1px; }
button { margin-top: 1rem; width: 100%; font: inherit; font-weight: 600; padding: 0.75rem; border: 0; border-radius: 999px; background: #f5a13a; color: #1d1205; cursor: pointer; }
.msg { min-height: 1.5rem; margin: 0.75rem 0 0; color: #c0392b; }
</style>
</head>
<body style="visibility:hidden">
<main>
<span class="mark">ICKM</span>
<p>Preview of the new website of the International Conference on Knowledge Management. Please enter the password.</p>
<form id="f"><label for="pw">Password</label><input id="pw" type="password" autocomplete="current-password" required>
<button type="submit">Open the preview</button><p class="msg" id="m" role="alert"></p></form>
<noscript><p>Please switch on JavaScript to open the preview.</p></noscript>
</main>
<script type="application/octet-stream" id="enc" data-iv="${iv}">${data}</script>
<script>
(function () {
  var S = "${b64(salt)}", N = ${ITERATIONS};
  var d = document, el = d.getElementById("enc");
  var from64 = function (s) { return Uint8Array.from(atob(s), function (c) { return c.charCodeAt(0); }); };
  // Replace the whole page only once this small page has finished loading (otherwise browsers ignore document.open).
  var show = function (html) {
    var go = function () { d.open(); d.write(html); d.close(); };
    if (d.readyState === "complete") go(); else window.addEventListener("load", go);
  };
  var reveal = function () { d.body.style.visibility = "visible"; d.getElementById("pw").focus(); };
  if (!window.crypto || !crypto.subtle) { reveal(); d.getElementById("m").textContent = "This browser cannot open the preview."; return; }
  var open = function (raw) {
    return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]).then(function (k) {
      return crypto.subtle.decrypt({ name: "AES-GCM", iv: from64(el.dataset.iv) }, k, from64(el.textContent.trim()));
    }).then(function (buf) { return new TextDecoder().decode(buf); });
  };
  var saved = null;
  try { saved = sessionStorage.getItem("ickm-preview-key"); } catch (e) {}
  (saved ? open(from64(saved)) : Promise.reject()).then(show, function () {
    reveal();
    d.getElementById("f").addEventListener("submit", function (e) {
      e.preventDefault();
      var m = d.getElementById("m"); m.textContent = "";
      crypto.subtle.importKey("raw", new TextEncoder().encode(d.getElementById("pw").value), "PBKDF2", false, ["deriveBits"])
        .then(function (b) { return crypto.subtle.deriveBits({ name: "PBKDF2", salt: from64(S), iterations: N, hash: "SHA-256" }, b, 256); })
        .then(function (bits) {
          var raw = new Uint8Array(bits);
          return open(raw).then(function (html) {
            try { sessionStorage.setItem("ickm-preview-key", btoa(String.fromCharCode.apply(null, raw))); } catch (e) {}
            show(html);
          });
        })
        .catch(function () { m.textContent = "Wrong password."; });
    });
  });
})();
</script>
</body>
</html>
`;

let n = 0;
for (const file of dirs.flatMap(htmlFiles)) {
  const plain = readFileSync(file);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plain));
  writeFileSync(file, GATE(b64(iv), b64(data)), "utf8");
  n++;
}
console.log(`Protected ${n} pages in ${dirs.join(", ")}`);
