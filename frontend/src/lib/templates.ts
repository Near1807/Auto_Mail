export type Template = { id: string; name: string; description: string; html: string };

const wrap = (inner: string) => `<!doctype html>
<html lang="fr">
  <body style="margin:0;padding:0;background:#f4f1ec;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1ec;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;font-family:Arial,Helvetica,sans-serif;color:#222;">
${inner}
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>`;

export const TEMPLATES: Template[] = [
  {
    id: "simple",
    name: "Lettre simple",
    description: "Quelques paragraphes et une signature, sans décor.",
    html: `<p>Bonjour {prenom},</p>

<p>Je me permets de vous contacter au sujet de …</p>

<p>Pourriez-vous me dire :</p>
<ul>
  <li>si vos locaux sont disponibles du … au … ;</li>
  <li>le prix pour une quarantaine de personnes ;</li>
  <li>s'il y a une cuisine et des sanitaires sur place.</li>
</ul>

<p>Je reste joignable par téléphone si c'est plus simple.</p>

<p>Bien à vous,<br>
<strong>Votre nom</strong></p>`,
  },
  {
    id: "card",
    name: "Carte avec en-tête",
    description: "Bandeau coloré, corps centré, pied de page discret.",
    html: wrap(`            <tr>
              <td style="background:#e2552b;border-radius:12px 12px 0 0;padding:28px 32px;color:#fff;">
                <div style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;opacity:.85;">Unité Saint-Paul</div>
                <div style="font-size:24px;font-weight:bold;margin-top:6px;">Recherche d'un lieu de week-end</div>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 32px;font-size:15px;line-height:1.6;">
                <p style="margin:0 0 14px;">Bonjour {prenom},</p>
                <p style="margin:0 0 14px;">Votre message ici…</p>
                <p style="margin:0;">Bien à vous,<br><strong>Votre nom</strong></p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 32px 24px;font-size:12px;color:#8a8079;border-top:1px solid #eee;">
                Vous recevez ce message car votre établissement propose des locations.
              </td>
            </tr>`),
  },
  {
    id: "cta",
    name: "Annonce avec bouton",
    description: "Un message court et un bouton d'action.",
    html: wrap(`            <tr>
              <td style="padding:36px 32px 8px;font-size:22px;font-weight:bold;">Bonjour {prenom} 👋</td>
            </tr>
            <tr>
              <td style="padding:8px 32px 20px;font-size:15px;line-height:1.6;color:#444;">
                Une phrase qui explique pourquoi vous écrivez, et ce que vous attendez en retour.
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 32px;">
                <a href="https://example.com" style="display:inline-block;background:#e2552b;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:bold;">Répondre au sondage</a>
              </td>
            </tr>`),
  },
];
