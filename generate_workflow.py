#!/usr/bin/env python3
"""
Générateur du workflow n8n Newsletter LIBRE v2.0
Applique toutes les corrections et améliorations planifiées.
"""
import json

# ============================================================
# JAVASCRIPT CODE BLOCKS
# ============================================================

CODE_NORMALISATION = r"""let tavily_actu_resultats = [];
let tavily_actu_images   = [];
let tavily_coaching      = { resultats: [], images: [] };
let invite_rows          = [];
let ong_rows             = [];

function compresser(payload) {
  const resultats = (payload.resultats || [])
    .slice(0, 3)
    .map(r => ({
      title:   r.title   || '',
      url:     r.url     || '',
      content: (r.content || r.snippet || '').slice(0, 1500)
    }));
  const images = (payload.images || [])
    .filter(img => {
      const url = typeof img === 'string' ? img : (img.url || '');
      return url.length > 0
        && !url.endsWith('.ico')
        && !url.endsWith('.svg')
        && !url.includes('favicon')
        && !url.includes('logo')
        && !url.includes('gravatar')
        && !url.includes('avatar')
        && (url.includes('.jpg') || url.includes('.jpeg')
            || url.includes('.png') || url.includes('.webp')
            || url.includes('.gif'));
    })
    .slice(0, 3);
  return { resultats, images };
}

// Le coaching se distingue par ses mots-clés de requête
const COACHING_KEYWORDS = ['réussir', 'gestion', 'entrepreneur', 'afrique'];

for (const item of items) {
  const d = item.json;
  if (d.results !== undefined && d.query !== undefined) {
    const payload = {
      resultats: Array.isArray(d.results) ? d.results : [],
      images:    Array.isArray(d.images)  ? d.images  : []
    };
    const q = (d.query || '').toLowerCase();
    const is_coaching = COACHING_KEYWORDS.some(k => q.includes(k));
    if (is_coaching) {
      tavily_coaching = compresser(payload);
    } else {
      const compressed = compresser(payload);
      tavily_actu_resultats.push(...compressed.resultats);
      tavily_actu_images.push(...compressed.images);
    }
  } else if (d.frein_invisible !== undefined) {
    invite_rows.push(d);
  } else if (d.contenu !== undefined && d.created_at !== undefined) {
    ong_rows.push(d);
  }
}

const tavily_actu = {
  resultats: tavily_actu_resultats.slice(0, 9),
  images:    tavily_actu_images.slice(0, 6)
};

// Candidats images : sources actu en priorité, coaching en fallback
const images_candidates = tavily_actu.images.length > 0
  ? tavily_actu.images
  : tavily_coaching.images;

const invite = (invite_rows.length > 0) ? {
  disponible:              true,
  nom:                     invite_rows[0].nom                     || null,
  fonction:                invite_rows[0].fonction                || null,
  frein_invisible:         invite_rows[0].frein_invisible         || null,
  levier_acceleration:     invite_rows[0].levier_acceleration     || null,
  partage_experience:      invite_rows[0].partage_experience      || null,
  opportunite_sectorielle: invite_rows[0].opportunite_sectorielle || null,
  engagement_tinga:        invite_rows[0].engagement_tinga        || null,
  consentement:            invite_rows[0].consentement            || null
} : { disponible: false };

let ong = { disponible: false };
if (ong_rows.length > 0) {
  const age_jours = (Date.now() - new Date(ong_rows[0].created_at)) / (1000 * 60 * 60 * 24);
  ong = age_jours <= 14
    ? { disponible: true,  contenu: ong_rows[0].contenu, date: ong_rows[0].created_at }
    : { disponible: false, raison: 'contenu_trop_ancien' };
}

return [{
  json: {
    semaine:         new Date().toISOString().split('T')[0],
    images_candidates,
    sources:         { tavily_actu, tavily_coaching },
    rubriques_optionnelles: { invite, vie_tinga: ong }
  }
}];"""

CODE_SELECTION_IMAGE = r"""// Vérifie les candidats via HEAD et retourne la première URL accessible.
// En cas d'échec total, utilise le fallback Supabase Storage.
const FALLBACK_IMAGE = 'SUPABASE_CDN_BANNIERE_URL_ICI';
const candidates = $input.first().json.images_candidates || [];

let image_validee = FALLBACK_IMAGE;

for (const img_brut of candidates) {
  const url = typeof img_brut === 'string' ? img_brut : (img_brut.url || '');
  if (!url) continue;
  try {
    const resp = await this.helpers.httpRequest({
      method: 'HEAD',
      url,
      timeout: 4000,
      returnFullResponse: true
    });
    if (resp.statusCode >= 200 && resp.statusCode < 400) {
      image_validee = url;
      break;
    }
  } catch (e) {
    // Image inaccessible — essayer la suivante
  }
}

return [{ json: { ...$input.first().json, image_validee } }];"""

CODE_EXTRACTION_FAITS = r"""// Extrait chiffres, montants, institutions et dates des sources Tavily
// pour forcer l'agent Brief à produire des ancres réelles.
const data     = $input.first().json;
const all_text = JSON.stringify(data.sources || {});

const unique = arr => [...new Set(arr)];

const montants = unique(
  [...all_text.matchAll(/(\d[\d\s]{0,8}(?:[ \s]000)?\s*(?:FCFA|francs?\s+CFA|F\.?CFA))/gi)]
    .map(m => m[1].replace(/\s+/g, ' ').trim())
).slice(0, 8);

const pourcentages = unique(
  [...all_text.matchAll(/(\d+[,.]?\d*\s*%)/g)]
    .map(m => m[1].trim())
).slice(0, 8);

const dates_detectees = unique(
  [...all_text.matchAll(/\b(\d{1,2}(?:er)?\s+(?:janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)\s+\d{4})\b/gi)]
    .map(m => m[1])
).slice(0, 5);

const institutions = unique(
  [...all_text.matchAll(/\b(BGFIBank|BCEG|BEAC|CNAMGS|DGI|CNSS|SEEG|OPRAG|GSEZ|Okoum[eé]\s+Capital|Gabon\s+Oil\s+Company|ANGTI|ANPI|AGASA)\b/g)]
    .map(m => m[1])
);

return [{
  json: {
    ...data,
    faits_extraits: { montants, pourcentages, dates_detectees, institutions }
  }
}];"""

CODE_PREPARER_PROMPT = r"""try {
  const raw_brief = items[0].json.output
                 || items[0].json.text
                 || JSON.stringify(items[0].json);

  const first_brace = raw_brief.indexOf('{');
  const last_brace  = raw_brief.lastIndexOf('}');

  if (first_brace === -1 || last_brace === -1) {
    return [{
      json: {
        erreur:  true,
        message: "Aucun bloc JSON trouvé dans la sortie de l'Éditorialiste",
        raw:     raw_brief
      }
    }];
  }

  const clean_brief = raw_brief.substring(first_brace, last_brace + 1);
  const brief = JSON.parse(clean_brief);

  const faits_actu     = brief.actu_impact?.faits    || [];
  const faits_bloquant = brief.point_bloquant?.faits || [];
  const faits_conseil  = brief.conseil?.faits        || [];

  const actu_ok     = brief.actu_impact    && !brief.actu_impact.matiere_insuffisante    && faits_actu.length > 0;
  const bloquant_ok = brief.point_bloquant && !brief.point_bloquant.matiere_insuffisante && faits_bloquant.length > 0;
  const conseil_ok  = brief.conseil        && !brief.conseil.matiere_insuffisante        && faits_conseil.length > 0;

  const avec_invite    = brief.rubriques_optionnelles?.invite?.disponible    === true
                      || brief.invite?.disponible    === true;
  const avec_vie_tinga = brief.rubriques_optionnelles?.vie_tinga?.disponible === true
                      || brief.vie_tinga?.disponible === true;

  const nb_optionnelles = (avec_invite ? 1 : 0) + (avec_vie_tinga ? 1 : 0);

  let longueurs = {};
  if (nb_optionnelles === 0) {
    longueurs = { actu_impact: 500, point_bloquant: 500, conseil: 250 };
  } else if (nb_optionnelles === 1 && avec_vie_tinga) {
    longueurs = { actu_impact: 500, point_bloquant: 500, conseil: 250, vie_tinga: 150 };
  } else if (nb_optionnelles === 1 && avec_invite) {
    longueurs = { actu_impact: 500, point_bloquant: 500, conseil: 250, invite: 500 };
  } else {
    longueurs = { actu_impact: 500, point_bloquant: 500, conseil: 250, invite: 500, vie_tinga: 500 };
  }

  const angle_edito = actu_ok && brief.actu_impact.angle
    ? brief.actu_impact.angle
    : "La réalité des travailleurs indépendants gabonais cette semaine";

  const ACTION_TEMPLATE = `
ACTION DE LA SEMAINE (OBLIGATOIRE) :
1 phrase à l'impératif. Délai précis (ex: "Avant vendredi"). Coût : zéro franc.
Exemple : "Avant vendredi, télécharge le formulaire DGI 2026 et vérifie que ton NIF est actif."
`;

  let instructions = `
RUBRIQUE 0 — ÉDITO DU PRÉSIDENT (TOUJOURS OBLIGATOIRE)
Inspiration : ${angle_edito}
Tension à adresser : ${brief.actu_impact?.tension || 'Le doute du lecteur ce lundi matin'}
Ton : personnel, direct, habité. Pas institutionnel.
Pas de "chers membres", pas de formule de politesse.
Longueur : 100 à 200 mots maximum.
Signature obligatoire : — Elijah Parfait ONDO OYONO,
Président de TINGA, les travailleurs indépendants du Gabon
`;

  if (actu_ok) {
    instructions += `
RUBRIQUE 1 — ACTU IMPACT (OBLIGATOIRE)
Angle : ${brief.actu_impact.angle}
Tension : ${brief.actu_impact.tension || ''}
Analyse : ${brief.actu_impact.analyse || ''}
Faits sourcés :
${faits_actu.map(f => `- ${f.texte} (${f.url})`).join('\n')}
Longueur : ${longueurs.actu_impact} mots.
${ACTION_TEMPLATE}
`;
  }

  if (bloquant_ok) {
    instructions += `
RUBRIQUE 2 — POINT BLOQUANT (OBLIGATOIRE)
Angle : ${brief.point_bloquant.angle}
Tension : ${brief.point_bloquant.tension || ''}
Analyse : ${brief.point_bloquant.analyse || ''}
Faits sourcés :
${faits_bloquant.map(f => `- ${f.texte} (${f.url})`).join('\n')}
Longueur : ${longueurs.point_bloquant} mots.
${ACTION_TEMPLATE}
`;
  }

  if (conseil_ok) {
    instructions += `
RUBRIQUE 3 — CONSEIL (OBLIGATOIRE)
Angle : ${brief.conseil.angle}
Tension : ${brief.conseil.tension || ''}
Analyse : ${brief.conseil.analyse || ''}
Faits sourcés :
${faits_conseil.map(f => `- ${f.texte} (${f.url})`).join('\n')}
Longueur : ${longueurs.conseil} mots.
${ACTION_TEMPLATE}
`;
  }

  if (avec_invite) {
    const inv = brief.invite || brief.rubriques_optionnelles?.invite;
    instructions += `
RUBRIQUE 4 — L'INVITÉ DU MOIS (OPTIONNELLE)
Nom : ${inv.nom || ''}
Fonction : ${inv.fonction || ''}
Frein invisible : ${inv.frein_invisible || ''}
Levier accélération : ${inv.levier_acceleration || ''}
Longueur : ${longueurs.invite} mots.
`;
  }

  if (avec_vie_tinga) {
    const ong = brief.vie_tinga || brief.rubriques_optionnelles?.vie_tinga;
    instructions += `
RUBRIQUE 5 — VIE DE TINGA (OPTIONNELLE)
Contenu brut : ${ong.contenu || ''}
Longueur : ${longueurs.vie_tinga} mots.
`;
  }

  const rubriques_actives = ['edito'];
  if (actu_ok)        rubriques_actives.push('actu_impact');
  if (bloquant_ok)    rubriques_actives.push('point_bloquant');
  if (conseil_ok)     rubriques_actives.push('conseil');
  if (avec_invite)    rubriques_actives.push('invite');
  if (avec_vie_tinga) rubriques_actives.push('vie_tinga');

  const prompt_redacteur = `
Voici le brief éditorial de la newsletter LIBRE
pour la semaine du ${brief.semaine}.

RUBRIQUES À RÉDIGER OBLIGATOIREMENT :
${rubriques_actives.join(', ')}

Tu rédiges UNIQUEMENT ces rubriques dans la voix
de TINGA, à partir des faits et analyses fournis.

${instructions}

RAPPEL : Produis un JSON strict.
Aucun texte avant ou après.
`;

  return [{
    json: {
      prompt_redacteur,
      semaine:            brief.semaine,
      image_selectionnee: brief.image_selectionnee || null,
      rubriques_actives,
      longueurs
    }
  }];

} catch(e) {
  return [{
    json: {
      erreur:  true,
      message: "Erreur dans Préparer Prompt Rédaction : " + e.message,
      stack:   e.stack
    }
  }];
}"""

CODE_CORRECTION_JSON = r"""let raw = items[0].json.output
        || items[0].json.text
        || items[0].json.message?.content
        || JSON.stringify(items[0].json);

const first_brace = raw.indexOf('{');
const last_brace  = raw.lastIndexOf('}');

if (first_brace === -1 || last_brace === -1) {
  return [{
    json: {
      erreur:  true,
      message: "Aucun bloc JSON trouvé dans la sortie du Rédacteur",
      raw,
      semaine: items[0].json.semaine || null
    }
  }];
}

let parsed;
try {
  parsed = JSON.parse(raw.substring(first_brace, last_brace + 1));
} catch(e) {
  return [{
    json: {
      erreur:  true,
      message: "JSON du Rédacteur irréparable : " + e.message,
      raw,
      semaine: items[0].json.semaine || null
    }
  }];
}

const rubriques = parsed.rubriques || {};

if (!rubriques.edito?.corps) {
  return [{
    json: {
      erreur:  true,
      message: "Édito manquant ou vide — rubrique obligatoire",
      raw,
      semaine: parsed.semaine || null
    }
  }];
}

// Récupération depuis les nœuds amont (fix : items[0] ne porte pas ces données)
const prep              = $('Préparer Prompt Rédaction').first().json;
const rubriques_actives = prep.rubriques_actives || [];
const image_selectionnee = $('Sélection Image Fiable').first().json.image_validee
                        || prep.image_selectionnee
                        || null;

const avertissements = [];
for (const r of ['actu_impact', 'point_bloquant', 'conseil']) {
  if (rubriques_actives.includes(r) && !rubriques[r]?.corps) {
    avertissements.push(`${r} attendu mais absent`);
  }
}

return [{
  json: {
    erreur:          false,
    avertissements:  avertissements.length > 0 ? avertissements : null,
    semaine:         parsed.semaine,
    image_selectionnee,
    rubriques_actives,
    rubriques:       parsed.rubriques
  }
}];"""

CODE_GENERER_HTML = r"""// LIBRE — Nœud "Générer HTML Newsletter" v2.0
// Design éditorial premium TINGA — CSS inline email-safe

const data          = items[0].json;
const r             = data.rubriques;
const image_header  = data.image_selectionnee || null;

// Placeholders configurables
const PHOTO_PRESIDENT  = 'PHOTO_PRESIDENT_URL';
const TALLY_LINK       = 'TALLY_FEEDBACK_URL';
const UNSUBSCRIBE_LINK = 'UNSUBSCRIBE_URL';
const MEMBRE_COUNT     = '847';

if (!r || !r.edito) {
  throw new Error('Données rubriques manquantes ou malformées');
}

// Numéro de newsletter (N°001 = semaine du 2026-01-05)
const NEWSLETTER_START  = new Date('2026-01-05');
const current_date      = new Date(data.semaine || new Date());
const weeks_elapsed     = Math.max(0, Math.floor((current_date - NEWSLETTER_START) / (7 * 24 * 60 * 60 * 1000)));
const numero            = String(weeks_elapsed + 1).padStart(3, '0');

// Date formatée en français
const date_obj      = new Date(data.semaine || new Date());
const date_formatee = date_obj.toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' });

// Pull quote : première phrase substantielle de l'édito
const pq_match  = (r.edito.corps || '').match(/[^.!?\n]{20,}[.!?]/);
const pull_quote = pq_match ? pq_match[0].trim() : '';

// ============================================================
// RUBRIQUE BUILDER — fond coloré + badge + action_semaine
// ============================================================
function rubrique(couleur_accent, bg_color, label_badge, titre, corps, action_semaine) {
  const action_html = action_semaine ? `
        <tr>
          <td style="padding-top: 16px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="
                  background-color: #FDFCFB;
                  border-left: 3px solid ${couleur_accent};
                  padding: 10px 14px;
                  font-family: 'Courier New', Courier, monospace;
                  font-size: 12px;
                  color: #1A1A1A;
                  line-height: 1.6;
                ">&#8594; ${action_semaine}</td>
              </tr>
            </table>
          </td>
        </tr>` : '';

  return `
  <tr>
    <td style="background-color: ${bg_color}; padding: 24px 32px 28px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="padding-bottom: 10px;">
            <span style="
              display: inline-block;
              background-color: ${couleur_accent};
              color: #FFFFFF;
              font-family: 'Courier New', Courier, monospace;
              font-size: 10px;
              font-weight: 700;
              letter-spacing: 2px;
              text-transform: uppercase;
              padding: 4px 10px;
              border-radius: 2px;
            ">${label_badge}</span>
          </td>
        </tr>
        <tr>
          <td style="
            font-family: Georgia, 'Times New Roman', serif;
            font-size: 18px;
            font-weight: 700;
            color: #1A1A1A;
            line-height: 1.3;
            padding-bottom: 10px;
          ">${titre || ''}</td>
        </tr>
        <tr>
          <td style="
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-size: 15px;
            color: #4A4A4A;
            line-height: 1.75;
          ">${corps || ''}</td>
        </tr>
        ${action_html}
      </table>
    </td>
  </tr>
  <tr>
    <td style="padding: 0;"><hr style="border: none; border-top: 1px solid #E8E2D9; margin: 0;" /></td>
  </tr>`;
}

// Rubriques dynamiques avec palettes distinctes
let rubriques_html = '';
if (r.actu_impact)                 rubriques_html += rubrique('#1B4332', '#EDF5F0', 'Actualité impact',    r.actu_impact.titre,    r.actu_impact.corps,    r.actu_impact.action_semaine);
if (r.point_bloquant)              rubriques_html += rubrique('#7C2D12', '#FDF0EC', 'Point bloquant',      r.point_bloquant.titre, r.point_bloquant.corps, r.point_bloquant.action_semaine);
if (r.conseil)                     rubriques_html += rubrique('#1C3A6E', '#EEF2F9', 'Conseil de la semaine', r.conseil.titre,      r.conseil.corps,        r.conseil.action_semaine);
if (r.invite   && r.invite.corps)  rubriques_html += rubrique('#5B2D8E', '#F5EFF9', "L'invité du mois",   r.invite.titre,         r.invite.corps,         null);
if (r.vie_tinga && r.vie_tinga.corps) rubriques_html += rubrique('#C9943A', '#FDF6E9', 'Vie de TINGA',    r.vie_tinga.titre,      r.vie_tinga.corps,      null);

// Image header sécurisée
const image_html = image_header
  ? `<tr><td style="padding: 0; line-height: 0; font-size: 0;">
      <img src="${image_header}" alt="Image de la semaine" width="600"
           style="display: block; width: 100%; max-width: 600px; height: 220px; object-fit: cover;" />
    </td></tr>`
  : '';

// Pull quote HTML
const pull_quote_html = pull_quote
  ? `<tr>
      <td style="padding: 20px 32px 0 32px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="
              border-left: 4px solid #C9943A;
              padding: 8px 0 8px 16px;
              font-family: Georgia, 'Times New Roman', serif;
              font-size: 19px;
              font-style: italic;
              color: #2A2A2A;
              line-height: 1.5;
            ">${pull_quote}</td>
          </tr>
        </table>
      </td>
    </tr>`
  : '';

const html_body = `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<title>LIBRE N°${numero} — La Lettre de TINGA</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F0EBE3; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F0EBE3; padding: 32px 0;">
  <tr>
    <td align="center">

      <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; background-color: #FFFFFF;">

        <!-- BANDE OR -->
        <tr>
          <td style="background-color: #C9943A; padding: 6px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-family: 'Courier New', Courier, monospace; font-size: 10px; font-weight: 700; letter-spacing: 3px; text-transform: uppercase; color: #FFFFFF;">ONG TINGA — Les Travailleurs Indépendants du Gabon</td>
                <td align="right" style="font-family: 'Courier New', Courier, monospace; font-size: 10px; color: rgba(255,255,255,0.85); letter-spacing: 1px; white-space: nowrap;">${date_formatee}</td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- MASTHEAD -->
        <tr>
          <td style="background-color: #1B4332; padding: 40px 32px 32px 32px; text-align: center;">
            <p style="margin: 0 0 4px 0; font-family: 'Courier New', Courier, monospace; font-size: 11px; letter-spacing: 4px; text-transform: uppercase; color: rgba(201,148,58,0.85);">N°${numero} &middot; Semaine du ${date_formatee}</p>
            <p style="margin: 0 0 8px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 60px; font-weight: 700; letter-spacing: -2px; color: #F7F3ED; line-height: 1;">LIBRE</p>
            <p style="margin: 0; font-family: 'Courier New', Courier, monospace; font-size: 11px; letter-spacing: 4px; text-transform: uppercase; color: #C9943A;">La lettre des bâtisseurs du Gabon</p>
          </td>
        </tr>

        <!-- IMAGE HEADER -->
        ${image_html}

        <!-- ÉDITO DU PRÉSIDENT -->
        <tr>
          <td style="background-color: #F7F3ED; padding: 32px 32px 28px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="padding-bottom: 16px;">
                  <p style="margin: 0; font-family: 'Courier New', Courier, monospace; font-size: 10px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; color: #C9943A;">Édito du Président</p>
                </td>
              </tr>
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td width="60" valign="top" style="padding-right: 14px;">
                        <img src="${PHOTO_PRESIDENT}" alt="Elijah Parfait ONDO OYONO" width="48" height="48"
                             style="display: block; width: 48px; height: 48px; border-radius: 50%; object-fit: cover; border: 2px solid #C9943A;" />
                      </td>
                      <td valign="top">
                        <p style="margin: 0; font-family: Georgia, 'Times New Roman', serif; font-size: 18px; font-weight: 700; color: #1A1A1A; line-height: 1.3;">${r.edito.titre || ''}</p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
              ${pull_quote_html}
              <tr>
                <td style="padding-top: 18px; border-left: 3px solid #C9943A; padding-left: 16px;">
                  <p style="margin: 0 0 14px 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 15px; color: #4A4A4A; line-height: 1.8; font-style: italic;">${r.edito.corps || ''}</p>
                  <p style="margin: 0; font-family: 'Courier New', Courier, monospace; font-size: 11px; color: #1B4332; font-weight: 700; letter-spacing: 0.5px;">${r.edito.signature || '— Elijah Parfait ONDO OYONO, Président de TINGA'}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- SÉPARATEUR VERT -->
        <tr>
          <td style="padding: 0;"><hr style="border: none; border-top: 2px solid #1B4332; margin: 0;" /></td>
        </tr>

        <!-- RUBRIQUES DYNAMIQUES -->
        ${rubriques_html}

        <!-- BLOC FEEDBACK TALLY -->
        <tr>
          <td style="background-color: #F7F3ED; padding: 24px 32px; text-align: center;">
            <p style="margin: 0 0 10px 0; font-family: 'Courier New', Courier, monospace; font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; color: #1B4332;">Cette semaine, ton défi principal c'est :</p>
            <p style="margin: 0 0 12px 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 13px; color: #4A4A4A; line-height: 2;">
              <a href="${TALLY_LINK}?r=clients" style="color: #1B4332; text-decoration: underline; margin: 0 6px;">Trouver des clients</a> &middot;
              <a href="${TALLY_LINK}?r=tresorerie" style="color: #1B4332; text-decoration: underline; margin: 0 6px;">Gérer la trésorerie</a> &middot;
              <a href="${TALLY_LINK}?r=fiscalite" style="color: #1B4332; text-decoration: underline; margin: 0 6px;">Comprendre la fiscalité</a>
            </p>
            <p style="margin: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 11px; color: #9A9A9A;">(1 clic &middot; anonyme &middot; oriente la prochaine édition)</p>
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background-color: #1B4332; padding: 32px 32px 24px 32px; text-align: center;">
            <p style="margin: 0 0 4px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 22px; font-weight: 700; color: #C9943A; letter-spacing: 1px;">TINGA</p>
            <p style="margin: 0 0 16px 0; font-family: 'Courier New', Courier, monospace; font-size: 10px; letter-spacing: 2px; text-transform: uppercase; color: rgba(247,243,237,0.5);">Trouver sa voie pour réussir</p>
            <p style="margin: 0 0 14px 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 13px; color: rgba(247,243,237,0.85); font-style: italic;">Rejoins les ${MEMBRE_COUNT} indépendants qui lisent LIBRE chaque lundi.</p>
            <p style="margin: 0 0 20px 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 12px; color: rgba(247,243,237,0.45); line-height: 1.6;">ONG TINGA — Angondjé, Carrefour Jiji, Libreville, Gabon<br />Récépissé N° 000691</p>
            <p style="margin: 0 0 16px 0;">
              <a href="https://facebook.com/ongtinga"          style="color: #C9943A; text-decoration: none; font-family: 'Courier New', Courier, monospace; font-size: 10px; letter-spacing: 1px; margin: 0 8px;">Facebook</a>
              <a href="https://linkedin.com/company/ongtinga"  style="color: #C9943A; text-decoration: none; font-family: 'Courier New', Courier, monospace; font-size: 10px; letter-spacing: 1px; margin: 0 8px;">LinkedIn</a>
              <a href="https://ongtinga.org"                   style="color: #C9943A; text-decoration: none; font-family: 'Courier New', Courier, monospace; font-size: 10px; letter-spacing: 1px; margin: 0 8px;">Site web</a>
            </p>
            <p style="margin: 0 0 8px 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 11px; color: rgba(247,243,237,0.3);">&copy; 2026 ONG TINGA &middot; Tous droits réservés</p>
            <p style="margin: 0;">
              <a href="${UNSUBSCRIBE_LINK}" style="color: rgba(247,243,237,0.35); font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 10px; text-decoration: underline;">Se désinscrire</a>
            </p>
          </td>
        </tr>

      </table>

    </td>
  </tr>
</table>

</body>
</html>`;

const sujet_email = `LIBRE N°${numero} · ${date_formatee} · ${r.edito.titre || 'La lettre des bâtisseurs du Gabon'}`;

return [{
  json: {
    html_body,
    subject_email: sujet_email,
    semaine:       data.semaine,
    image_selectionnee: image_header
  }
}];"""

CODE_PREPARE_SPEECHIFY = r"""const input = $input.first().json;
let script = input.output || input.text || '';

if (!script) throw new Error('Champ texte introuvable : ' + JSON.stringify(Object.keys(input)));

// NIVEAU 1 — Dictionnaire permanent acronymes gabonais
// FMI dédoublonné (bug corrigé)
const sigles = [
  'ANBG', 'PME', 'VPN', 'PIB', 'FMI', 'BEAC',
  'RDC', 'ONU', 'TVA', 'BEI', 'CNSS',
  'PDG', 'RPG', 'CTG', 'BGD'
];

const mots = [
  ['SEEG',   'esøʒe'],
  ['CNAMGS', 'knamʒes'],
  ['HAC',    'ak'],
  ['OPRAG',  'ɔpʁaɡ'],
  ['GSEZ',   'ɡsɛz'],
  ['GABON',  'ɡabɔ̃']
];

// NIVEAU 2 — Acronymes dynamiques détectés par l'agent
let acronymesMot   = [];
let acronymesSigle = [];

const motMatch   = script.match(/ACRONYMES_MOT:\s*([^\n]+)/);
const sigleMatch = script.match(/ACRONYMES_SIGLE:\s*([^\n]+)/);

if (motMatch)   acronymesMot   = motMatch[1].split(',').map(a => a.trim()).filter(Boolean);
if (sigleMatch) acronymesSigle = sigleMatch[1].split(',').map(a => a.trim()).filter(Boolean);

script = script
  .replace(/ACRONYMES_MOT:[^\n]+\n?/g, '')
  .replace(/ACRONYMES_SIGLE:[^\n]+\n?/g, '')
  .trim();

// Nettoyage
script = script
  .replace(/[\u{1F000}-\u{1FFFF}]/gu, '')
  .replace(/1️⃣|2️⃣|3️⃣|4️⃣|5️⃣/g, '')
  .replace(/^\d+\.\s/gm, '')
  .replace(/\bFCFA\b/g, 'francs CFA')
  .replace(/PRI\$ME/g, 'Prime');

// Application acronymes permanents
sigles.forEach(s => {
  const regex = new RegExp(`\\b${s}\\b`, 'g');
  script = script.replace(regex, `<say-as interpret-as="characters">${s}</say-as>`);
});

mots.forEach(([acronyme, phoneme]) => {
  const regex = new RegExp(`\\b${acronyme}\\b`, 'g');
  script = script.replace(regex, `<phoneme alphabet="ipa" ph="${phoneme}">${acronyme}</phoneme>`);
});

// Application acronymes dynamiques
acronymesSigle.forEach(s => {
  if (!sigles.includes(s)) {
    const regex = new RegExp(`\\b${s}\\b`, 'g');
    script = script.replace(regex, `<say-as interpret-as="characters">${s}</say-as>`);
  }
});

acronymesMot.forEach(s => {
  if (!mots.find(m => m[0] === s)) {
    const regex = new RegExp(`\\b${s}\\b`, 'g');
    script = script.replace(regex, `<say-as interpret-as="spell-out">${s}</say-as>`);
  }
});

// Pauses structurelles
script = script
  .replace(/\[Pause\]/g, '<break time="300ms"/>')
  .replace(/\n\n/g, '<break time="300ms"/>')
  .replace(/\n/g, ' ');

script = script.replace(
  /^(.{10,60}\.)\s/,
  '$1<break time="400ms"/> '
);

const ssml = `<speak>${script}</speak>`;

return [{ json: { text: ssml } }];"""

CODE_AUDIO_OUTPUT = r"""const audioData = $input.first().json.audio_data;
const buffer    = Buffer.from(audioData, 'base64');

return [{
  binary: {
    data: await this.helpers.prepareBinaryData(buffer, 'newsletter.mp3', 'audio/mpeg')
  },
  json: {}
}];"""

# ============================================================
# SYSTEM MESSAGES
# ============================================================

SYSTEM_BRIEF = """\
FORMAT DE SORTIE STRICT : JSON uniquement. Pas de texte avant ou après.

Tu es l'Analyste Éditorial de LIBRE (ONG TINGA). Ton rôle n'est pas de résumer, mais d'extraire la substance vitale des sources pour un indépendant au Gabon.

DIRECTIVES DE DENSITÉ :
1. INTERDICTION de faire des généralités (ex: "les opportunités", "le développement").
2. OBLIGATION d'extraire au moins deux "ancres réelles" par rubrique : noms propres, chiffres, dates, lieux, noms de banques (BCEG, BGFIBank, Okoumé Capital, etc.) ou décrets.
3. Les FAITS CHIFFRÉS EXTRAITS AUTOMATIQUEMENT fournis dans le prompt sont des ancres obligatoires — tu dois en utiliser au moins une par rubrique active.

ÉTAPES DE TRAVAIL :
- ANALYSE : Que change ce fait PRÉCISÉMENT pour celui qui travaille seul à Libreville ou Port-Gentil ?
- SÉLECTION IMAGE : 1 seule URL valide (pas de logo/icon).
- DÉTECTION DE TENSION : Quelle peur ou frustration réelle ce fait réveille-t-il ?

STRUCTURE DU JSON :
{
  "semaine": "YYYY-MM-DD",
  "image_selectionnee": "URL",
  "rubriques_actives": ["actu_impact", "point_bloquant", "conseil"],
  "actu_impact": {
    "faits": [{"texte": "Détail précis avec nom propre/chiffre", "url": "URL"}],
    "analyse": "L'impact sur le portefeuille ou l'emploi du temps de l'indépendant.",
    "angle": "Direction pour le rédacteur.",
    "tension": "L'émotion brute identifiée.",
    "matiere_insuffisante": false
  },
  "point_bloquant": {
    "faits": [{"texte": "L'obstacle sourcé", "url": "URL"}],
    "analyse": "Le non-dit derrière cet obstacle.",
    "angle": "Comment retourner la situation.",
    "tension": "Le sentiment d'étouffement ou de blocage.",
    "matiere_insuffisante": false
  },
  "conseil": {
    "faits": [{"texte": "L'action concrète", "url": "URL"}],
    "analyse": "Le déclic psychologique nécessaire.",
    "angle": "L'action immédiate.",
    "tension": "Le doute avant de se lancer.",
    "matiere_insuffisante": false
  },
  "invite": {"disponible": false},
  "vie_tinga": {"disponible": false}
}"""

SYSTEM_REDACTION = """\
FORMAT DE SORTIE STRICT : JSON uniquement. Pas de texte avant ou après.

Tu es le Rédacteur de LIBRE. Tu écris pour le lundi matin. Le lecteur est fatigué, seul et méfiant. Tu ne lui vends rien, tu nommes sa réalité.

TES RÈGLES D'OR :
- STRUCTURE : Chaque rubrique commence par la TENSION (ce que le lecteur ressent), s'appuie sur le FAIT PRÉCIS (nom propre, chiffre), et finit par l'OUVERTURE (la perspective).
- STYLE : Zéro adjectif inutile. Pas de "crucial", "important", "dynamique". Verbes d'action.
- ANCRAGE : Si le brief mentionne une institution (ex: la CNAMGS), elle doit figurer dans ton texte.
- INTERDIT : Ne commence jamais par une généralité. Pas de conclusion. Pas de "Chers membres".
- ACTION DE LA SEMAINE : Chaque rubrique obligatoire (actu_impact, point_bloquant, conseil) doit avoir un champ action_semaine : 1 phrase à l'impératif, délai précis, coût zéro franc.

TON : Un pair expérimenté, sec mais bienveillant.

STRUCTURE DU JSON :
{
  "semaine": "YYYY-MM-DD",
  "rubriques": {
    "edito":         {"titre": "...", "corps": "...", "signature": "— Elijah Parfait ONDO OYONO, Président de TINGA"},
    "actu_impact":   {"titre": "...", "corps": "...", "action_semaine": "Avant [délai], [verbe + détail précis]."},
    "point_bloquant":{"titre": "...", "corps": "...", "action_semaine": "Avant [délai], [verbe + détail précis]."},
    "conseil":       {"titre": "...", "corps": "...", "action_semaine": "Avant [délai], [verbe + détail précis]."},
    "invite":        {"titre": "...", "nom": "...", "corps": "..."},
    "vie_tinga":     {"titre": "...", "corps": "..."}
  }
}"""

TEXT_BRIEF = (
    "=Voici les données brutes collectées pour la newsletter \\nLIBRE de cette semaine \\n"
    "({{ $node[\"Extraction Faits Chiffrés\"].json[\"semaine\"] }}).\\n\\n"
    "FAITS CHIFFRÉS EXTRAITS AUTOMATIQUEMENT :\\n"
    "Montants FCFA détectés : {{ $node[\"Extraction Faits Chiffrés\"].json.faits_extraits.montants.join(', ') || 'aucun' }}\\n"
    "Pourcentages détectés : {{ $node[\"Extraction Faits Chiffrés\"].json.faits_extraits.pourcentages.join(', ') || 'aucun' }}\\n"
    "Institutions citées : {{ $node[\"Extraction Faits Chiffrés\"].json.faits_extraits.institutions.join(', ') || 'aucune' }}\\n\\n"
    "DONNÉES COMPLÈTES À TRAITER :\\n"
    "{{ JSON.stringify($node[\"Extraction Faits Chiffrés\"].json) }}\\n\\n"
    "CONSIGNE IMMÉDIATE :\\n"
    "Applique les 4 étapes de ton rôle d'éditorialiste.\\n"
    "1. Filtre les faits (Réf. Aujourd'hui : \\n"
    "   {{ $node[\"Extraction Faits Chiffrés\"].json[\"semaine\"] }}).\\n"
    "2. Sélectionne l'image selon les critères définis.\\n"
    "3. Vérifie la disponibilité de l'invité et de la vie de l'ONG.\\n"
    "4. Construis le brief JSON strict.\\n\\n"
    "TU ES OBLIGÉ D'UTILISER AU MOINS UN FAIT CHIFFRÉ OU UNE INSTITUTION DÉTECTÉE PAR RUBRIQUE.\\n"
    "RESTE FACTUEL. SI UNE DONNÉE MANQUE, UTILISE \\\"matiere_insuffisante\\\": true."
)

# ============================================================
# WORKFLOW JSON ASSEMBLY
# ============================================================

workflow = {
    "name": "Newsletter LIBRE de l'ONG Tinga",
    "nodes": [

        # --------------------------------------------------
        # SCHEDULE TRIGGER — lundi 06h00 WAT (UTC+1)
        # --------------------------------------------------
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {
                            "field": "weeks",
                            "weeksInterval": 1,
                            "triggerAtDay": [1],
                            "triggerAtHour": 6,
                            "triggerAtMinute": 0
                        }
                    ]
                }
            },
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.3,
            "position": [-1488, 80],
            "id": "e6d5addc-18d0-46c2-89bd-55f0d45136b5",
            "name": "Schedule Trigger"
        },

        # --------------------------------------------------
        # TAVILY — 3 requêtes ciblées (remplace Actualités)
        # --------------------------------------------------
        {
            "parameters": {
                "query": "fiscalité TVA impôts DGI CNSS PME indépendants Gabon 2026",
                "options": {
                    "topic": "news",
                    "search_depth": "advanced",
                    "max_results": 8,
                    "days": 7,
                    "include_images": True,
                    "include_domains": [
                        "gabonreview.com", "info241.com", "gabonmediatime.com",
                        "fr.infosgabon.com", "agenceecofin.com", "gabonclic.info"
                    ]
                }
            },
            "type": "@tavily/n8n-nodes-tavily.tavily",
            "typeVersion": 1,
            "position": [-1232, -480],
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "name": "Tavily Fiscalité",
            "credentials": {
                "tavilyApi": {"id": "Qh4bnHTxOpHEAaOf", "name": "Tavily Tinga"}
            }
        },
        {
            "parameters": {
                "query": "accès crédit prêt banque PME TPE Gabon BGFIBank BCEG financement 2026",
                "options": {
                    "topic": "news",
                    "search_depth": "advanced",
                    "max_results": 8,
                    "days": 14,
                    "include_images": True,
                    "include_domains": [
                        "gabonreview.com", "info241.com", "agenceecofin.com",
                        "gabonmediatime.com", "fr.infosgabon.com"
                    ]
                }
            },
            "type": "@tavily/n8n-nodes-tavily.tavily",
            "typeVersion": 1,
            "position": [-1232, -320],
            "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "name": "Tavily Crédit",
            "credentials": {
                "tavilyApi": {"id": "Qh4bnHTxOpHEAaOf", "name": "Tavily Tinga"}
            }
        },
        {
            "parameters": {
                "query": "marchés publics appels offres contrats entreprises Gabon opportunités 2026",
                "options": {
                    "topic": "news",
                    "search_depth": "advanced",
                    "max_results": 8,
                    "days": 7,
                    "include_images": True,
                    "include_domains": [
                        "gabonreview.com", "info241.com", "gabonmediatime.com",
                        "agenceecofin.com", "gabonclic.info"
                    ]
                }
            },
            "type": "@tavily/n8n-nodes-tavily.tavily",
            "typeVersion": 1,
            "position": [-1232, -160],
            "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
            "name": "Tavily Marché",
            "credentials": {
                "tavilyApi": {"id": "Qh4bnHTxOpHEAaOf", "name": "Tavily Tinga"}
            }
        },

        # --------------------------------------------------
        # COACHING — domaines corrigés
        # --------------------------------------------------
        {
            "parameters": {
                "query": "conseils gestion entreprise Afrique francophone TPE indépendants réussir",
                "options": {
                    "topic": "general",
                    "search_depth": "advanced",
                    "max_results": 10,
                    "days": 30,
                    "include_images": True,
                    "include_domains": [
                        "agenceecofin.com",
                        "jeuneafrique.com",
                        "afripriz.org",
                        "macarrierepro.com",
                        "ietp.com"
                    ]
                }
            },
            "type": "@tavily/n8n-nodes-tavily.tavily",
            "typeVersion": 1,
            "position": [-1232, 0],
            "id": "04e8c3aa-26c4-418a-a5fc-fb41e0d5f68a",
            "name": "Coaching",
            "credentials": {
                "tavilyApi": {"id": "Qh4bnHTxOpHEAaOf", "name": "Tavily Tinga"}
            }
        },

        # --------------------------------------------------
        # SUPABASE CHECKS
        # --------------------------------------------------
        {
            "parameters": {
                "operation": "getAll",
                "tableId": "articles_traites",
                "filters": {
                    "conditions": [
                        {
                            "keyName": "date_collecte",
                            "condition": "gt",
                            "keyValue": "={{ $now.minus({days: 7}).toISO() }}"
                        }
                    ]
                }
            },
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [-1232, 176],
            "id": "6c5aa04b-7d58-4dcf-9bca-89d800b39ed8",
            "name": "Tally Check",
            "executeOnce": True,
            "alwaysOutputData": True,
            "credentials": {
                "supabaseApi": {"id": "qgQaNipmMDt1dnkB", "name": "LE BURÖ"}
            }
        },
        {
            "parameters": {
                "operation": "getAll",
                "tableId": "articles_traites",
                "filters": {
                    "conditions": [
                        {
                            "keyName": "date_collecte",
                            "condition": "gt",
                            "keyValue": "={{ $now.minus({days: 7}).toISO() }}"
                        }
                    ]
                }
            },
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [-1232, 336],
            "id": "c2d81ddc-389d-4c8c-b0d9-054ceca14d33",
            "name": "ONG Check",
            "executeOnce": True,
            "alwaysOutputData": True,
            "credentials": {
                "supabaseApi": {"id": "qgQaNipmMDt1dnkB", "name": "LE BURÖ"}
            }
        },

        # --------------------------------------------------
        # MERGE — 6 entrées (3 Tavily actu + Coaching + Tally + ONG)
        # --------------------------------------------------
        {
            "parameters": {"numberInputs": 6},
            "type": "n8n-nodes-base.merge",
            "typeVersion": 3.2,
            "position": [-992, 64],
            "id": "fe775217-6192-496a-8fe6-892b6818cfa9",
            "name": "Merge"
        },

        # --------------------------------------------------
        # NORMALISATION — mise à jour pour 6 sources
        # --------------------------------------------------
        {
            "parameters": {"jsCode": CODE_NORMALISATION},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-752, 96],
            "id": "f2e2ab15-69ce-41d6-99ad-edae2997eb32",
            "name": "normalisation"
        },

        # --------------------------------------------------
        # SÉLECTION IMAGE FIABLE (nouveau nœud)
        # --------------------------------------------------
        {
            "parameters": {"jsCode": CODE_SELECTION_IMAGE},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-544, -80],
            "id": "e5f6a7b8-c9d0-1234-efab-345678901234",
            "name": "Sélection Image Fiable"
        },

        # --------------------------------------------------
        # EXTRACTION FAITS CHIFFRÉS (nouveau nœud)
        # --------------------------------------------------
        {
            "parameters": {"jsCode": CODE_EXTRACTION_FAITS},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-352, -80],
            "id": "f6a7b8c9-d0e1-2345-fabc-456789012345",
            "name": "Extraction Faits Chiffrés"
        },

        # --------------------------------------------------
        # AGENT IA — BRIEF ÉDITORIAL
        # --------------------------------------------------
        {
            "parameters": {
                "promptType": "define",
                "text": TEXT_BRIEF,
                "options": {"systemMessage": SYSTEM_BRIEF}
            },
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 3.1,
            "position": [-544, 96],
            "id": "cd426515-3bb6-47de-9dfd-80e65558c1cb",
            "name": "Agent IA - Brief Éditorial"
        },

        # --------------------------------------------------
        # PRÉPARER PROMPT RÉDACTION
        # --------------------------------------------------
        {
            "parameters": {"jsCode": CODE_PREPARER_PROMPT},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-224, 96],
            "id": "e509f6e9-b439-4016-b732-686c8c88278e",
            "name": "Préparer Prompt Rédaction",
            "executeOnce": False
        },

        # --------------------------------------------------
        # AGENT IA — RÉDACTION NEWSLETTER
        # --------------------------------------------------
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $node[\"Préparer Prompt Rédaction\"].json[\"prompt_redacteur\"] }}",
                "options": {
                    "systemMessage": "=" + SYSTEM_REDACTION,
                    "batching": {"batchSize": 1, "delayBetweenBatches": 4000}
                }
            },
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 3.1,
            "position": [-32, 96],
            "id": "acd7e6ce-b5c3-454c-a31b-f6471ce88114",
            "name": "Agent IA - Rédaction Newsletter"
        },

        # --------------------------------------------------
        # CORRECTION DU JSON — fix rubriques_actives
        # --------------------------------------------------
        {
            "parameters": {"jsCode": CODE_CORRECTION_JSON},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [304, 96],
            "id": "72b8964f-7a81-4a05-8ea4-fbf1ac24fd80",
            "name": "Correction du JSON"
        },

        # --------------------------------------------------
        # IF — vérification erreur
        # --------------------------------------------------
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict",
                        "version": 3
                    },
                    "conditions": [
                        {
                            "id": "c044fa5a-52ac-4af0-8ae4-744beb38141e",
                            "leftValue": "={{ $json.erreur }}",
                            "rightValue": False,
                            "operator": {"type": "boolean", "operation": "equals"}
                        }
                    ],
                    "combinator": "and"
                },
                "options": {}
            },
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.3,
            "position": [512, 96],
            "id": "a2d22aef-538a-4d5a-a7a9-9efcfa6ce097",
            "name": "If"
        },

        # --------------------------------------------------
        # GÉNÉRER HTML NEWSLETTER — redesign v2
        # --------------------------------------------------
        {
            "parameters": {"jsCode": CODE_GENERER_HTML},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [848, 80],
            "id": "137c80ee-ed37-43fb-82f3-4495412d3a92",
            "name": "Générer HTML Newsletter",
            "executeOnce": True
        },

        # --------------------------------------------------
        # SEND A MESSAGE — Gmail (inchangé)
        # --------------------------------------------------
        {
            "parameters": {
                "sendTo": "kodbart@gmail.com",
                "subject": "={{ $json.subject_email }}",
                "message": "={{ $json.html_body }}",
                "options": {}
            },
            "type": "n8n-nodes-base.gmail",
            "typeVersion": 2.2,
            "position": [1024, 80],
            "id": "62f026c6-2fb1-405b-97c8-37094a17c2a4",
            "name": "Send a message",
            "webhookId": "487720dd-42e7-4872-ba4b-b30a4d15c010",
            "credentials": {
                "gmailOAuth2": {"id": "pLxdjO9AlsoAOgXR", "name": "Gmail account"}
            }
        },

        # --------------------------------------------------
        # SAVE TO DATABASE — champs corrigés
        # --------------------------------------------------
        {
            "parameters": {
                "tableId": "articles_traites",
                "fieldsUi": {
                    "fieldValues": [
                        {"fieldId": "url",          "fieldValue": "={{ 'newsletter-' + $node['Correction du JSON'].json.semaine }}"},
                        {"fieldId": "titre",         "fieldValue": "={{ $node['Générer HTML Newsletter'].json.subject_email }}"},
                        {"fieldId": "source",        "fieldValue": "LIBRE"},
                        {"fieldId": "resume",        "fieldValue": "={{ $node['Correction du JSON'].json.semaine }}"},
                        {"fieldId": "date_collecte", "fieldValue": "={{ $now.toISO() }}"}
                    ]
                }
            },
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [1200, 80],
            "id": "df052096-7246-49f9-a3df-e76697d7cf7a",
            "name": "Save to Database",
            "credentials": {
                "supabaseApi": {"id": "qgQaNipmMDt1dnkB", "name": "LE BURÖ"}
            },
            "onError": "continueRegularOutput"
        },

        # --------------------------------------------------
        # TELEGRAM — chatId corrigé (placeholder numérique)
        # --------------------------------------------------
        {
            "parameters": {
                "chatId": "TELEGRAM_CHAT_ID_ICI",
                "text": "=⚠️ LIBRE — Erreur JSON détectée\nSemaine : {{ $json.semaine }}\nMotif : {{ $json.message }}\n\nContenu brut :\n{{ ($json.raw || '').substring(0, 1000) }}",
                "additionalFields": {}
            },
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [720, 192],
            "id": "d1f7458e-563c-4969-96e8-849bbdc1d614",
            "name": "Send a text message",
            "webhookId": "42545d10-cc71-4e45-825c-0d33c4a8c3ab",
            "credentials": {
                "telegramApi": {"id": "rgtTq9hA0xOk54CO", "name": "Telegram TINGA"}
            }
        },

        # --------------------------------------------------
        # PREPARE SPEECHIFY — doublon FMI supprimé
        # --------------------------------------------------
        {
            "parameters": {"jsCode": CODE_PREPARE_SPEECHIFY},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [848, -144],
            "id": "93bb0792-4d0b-4fbc-8283-4c9a2f477fea",
            "name": "Prepare Speechify"
        },

        # --------------------------------------------------
        # SPEECHIFY — clé API sécurisée (placeholder)
        # --------------------------------------------------
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.speechify.ai/v1/audio/speech",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {
                            "name": "Authorization",
                            "value": "Bearer SPEECHIFY_API_KEY_ICI"
                        }
                    ]
                },
                "sendBody": True,
                "bodyParameters": {
                    "parameters": [
                        {"name": "input",        "value": "={{ $json.text }}"},
                        {"name": "voice_id",     "value": "maxime"},
                        {"name": "audio_format", "value": "mp3"},
                        {"name": "model",        "value": "simba-multilingual"},
                        {"name": "language",     "value": "fr-FR"}
                    ]
                },
                "options": {
                    "response": {
                        "response": {"responseFormat": "json"}
                    }
                }
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.4,
            "position": [1024, -144],
            "id": "759dd568-73ad-4c6c-bd16-7b0bae9f8d4b",
            "name": "SPEECHIFY"
        },

        # --------------------------------------------------
        # AUDIO OUTPUT (inchangé)
        # --------------------------------------------------
        {
            "parameters": {"jsCode": CODE_AUDIO_OUTPUT},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1200, -144],
            "id": "8b34c6af-ed71-44a0-bec7-8791324db070",
            "name": "Audio Output"
        },

        # --------------------------------------------------
        # MODÈLES IA
        # --------------------------------------------------
        {
            "parameters": {
                "model": "llama-3.3-70b-versatile",
                "options": {"maxTokensToSample": 8000, "temperature": 0.4}
            },
            "type": "@n8n/n8n-nodes-langchain.lmChatGroq",
            "typeVersion": 1,
            "position": [-544, 352],
            "id": "2f8e09ad-67fb-4745-b154-2c52230deff6",
            "name": "Groq Edito",
            "credentials": {
                "groqApi": {"id": "r2Ij0yqdN2dpjWcQ", "name": "Groq TINGA"}
            }
        },
        {
            "parameters": {
                "model": "anthropic/claude-sonnet-4",
                "options": {"temperature": 0.7}
            },
            "type": "@n8n/n8n-nodes-langchain.lmChatOpenRouter",
            "typeVersion": 1,
            "position": [-32, 336],
            "id": "3c070ae1-a76b-406d-9481-ae3f3c6da78b",
            "name": "OpenRouter Chat Model",
            "credentials": {
                "openRouterApi": {"id": "awZ7N9zLM2eDQryI", "name": "OpenRouter account"}
            }
        }
    ],

    # ============================================================
    # CONNEXIONS
    # ============================================================
    "connections": {

        "Schedule Trigger": {
            "main": [[
                {"node": "Tavily Fiscalité", "type": "main", "index": 0},
                {"node": "Tavily Crédit",    "type": "main", "index": 0},
                {"node": "Tavily Marché",    "type": "main", "index": 0},
                {"node": "Coaching",         "type": "main", "index": 0},
                {"node": "Tally Check",      "type": "main", "index": 0},
                {"node": "ONG Check",        "type": "main", "index": 0}
            ]]
        },

        "Tavily Fiscalité": {"main": [[{"node": "Merge", "type": "main", "index": 0}]]},
        "Tavily Crédit":    {"main": [[{"node": "Merge", "type": "main", "index": 1}]]},
        "Tavily Marché":    {"main": [[{"node": "Merge", "type": "main", "index": 2}]]},
        "Coaching":         {"main": [[{"node": "Merge", "type": "main", "index": 3}]]},
        "Tally Check":      {"main": [[{"node": "Merge", "type": "main", "index": 4}]]},
        "ONG Check":        {"main": [[{"node": "Merge", "type": "main", "index": 5}]]},

        "Merge": {
            "main": [[{"node": "normalisation", "type": "main", "index": 0}]]
        },

        "normalisation": {
            "main": [[
                {"node": "Sélection Image Fiable",    "type": "main", "index": 0}
            ]]
        },

        "Sélection Image Fiable": {
            "main": [[{"node": "Extraction Faits Chiffrés", "type": "main", "index": 0}]]
        },

        "Extraction Faits Chiffrés": {
            "main": [[{"node": "Agent IA - Brief Éditorial", "type": "main", "index": 0}]]
        },

        "Agent IA - Brief Éditorial": {
            "main": [[{"node": "Préparer Prompt Rédaction", "type": "main", "index": 0}]]
        },

        "Préparer Prompt Rédaction": {
            "main": [[{"node": "Agent IA - Rédaction Newsletter", "type": "main", "index": 0}]]
        },

        "Agent IA - Rédaction Newsletter": {
            "main": [[{"node": "Correction du JSON", "type": "main", "index": 0}]]
        },

        "Correction du JSON": {
            "main": [[{"node": "If", "type": "main", "index": 0}]]
        },

        # If true → HTML email + pipeline audio en parallèle
        # If false → alerte Telegram
        "If": {
            "main": [
                [
                    {"node": "Générer HTML Newsletter", "type": "main", "index": 0},
                    {"node": "Prepare Speechify",       "type": "main", "index": 0}
                ],
                [
                    {"node": "Send a text message", "type": "main", "index": 0}
                ]
            ]
        },

        "Générer HTML Newsletter": {
            "main": [[{"node": "Send a message", "type": "main", "index": 0}]]
        },

        "Send a message": {
            "main": [[{"node": "Save to Database", "type": "main", "index": 0}]]
        },

        "Prepare Speechify": {
            "main": [[{"node": "SPEECHIFY", "type": "main", "index": 0}]]
        },

        "SPEECHIFY": {
            "main": [[{"node": "Audio Output", "type": "main", "index": 0}]]
        },

        "Groq Edito": {
            "ai_languageModel": [[
                {"node": "Agent IA - Brief Éditorial", "type": "ai_languageModel", "index": 0}
            ]]
        },

        "OpenRouter Chat Model": {
            "ai_languageModel": [[
                {"node": "Agent IA - Rédaction Newsletter", "type": "ai_languageModel", "index": 0}
            ]]
        }
    },

    "pinData": {},
    "active": False,
    "settings": {
        "executionOrder": "v1",
        "binaryMode": "separate"
    },
    "versionId": "aed6ff7b-ae55-401e-beb8-4b9d2aaf95b3",
    "meta": {
        "templateCredsSetupCompleted": True,
        "instanceId": "ef4f6e096e4f388cc53079b9f28db5969c578c760fd94221fe1b8fbaa6e035a5"
    },
    "id": "8AxFOHVYY9zu4Phu",
    "tags": []
}

# Écriture du JSON
output_path = "/home/user/ongtinga/newsletter_LIBRE_v2.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(workflow, f, ensure_ascii=False, indent=2)

print(f"JSON généré : {output_path}")
print(f"Taille : {len(json.dumps(workflow, ensure_ascii=False))} caractères")
