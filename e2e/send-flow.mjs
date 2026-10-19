// Test de bout en bout de l'écran d'envoi, en mode démo (faux Gmail : rien ne part).
//
// Reproduit le bug « page blanche à la fin d'un envoi » : pour chaque scénario
// (envoi complet, avec erreurs, pause/reprise, annulation, 0 destinataire), on lance
// l'envoi depuis l'interface puis on vérifie que :
//   - aucune erreur JavaScript n'a eu lieu ;
//   - le récapitulatif s'affiche, puis l'appli revient sur la page principale ;
//   - la navigation par la sidebar fonctionne encore.
//
// Deux façons de le lancer :
//   CDP_URL=http://127.0.0.1:9222 node send-flow.mjs   s'attache à la fenêtre AutoMail.exe (WebView2)
//   APP_URL=http://127.0.0.1:8765 node send-flow.mjs   ouvre l'appli dans Chromium (back lancé avec AUTOMAIL_DEMO=1)
import { chromium } from "playwright-core";

const SCENARIOS = {
  complet: { raw: "email\tprenom\nann@exemple.be\tAnn\nbob@exemple.be\tBob\ncid@exemple.be\tCid", expect: { sent: 3, errors: 0 } },
  erreurs: { raw: "ann@exemple.be\nbounce@exemple.be\nbounce2@exemple.be", expect: { sent: 1, errors: 2 } },
  pause: { raw: "a1@exemple.be a2@exemple.be a3@exemple.be a4@exemple.be", delay: 1, pause: true, expect: { sent: 4, errors: 0 } },
  annulation: { raw: Array.from({ length: 8 }, (_, i) => `x${i}@exemple.be`).join("\n"), delay: 2, cancel: true, expect: { cancelled: true } },
  zero: { raw: "ann@exemple.be", alreadySent: true, expect: { nothing: true } },
  plantage: { crash: true },
};

const wanted = (process.env.SCENARIOS || Object.keys(SCENARIOS).join(",")).split(",");
const failures = [];
const jsErrors = [];

async function open() {
  if (process.env.CDP_URL) {
    const browser = await chromium.connectOverCDP(process.env.CDP_URL);
    const page = browser.contexts()[0].pages()[0];
    return { browser, page, close: async () => {} };
  }
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 820 } })).newPage();
  if (process.env.SIMULATE_WEBVIEW2 !== "0") {
    // Comme le WebView2 récent de Windows : scrollIntoView() renvoie une Promise.
    await page.addInitScript(() => {
      const original = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function (...args) {
        const result = original.apply(this, args);
        return result instanceof Promise ? result : Promise.resolve();
      };
    });
  }
  await page.goto(process.env.APP_URL || "http://127.0.0.1:8765");
  return { browser, page, close: () => browser.close() };
}

const { page, close } = await open();
// Diagnostic : ce que renvoie scrollIntoView() dans ce navigateur (Promise dans le WebView2 récent).
console.log("navigateur :", await page.evaluate(() => navigator.userAgent));
console.log("scrollIntoView() renvoie :", await page.evaluate(() => {
  const r = document.body.scrollIntoView({ block: "nearest" });
  return r instanceof Promise ? "une Promise" : String(r);
}));
page.on("pageerror", (e) => jsErrors.push(String(e.stack || e)));
// Une réponse HTTP 4xx attendue (ex. envoi refusé) n'est pas une erreur JavaScript.
page.on("console", (m) => m.type() === "error" && !m.text().startsWith("Failed to load resource") && jsErrors.push(`console: ${m.text()}`));
page.setDefaultTimeout(15000);

const api = (method, url, body) =>
  page.evaluate(
    async ([m, u, b]) => {
      const r = await fetch(u, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined });
      return { status: r.status, data: r.status === 204 ? null : await r.json() };
    },
    [method, url, body],
  );
const sidebar = (name) => page.locator("aside").getByRole("button", { name, exact: true });
const heading = (text) => page.locator("main h1", { hasText: new RegExp(`^${text}$`) });

async function checkNavigation(label) {
  for (const [nav, title] of [["Suivi", "Suivi"], ["Destinataires", "Destinataires"], ["Envoi", "Envoi"], ["Campagnes", "Campagnes"]]) {
    await sidebar(nav).click();
    await heading(title).waitFor({ state: "visible", timeout: 5000 }).catch(() => {
      throw new Error(`${label} : la sidebar n'ouvre pas « ${nav} »`);
    });
  }
}

async function stopRunningJob() {
  // Un scénario précédent en échec peut avoir laissé un envoi actif.
  const current = (await api("GET", "/api/jobs/current")).data;
  if (current && ["running", "paused", "pending"].includes(current.state)) {
    await api("POST", `/api/jobs/${current.id}/cancel`);
    for (let i = 0; i < 50 && ["running", "paused", "pending"].includes((await api("GET", "/api/jobs/current")).data?.state); i++) await page.waitForTimeout(200);
  }
}

async function crashScenario() {
  const errorsBefore = jsErrors.length;
  await page.evaluate(() => localStorage.setItem("automail-page", "campaigns"));
  await page.reload();
  await heading("Campagnes").waitFor();
  await page.evaluate(() => { window.__automailCrash = "settings"; });
  await sidebar("Réglages").click();
  await page.getByText("Cet écran a rencontré un problème").waitFor().catch(() => { throw new Error("plantage : pas de message d'erreur lisible"); });
  if (!(await sidebar("Campagnes").isVisible())) throw new Error("plantage : la sidebar a disparu");
  await page.evaluate(() => { window.__automailCrash = undefined; });
  await page.getByRole("button", { name: "Retour à l'accueil" }).click();
  await heading("Campagnes").waitFor({ timeout: 5000 }).catch(() => { throw new Error("plantage : « Retour à l'accueil » ne ramène pas aux campagnes"); });
  await checkNavigation("plantage");
  if (process.env.LOG_FILE) {
    const { readFileSync } = await import("node:fs");
    await page.waitForTimeout(500);
    const log = readFileSync(process.env.LOG_FILE, "utf8");
    if (!log.includes("Plantage de test sur l'écran « settings »")) throw new Error(`plantage : l'erreur n'est pas dans ${process.env.LOG_FILE}`);
  }
  // L'erreur volontaire est attendue : on la retire des erreurs JavaScript « inattendues ».
  jsErrors.splice(errorsBefore);
}

async function run(name, s) {
  await stopRunningJob();
  if (s.crash) return crashScenario();
  const errorsBefore = jsErrors.length;
  await api("PUT", "/api/settings", { email: "demo@gmail.com", display_name: "Démo", delay_seconds: s.delay ?? 0 });
  await api("PUT", "/api/account/password", { password: "demo" });
  const { data: c } = await api("POST", "/api/campaigns", { name: `E2E ${name} ${Date.now()}` });
  await api("PUT", `/api/campaigns/${c.id}/draft`, { subject: "Bonjour {prenom}", mode: "text", text: "Message de test {prenom}", recipients_raw: s.raw });
  if (s.alreadySent) {
    // Tout est déjà « Envoyé » dans le suivi : il ne reste personne à qui écrire.
    await api("PUT", `/api/campaigns/${c.id}/draft`, { recipients_raw: s.raw });
    await api("POST", `/api/campaigns/${c.id}/send`);
    for (let i = 0; i < 50 && (await api("GET", "/api/jobs/current")).data?.state !== "done"; i++) await page.waitForTimeout(200);
  }

  await page.evaluate((id) => { localStorage.setItem("automail-campaign", id); localStorage.setItem("automail-page", "campaigns"); }, c.id);
  await page.reload();
  await heading("Campagnes").waitFor();
  await sidebar("Envoi").click();
  await heading("Envoi").waitFor();

  if (s.expect.nothing) {
    const launch = page.getByRole("button", { name: "Lancer l'envoi", exact: true });
    if (!(await launch.isDisabled())) throw new Error("zero : « Lancer l'envoi » devrait être désactivé sans destinataire");
    const refused = await api("POST", `/api/campaigns/${c.id}/send`);
    if (refused.status !== 400) throw new Error(`zero : l'API devrait refuser l'envoi (reçu ${refused.status})`);
    await checkNavigation(name);
  } else {
    await page.getByRole("button", { name: "Lancer l'envoi", exact: true }).click();
    await page.getByRole("button", { name: /^Envoyer \d/ }).click();
    if (s.pause) {
      await page.getByRole("button", { name: "Pause", exact: true }).click();
      await page.getByText("En pause", { exact: true }).first().waitFor();
      await page.waitForTimeout(1500);
      await page.getByRole("button", { name: "Reprendre", exact: true }).click();
    }
    if (s.cancel) {
      await page.waitForTimeout(2500);
      await page.getByRole("button", { name: "Annuler", exact: true }).click();
    }

    // Fin d'envoi : récapitulatif (toast) puis retour automatique à la page principale.
    const toast = page.locator("[data-sonner-toast]", { hasText: /Envoi (terminé|annulé)/ });
    await toast.first().waitFor({ timeout: 60000 }).catch(() => { throw new Error(`${name} : pas de récapitulatif de fin d'envoi`); });
    const text = (await toast.first().innerText()).replace(/\s+/g, " ");
    if (s.expect.sent !== undefined && !text.includes(`${s.expect.sent} envoyé`)) throw new Error(`${name} : récapitulatif inattendu « ${text} »`);
    if (s.expect.errors !== undefined && !text.includes(`${s.expect.errors} erreur`)) throw new Error(`${name} : récapitulatif inattendu « ${text} »`);
    if (s.expect.cancelled && !text.includes("annulé")) throw new Error(`${name} : récapitulatif inattendu « ${text} »`);
    await heading("Campagnes").waitFor({ timeout: 10000 }).catch(() => { throw new Error(`${name} : pas de retour à la page principale`); });
    await checkNavigation(name);
  }

  const rootSize = await page.evaluate(() => document.getElementById("root")?.innerHTML.length ?? 0);
  if (rootSize < 1000) throw new Error(`${name} : page blanche (#root presque vide)`);
  if (jsErrors.length > errorsBefore) throw new Error(`${name} : erreur JavaScript\n${jsErrors.slice(errorsBefore).join("\n")}`);
}

for (const name of wanted) {
  try {
    await run(name, SCENARIOS[name]);
    console.log(`ok   ${name}`);
  } catch (error) {
    failures.push(name);
    console.log(`FAIL ${name}\n     ${String(error.message || error).replace(/\n/g, "\n     ")}`);
    await page.screenshot({ path: `echec-${name}.png` }).catch(() => {});
  }
}
if (jsErrors.length) console.log("\nErreurs JavaScript vues :\n" + jsErrors.join("\n"));
await close();
process.exit(failures.length ? 1 : 0);
