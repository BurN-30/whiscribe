/* =========================================================================
   WhisperScribe — logique d'interface

   Le Python appelle les fonctions globales onXxx() définies plus bas.
   L'interface appelle Python via pywebview.api.*
   ========================================================================= */

'use strict';

const etat = {
  config: {},
  presets: [],
  fichiers: new Map(),   // identifiant -> données de la ligne
  historique: [],
  diarisation: { disponible: false, jeton_present: false, guide: {} },
  enCours: false,
  apercuChemin: null,
  pret: false,
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function ech(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function nbFr(valeur, decimales) {
  return Number(valeur).toFixed(decimales === undefined ? 2 : decimales).replace('.', ',');
}

function icone(nom, classe) {
  return `<svg class="icone ${classe || ''}"><use href="#${nom}"></use></svg>`;
}

/* ------------------------------------------------------------ Démarrage */

window.addEventListener('pywebviewready', async () => {
  try {
    const donnees = await pywebview.api.etat_initial();
    initialiser(donnees);
  } catch (e) {
    journaliser('erreur', "L'interface n'a pas pu récupérer l'état de l'application.");
    console.error(e);
  }
});

function initialiser(d) {
  etat.config = d.config || {};
  etat.presets = d.presets || [];
  etat.diarisation = d.diarisation || etat.diarisation;

  $('#version').textContent = 'v' + d.version;
  appliquerTheme(etat.config.theme || 'auto');
  appliquerZoom(etat.config.zoom || 1);

  dessinerMateriel(d.materiel, d.recommandation);
  dessinerPresets(d.recommandation);
  remplirModelesAvances(d.modeles_avances || []);
  appliquerConfig();
  majGlossaire(d.glossaire ? d.glossaire.resume : null);
  majCorrections(d.corrections || {});
  majDiarisation();
  afficherAvertissements(d.avertissements || []);

  if (!d.ffmpeg) {
    journaliser('erreur',
      "FFmpeg est introuvable : aucun fichier ne pourra être lu. Relancez « installer.bat ».");
  }
  journaliser('info', 'Prêt. Journal détaillé : logs/' + d.journal);

  etat.pret = true;
  majBoutons();
  pywebview.api.charger_historique();
}

/* -------------------------------------------------------------- Matériel */

function dessinerMateriel(mat, reco) {
  $('#materiel-resume').textContent = mat.resume;
  $('#materiel-conseil').textContent = reco.phrase;

  const lignes = [];
  const ajout = (cle, valeur, classe) =>
    lignes.push(`<div class="materiel-ligne"><span class="cle">${ech(cle)}</span>
      <span class="valeur ${classe || ''}">${ech(valeur)}</span></div>`);

  ajout('Processeur', mat.cpu_nom);
  ajout('Cœurs', (mat.coeurs_physiques ? mat.coeurs_physiques + ' physiques, ' : '')
    + mat.coeurs_logiques + ' logiques, ' + mat.fils_calcul + ' utilisés');
  ajout('Mémoire vive', nbFr(mat.ram_go, 1) + ' Go'
    + (mat.ram_libre_go ? ' (' + nbFr(mat.ram_libre_go, 1) + ' Go libres)' : ''));
  (mat.gpus || []).forEach((g) => {
    ajout('Carte graphique', g.nom + (g.memoire_mo ? ' — ' + nbFr(g.memoire_mo / 1024, 1) + ' Go' : ''));
    if (g.note) ajout('', g.note, g.accelere ? '' : 'mention-honnete');
  });
  (mat.npus || []).forEach((n) => {
    ajout('Circuit neuronal', n.nom);
    if (n.note) ajout('', n.note, 'mention-honnete');
  });
  if (!mat.gpus.length) ajout('Carte graphique', 'aucune carte dédiée détectée');
  ajout('Calcul retenu', mat.peripherique === 'cuda'
    ? 'NVIDIA CUDA, précision float16'
    : 'processeur, quantification int8');
  ajout('Système', mat.systeme);

  lignes.push('<div style="height:8px"></div>');
  (reco.estimations || []).forEach((e) => {
    ajout(e.nom, 'environ ' + e.pour_une_heure + ' pour une heure d\'audio (facteur '
      + nbFr(e.facteur) + ')');
  });
  lignes.push(`<div class="materiel-ligne"><span class="cle"></span>
    <span class="valeur" style="font-size:11.5px">Estimations, pas des garanties :
    l'interface affiche le temps réellement mesuré à chaque transcription.</span></div>`);

  $('#materiel-detail').innerHTML = lignes.join('');
}

function basculerMateriel() {
  const detail = $('#materiel-detail');
  const ouvert = detail.classList.toggle('ouvert');
  $('#materiel-entete').setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  $('#materiel-chevron').style.transform = ouvert ? 'rotate(180deg)' : '';
}

/* --------------------------------------------------------------- Presets */

function dessinerPresets(reco) {
  const conseille = reco ? reco.preset_conseille : null;
  $('#presets').innerHTML = etat.presets.map((p) => `
    <button class="preset" data-preset="${ech(p.cle)}" aria-pressed="false">
      <span class="titre">
        <span class="marqueur"></span>${ech(p.nom)}
        ${p.cle === conseille ? '<span class="conseille">conseillé ici</span>' : ''}
      </span>
      <span class="desc">${ech(p.resume)}</span>
      <span class="chiffres">
        ${ech(p.modele)} · environ ${ech(p.pour_une_heure)} pour une heure d'audio
        · téléchargement ${ech(p.telechargement)}
      </span>
    </button>`).join('');

  $$('#presets .preset').forEach((b) => {
    b.addEventListener('click', () => {
      etat.config.preset = b.dataset.preset;
      majPresetActif();
      enregistrer({ preset: etat.config.preset });
      rafraichirEstimations();
    });
  });
  majPresetActif();
}

function majPresetActif() {
  $$('#presets .preset').forEach((b) => {
    b.setAttribute('aria-pressed', b.dataset.preset === etat.config.preset ? 'true' : 'false');
  });
}

function remplirModelesAvances(modeles) {
  const sel = $('#modele-avance');
  sel.innerHTML = '<option value="">Modèle du preset</option>' + modeles.map((m) =>
    `<option value="${ech(m.cle)}">${ech(m.nom)} — ${ech(m.taille)}, qualité ${ech(m.qualite.toLowerCase())}</option>`
  ).join('');
}

/* -------------------------------------------------------------- Réglages */

function appliquerConfig() {
  const c = etat.config;
  $('#langue').value = c.langue || 'fr';
  $('#dossier-sortie').value = c.dossier_sortie || '';
  const f = c.formats || {};
  $('#fmt-txt').checked = f.txt !== false;
  $('#fmt-srt').checked = !!f.srt;
  $('#fmt-vtt').checked = !!f.vtt;
  $('#fmt-horodatage').checked = !!f.horodatage;
  $('#opt-glossaire').checked = c.utiliser_glossaire !== false;
  $('#opt-corrections').checked = c.appliquer_corrections !== false;
  $('#opt-diarisation').checked = !!c.diarisation;
  $('#nb-locuteurs').value = String(c.nb_locuteurs || 0);
  $('#opt-avance').checked = !!c.mode_avance;
  $('#modele-avance').value = c.modele_avance || '';
  $('#beam').value = c.beam_size || '';
  $('#opt-contexte').checked = c.condition_on_previous_text !== false;
  $('#opt-salle').checked = !!c.filtres_salle;
  $('#opt-processeur').checked = !!c.forcer_processeur;
  $('#bloc-avance').style.display = c.mode_avance ? 'block' : 'none';
  $('#bloc-locuteurs').style.display = c.diarisation ? 'block' : 'none';
  majPresetActif();
}

async function enregistrer(partiel) {
  Object.assign(etat.config, partiel);
  try {
    const retour = await pywebview.api.sauver_config(partiel);
    if (retour) {
      etat.config = retour.config;
      afficherAvertissements(retour.avertissements || []);
    }
  } catch (e) { console.error(e); }
}

function afficherAvertissements(liste) {
  $('#avertissements').innerHTML = (liste || []).map((m) => `
    <div class="encart encart-attention">${icone('i-alerte', 'icone-s')}<span>${ech(m)}</span></div>`
  ).join('');
}

function majGlossaire(resume) {
  if (!resume) return;
  const el = $('#etat-glossaire');
  if (!resume.nb_termes) {
    el.textContent = 'Aucun terme, à remplir';
  } else {
    el.textContent = resume.nb_retenus + ' terme' + (resume.nb_retenus > 1 ? 's' : '')
      + ' actif' + (resume.nb_retenus > 1 ? 's' : '')
      + (resume.tronque ? ' sur ' + resume.nb_termes + ', liste tronquée' : '');
  }
}

function majCorrections(donnees) {
  const el = $('#etat-corrections');
  const nb = donnees.nb || 0;
  el.textContent = nb ? nb + ' règle' + (nb > 1 ? 's' : '') : 'Aucune règle';
  if (donnees.erreurs && donnees.erreurs.length) {
    el.textContent += ', ' + donnees.erreurs.length + ' ligne(s) en erreur';
  }
}

function majDiarisation() {
  const d = etat.diarisation;
  const el = $('#etat-diarisation');
  const bascule = $('#opt-diarisation');

  if (!d.disponible) {
    el.textContent = 'Composants non installés';
    bascule.checked = false;
    bascule.disabled = true;
    $('#libelle-jeton').textContent = 'Voir la procédure';
  } else if (!d.jeton_present) {
    el.textContent = 'Jeton Hugging Face à renseigner';
    bascule.disabled = false;
    $('#libelle-jeton').textContent = "Configurer l'accès";
  } else {
    el.textContent = bascule.checked ? 'Active' : 'Disponible';
    bascule.disabled = false;
    $('#libelle-jeton').textContent = 'Modifier le jeton';
  }
  $('#bloc-locuteurs').style.display = bascule.checked ? 'block' : 'none';
}

async function rafraichirEstimations() {
  for (const [id, item] of etat.fichiers) {
    if (item.etat !== 'attente' || !item.duree_secs) continue;
    try {
      item.estimation = await pywebview.api.estimation(
        item.duree_secs, etat.config.preset, !!etat.config.diarisation,
        etat.config.mode_avance ? (etat.config.modele_avance || '') : '');
      majLigne(id);
    } catch (e) { /* sans conséquence */ }
  }
}

/* ------------------------------------------------------------------ File */

function dessinerFile() {
  const vue = $('#vue-file');
  $('#compteur-file').textContent = String(etat.fichiers.size);
  if (!etat.fichiers.size) {
    vue.innerHTML = `<div class="vide">${icone('i-depot')}
      <div>Aucun fichier en attente.</div>
      <div style="font-size:12px;margin-top:4px">Glissez vos enregistrements dans la zone ci-dessus.</div>
    </div>`;
    return;
  }
  vue.innerHTML = Array.from(etat.fichiers.keys()).map(ligneHTML).join('');
  brancherLignes();
}

const PASTILLES = {
  attente: ['', 'i-fichier'],
  decodage: ['encours', 'i-onde'],
  transcription: ['encours', 'i-onde'],
  locuteurs: ['encours', 'i-personnes'],
  ecriture: ['encours', 'i-fichier'],
  termine: ['termine', 'i-coche'],
  erreur: ['erreur', 'i-alerte'],
  annule: ['annule', 'i-croix'],
};

function ligneHTML(id) {
  const it = etat.fichiers.get(id);
  const [classe, ic] = PASTILLES[it.etat] || PASTILLES.attente;
  const actif = ['decodage', 'transcription', 'locuteurs', 'ecriture'].includes(it.etat);

  let meta = '', classeMeta = '';
  if (it.etat === 'attente') {
    meta = [it.duree, it.taille, it.estimation ? 'environ ' + it.estimation + ' de calcul' : '']
      .filter(Boolean).join(' · ');
  } else if (actif) {
    meta = [it.phase || it.message, it.ecoule ? 'écoulé ' + it.ecoule : '',
      it.restant ? 'reste ' + it.restant : ''].filter(Boolean).join(' · ');
  } else if (it.etat === 'termine') {
    classeMeta = 'succes';
    meta = ['Terminé en ' + (it.duree_calcul || '?'),
      it.facteur ? nbFr(it.facteur) + ' x la durée de l\'audio' : '',
      it.locuteurs ? it.locuteurs + ' locuteurs' : '',
      it.corrections ? it.corrections + ' corrections' : ''].filter(Boolean).join(' · ');
  } else if (it.etat === 'erreur') {
    classeMeta = 'erreur';
    meta = (it.titre || 'Échec') + (it.message ? ' — ' + it.message : '');
  } else {
    meta = it.message || 'Annulé';
  }

  const sorties = (it.sorties || []).map((s) =>
    `<span class="sortie" data-ouvrir="${ech(s.chemin)}">${ech(s.format)} · ${ech(s.nom)}</span>`
  ).join('');

  return `<div class="ligne" data-id="${ech(id)}">
    <span class="pastille ${classe}">${icone(ic, 'icone-s')}</span>
    <div class="infos">
      <div class="nom" title="${ech(it.chemin)}">${ech(it.nom)}</div>
      <div class="meta ${classeMeta}">${ech(meta)}</div>
      ${actif ? `<div class="barre"><span style="width:${it.pct || 0}%"></span></div>` : ''}
      ${sorties ? `<div class="sorties">${sorties}</div>` : ''}
    </div>
    ${it.etat === 'erreur' ? `<button class="bouton-ligne" data-log title="Ouvrir le journal">${icone('i-info', 'icone-s')}</button>` : ''}
    ${actif ? '' : `<button class="bouton-ligne" data-retirer title="Retirer">${icone('i-croix', 'icone-s')}</button>`}
  </div>`;
}

function majLigne(id) {
  const ligne = document.querySelector(`#vue-file .ligne[data-id="${CSS.escape(id)}"]`);
  if (!ligne) { dessinerFile(); return; }
  ligne.outerHTML = ligneHTML(id);
  brancherLignes();
}

function brancherLignes() {
  $$('#vue-file [data-retirer]').forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      const id = b.closest('.ligne').dataset.id;
      etat.fichiers.delete(id);
      pywebview.api.retirer(id);
      dessinerFile();
      majBoutons();
    };
  });
  $$('#vue-file [data-log]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); pywebview.api.ouvrir_journal(); };
  });
  $$('#vue-file [data-ouvrir]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); ouvrirApercu(b.dataset.ouvrir); };
  });
}

/* ------------------------------------------------------------ Historique */

function dessinerHistorique() {
  const vue = $('#vue-historique');
  $('#compteur-historique').textContent = String(etat.historique.length);
  if (!etat.historique.length) {
    vue.innerHTML = `<div class="vide">${icone('i-horloge')}
      <div>Aucune transcription dans le dossier de sortie.</div></div>`;
    return;
  }
  vue.innerHTML = etat.historique.map((h) => `
    <div class="ligne" data-chemin="${ech(h.chemin)}">
      <span class="pastille termine">${icone('i-coche', 'icone-s')}</span>
      <div class="infos">
        <div class="nom">${ech(h.nom)}</div>
        <div class="meta">${ech(h.date)} · ${ech(h.taille)}</div>
      </div>
      <span class="etiquette-format">${ech(h.format)}</span>
    </div>`).join('');
  $$('#vue-historique .ligne').forEach((l) => {
    l.onclick = () => ouvrirApercu(l.dataset.chemin);
  });
}

async function ouvrirApercu(chemin) {
  etat.apercuChemin = chemin;
  $('#titre-apercu').textContent = chemin.split(/[\\/]/).pop();
  $('#contenu-apercu').textContent = 'Chargement...';
  ouvrirModale('#modale-apercu');
  try {
    const texte = await pywebview.api.lire_texte(chemin);
    $('#contenu-apercu').textContent = texte || '(fichier vide ou illisible)';
  } catch (e) {
    $('#contenu-apercu').textContent = '(lecture impossible)';
  }
}

/* --------------------------------------------------------------- Journal */

function journaliser(niveau, texte) {
  const zone = $('#journal-contenu');
  const heure = new Date().toLocaleTimeString('fr-FR', { hour12: false });
  const ligne = document.createElement('div');
  ligne.className = 'l';
  ligne.innerHTML = `<span class="h">${heure}</span><span class="${ech(niveau)}">${ech(texte)}</span>`;
  zone.appendChild(ligne);
  while (zone.childElementCount > 500) zone.removeChild(zone.firstChild);
  zone.scrollTop = zone.scrollHeight;
  $('#journal-dernier').textContent = texte;
}

function basculerJournal() {
  const entete = $('#journal-entete');
  const contenu = $('#journal-contenu');
  const ouvert = contenu.classList.toggle('ouvert');
  entete.classList.toggle('ouvert', ouvert);
  entete.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  if (ouvert) contenu.scrollTop = contenu.scrollHeight;
  enregistrer({ journal_ouvert: ouvert });
}

/* ------------------------------------------------------------ État global */

function setEtat(texte, classe) {
  $('#etat-texte').textContent = texte;
  $('#etat-global').className = 'etat-global ' + (classe || '');
}

function majBoutons() {
  const enAttente = Array.from(etat.fichiers.values()).filter((f) => f.etat === 'attente').length;
  $('#btn-lancer').disabled = etat.enCours || !enAttente || !etat.pret;
  $('#btn-arreter').disabled = !etat.enCours;
  $('#btn-lancer').innerHTML = icone('i-lecture', 'icone-s')
    + (enAttente > 1 ? ` Transcrire ${enAttente} fichiers` : ' Lancer la transcription');
}

/* ------------------------------------------- Rappels appelés par Python */

window.onFichiersAjoutes = function (items) {
  items.forEach((it) => etat.fichiers.set(it.id, Object.assign({ pct: 0 }, it)));
  dessinerFile();
  majBoutons();
  basculerVue('file');
};

window.onDuree = async function (id, secondes, texte) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  it.duree_secs = secondes;
  it.duree = texte;
  try {
    it.estimation = await pywebview.api.estimation(
      secondes, etat.config.preset, !!etat.config.diarisation,
      etat.config.mode_avance ? (etat.config.modele_avance || '') : '');
  } catch (e) { /* sans conséquence */ }
  majLigne(id);
};

window.onDossierSortie = function (chemin) {
  $('#dossier-sortie').value = chemin;
  etat.config.dossier_sortie = chemin;
};

window.onHistorique = function (items) {
  etat.historique = items || [];
  dessinerHistorique();
};

window.onEtat = function (id, nouvelEtat, message) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  it.etat = nouvelEtat;
  it.message = message;
  if (nouvelEtat !== 'attente') it.phase = message;
  majLigne(id);
  if (['decodage', 'transcription', 'locuteurs', 'ecriture'].includes(nouvelEtat)) {
    setEtat(message + ' — ' + it.nom, 'actif');
  }
};

window.onProgression = function (id, d) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  Object.assign(it, { pct: d.pct, phase: d.phase, ecoule: d.ecoule, restant: d.restant });
  const ligne = document.querySelector(`#vue-file .ligne[data-id="${CSS.escape(id)}"]`);
  if (ligne) {
    const barre = ligne.querySelector('.barre span');
    if (barre) barre.style.width = d.pct + '%';
    const meta = ligne.querySelector('.meta');
    if (meta) {
      meta.textContent = [d.phase, d.ecoule ? 'écoulé ' + d.ecoule : '',
        d.restant ? 'reste ' + d.restant : ''].filter(Boolean).join(' · ');
    }
  } else {
    majLigne(id);
  }
  setEtat(`${d.phase} ${d.pct} % — ${it.nom}`, 'actif');
};

window.onFichierTermine = function (id, d) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  if (d.ok) {
    it.etat = 'termine';
    it.sorties = d.sorties || [];
    it.duree_calcul = d.duree;
    it.facteur = d.facteur;
    it.locuteurs = d.locuteurs;
    it.corrections = d.corrections;
  } else if (d.annule) {
    it.etat = 'annule';
    it.message = 'Arrêté avant la fin';
  } else {
    it.etat = 'erreur';
    it.titre = d.titre;
    it.message = d.message;
  }
  majLigne(id);
  majBoutons();
};

window.onFileTerminee = function (d) {
  etat.enCours = false;
  majBoutons();
  if (d.echecs) {
    setEtat(`${d.reussis} réussie(s), ${d.echecs} en échec`, 'erreur');
  } else if (d.annules) {
    setEtat(`Arrêté — ${d.reussis} transcription(s) produite(s)`, '');
  } else {
    setEtat(`${d.reussis} transcription(s) terminée(s)`, 'succes');
  }
  journaliser(d.echecs ? 'attention' : 'ok',
    `File terminée : ${d.reussis} réussie(s), ${d.echecs} en échec, ${d.annules} annulée(s).`);
  pywebview.api.charger_historique();
};

window.onJournal = function (niveau, texte) {
  journaliser(niveau, texte);
};

window.finDepot = function () {
  $('#zone-depot').classList.remove('survol');
};

/* ---------------------------------------------------------------- Modales */

function ouvrirModale(selecteur) { $(selecteur).classList.add('ouvert'); }
function fermerModale(el) { el.classList.remove('ouvert'); }
function fermerToutesModales() { $$('.voile.ouvert').forEach(fermerModale); }

/* ------------------------------------------------------- Thème et zoom */

function appliquerTheme(mode) {
  if (mode === 'auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', mode);
  etat.config.theme = mode;
}

function themeSuivant() {
  const ordre = ['auto', 'clair', 'sombre'];
  const suivant = ordre[(ordre.indexOf(etat.config.theme || 'auto') + 1) % 3];
  appliquerTheme(suivant);
  enregistrer({ theme: suivant });
  journaliser('info', 'Thème : ' + suivant);
}

function appliquerZoom(valeur) {
  etat.config.zoom = Math.min(1.6, Math.max(0.7, valeur));
  document.body.style.zoom = etat.config.zoom;
}

/* ------------------------------------------------------------ Câblage UI */

document.addEventListener('DOMContentLoaded', () => {
  dessinerFile();
  dessinerHistorique();

  $('#materiel-entete').addEventListener('click', basculerMateriel);
  $('#materiel-entete').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); basculerMateriel(); }
  });

  $('#btn-theme').addEventListener('click', themeSuivant);
  $('#btn-aide').addEventListener('click', () => ouvrirModale('#modale-aide'));
  $('#btn-ouvrir-app').addEventListener('click', () => pywebview.api.ouvrir_dossier_application());

  // Dépôt de fichiers. Le chemin réel est récupéré côté Python : un navigateur
  // ne le communique jamais au JavaScript.
  const zone = $('#zone-depot');
  zone.addEventListener('click', () => pywebview.api.ajouter_fichiers());
  zone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pywebview.api.ajouter_fichiers(); }
  });
  ['dragenter', 'dragover'].forEach((evt) => {
    document.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.add('survol');
    });
  });
  ['dragleave', 'drop'].forEach((evt) => {
    document.addEventListener(evt, (e) => {
      e.preventDefault();
      if (evt === 'dragleave' && e.relatedTarget) return;
      zone.classList.remove('survol');
    });
  });

  // Onglets
  $('#onglet-file').addEventListener('click', () => basculerVue('file'));
  $('#onglet-historique').addEventListener('click', () => basculerVue('historique'));
  $('#btn-vider').addEventListener('click', () => {
    Array.from(etat.fichiers.entries()).forEach(([id, it]) => {
      if (['attente', 'termine', 'erreur', 'annule'].includes(it.etat)) etat.fichiers.delete(id);
    });
    pywebview.api.vider_file();
    dessinerFile();
    majBoutons();
  });

  // Réglages simples
  $('#langue').addEventListener('change', (e) => enregistrer({ langue: e.target.value }));
  $('#btn-dossier').addEventListener('click', () => pywebview.api.choisir_dossier_sortie());
  $('#btn-ouvrir-dossier').addEventListener('click', () => pywebview.api.ouvrir_dossier_sortie());

  const formats = () => ({
    txt: $('#fmt-txt').checked, srt: $('#fmt-srt').checked,
    vtt: $('#fmt-vtt').checked, horodatage: $('#fmt-horodatage').checked,
  });
  ['#fmt-txt', '#fmt-srt', '#fmt-vtt', '#fmt-horodatage'].forEach((s) => {
    $(s).addEventListener('change', () => {
      if (!$('#fmt-txt').checked && !$('#fmt-srt').checked && !$('#fmt-vtt').checked) {
        $('#fmt-txt').checked = true;
        journaliser('attention', 'Au moins un format de sortie doit rester coché.');
      }
      enregistrer({ formats: formats() });
    });
  });

  $('#opt-glossaire').addEventListener('change', (e) =>
    enregistrer({ utiliser_glossaire: e.target.checked }));
  $('#opt-corrections').addEventListener('change', (e) =>
    enregistrer({ appliquer_corrections: e.target.checked }));

  $('#opt-diarisation').addEventListener('change', (e) => {
    enregistrer({ diarisation: e.target.checked });
    majDiarisation();
    rafraichirEstimations();
    if (e.target.checked && !etat.diarisation.jeton_present) ouvrirModale('#modale-jeton');
  });
  $('#nb-locuteurs').addEventListener('change', (e) =>
    enregistrer({ nb_locuteurs: parseInt(e.target.value, 10) || 0 }));

  $('#opt-avance').addEventListener('change', (e) => {
    $('#bloc-avance').style.display = e.target.checked ? 'block' : 'none';
    enregistrer({ mode_avance: e.target.checked });
    rafraichirEstimations();
  });
  $('#modele-avance').addEventListener('change', (e) => {
    enregistrer({ modele_avance: e.target.value });
    rafraichirEstimations();
  });
  $('#beam').addEventListener('change', (e) =>
    enregistrer({ beam_size: parseInt(e.target.value, 10) || 0 }));
  $('#opt-contexte').addEventListener('change', (e) =>
    enregistrer({ condition_on_previous_text: e.target.checked }));
  $('#opt-salle').addEventListener('change', (e) =>
    enregistrer({ filtres_salle: e.target.checked }));
  $('#opt-processeur').addEventListener('change', (e) =>
    enregistrer({ forcer_processeur: e.target.checked }));

  // Glossaire et corrections
  $('#btn-glossaire').addEventListener('click', async () => {
    const d = await pywebview.api.etat_initial();
    $('#zone-glossaire').value = d.glossaire.contenu || '';
    $('#retour-glossaire').innerHTML = encartInfo(d.glossaire.resume.message);
    ouvrirModale('#modale-glossaire');
  });
  $('#btn-enregistrer-glossaire').addEventListener('click', async () => {
    const resume = await pywebview.api.sauver_glossaire($('#zone-glossaire').value);
    majGlossaire(resume);
    $('#retour-glossaire').innerHTML = resume.tronque
      ? encartAttention(resume.message) : encartSucces(resume.message);
    journaliser('ok', 'Glossaire enregistré. ' + resume.message);
    setTimeout(() => fermerModale($('#modale-glossaire')), 700);
  });

  $('#btn-corrections').addEventListener('click', async () => {
    const d = await pywebview.api.etat_initial();
    $('#zone-corrections').value = d.corrections.contenu || '';
    $('#retour-corrections').innerHTML = '';
    ouvrirModale('#modale-corrections');
  });
  $('#btn-enregistrer-corrections').addEventListener('click', async () => {
    const r = await pywebview.api.sauver_corrections($('#zone-corrections').value);
    majCorrections(r);
    $('#retour-corrections').innerHTML = r.erreurs.length
      ? r.erreurs.map(encartAttention).join('')
      : encartSucces(r.nb + ' règle(s) enregistrée(s).');
    journaliser('ok', r.nb + ' règle(s) de correction enregistrée(s).');
    if (!r.erreurs.length) setTimeout(() => fermerModale($('#modale-corrections')), 700);
  });

  // Jeton Hugging Face
  $('#btn-jeton').addEventListener('click', () => {
    const d = etat.diarisation;
    $('#etat-diarisation-modale').innerHTML = d.disponible ? '' :
      encartAttention(d.indisponibilite);
    $('#etapes-jeton').innerHTML = (d.guide.etapes || []).map((e) => `<li>${ech(e)}</li>`).join('');
    $('#retour-jeton').innerHTML = '';
    $('#champ-jeton').value = '';
    ouvrirModale('#modale-jeton');
  });
  $('#btn-lien-conditions').addEventListener('click', () =>
    pywebview.api.ouvrir_lien(etat.diarisation.guide.url_conditions));
  $('#btn-lien-jeton').addEventListener('click', () =>
    pywebview.api.ouvrir_lien(etat.diarisation.guide.url_jeton));
  $('#btn-enregistrer-jeton').addEventListener('click', async () => {
    const r = await pywebview.api.enregistrer_jeton($('#champ-jeton').value);
    $('#retour-jeton').innerHTML = r.ok ? encartSucces(r.message) : encartAttention(r.message);
    if (r.ok) {
      etat.diarisation.jeton_present = !!$('#champ-jeton').value.trim();
      majDiarisation();
      journaliser('ok', r.message);
    }
  });
  $('#btn-effacer-jeton').addEventListener('click', async () => {
    await pywebview.api.enregistrer_jeton('');
    etat.diarisation.jeton_present = false;
    $('#champ-jeton').value = '';
    $('#retour-jeton').innerHTML = encartInfo('Jeton effacé.');
    majDiarisation();
  });

  // Aperçu
  $('#btn-ouvrir-apercu').addEventListener('click', () => {
    if (etat.apercuChemin) pywebview.api.ouvrir(etat.apercuChemin);
  });
  $('#btn-copier-apercu').addEventListener('click', async () => {
    const texte = $('#contenu-apercu').textContent;
    try { await navigator.clipboard.writeText(texte); }
    catch (e) { pywebview.api.copier(texte); }
    journaliser('ok', 'Texte copié dans le presse-papiers.');
  });

  // Journal
  $('#journal-entete').addEventListener('click', (e) => {
    if (e.target.id === 'btn-fichier-log') return;
    basculerJournal();
  });
  $('#btn-fichier-log').addEventListener('click', (e) => {
    e.stopPropagation();
    pywebview.api.ouvrir_journal();
  });

  // Actions
  $('#btn-lancer').addEventListener('click', lancer);
  $('#btn-arreter').addEventListener('click', () => {
    pywebview.api.arreter();
    $('#btn-arreter').disabled = true;
    setEtat('Arrêt en cours...', '');
  });

  // Modales : fermeture
  $$('[data-fermer]').forEach((b) => {
    b.addEventListener('click', () => fermerModale(b.closest('.voile')));
  });
  $$('.voile').forEach((v) => {
    v.addEventListener('mousedown', (e) => { if (e.target === v) fermerModale(v); });
  });

  // Raccourcis
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { fermerToutesModales(); return; }
    if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); lancer(); }
    if (e.ctrlKey && (e.key === '+' || e.key === '=')) { e.preventDefault(); zoom(0.1); }
    if (e.ctrlKey && e.key === '-') { e.preventDefault(); zoom(-0.1); }
    if (e.ctrlKey && e.key === '0') { e.preventDefault(); appliquerZoom(1); enregistrer({ zoom: 1 }); }
  });
  document.addEventListener('wheel', (e) => {
    if (e.ctrlKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 0.05 : -0.05); }
  }, { passive: false });
});

function zoom(delta) {
  appliquerZoom((etat.config.zoom || 1) + delta);
  enregistrer({ zoom: etat.config.zoom });
}

function basculerVue(vue) {
  const file = vue === 'file';
  $('#vue-file').style.display = file ? 'flex' : 'none';
  $('#vue-historique').style.display = file ? 'none' : 'flex';
  $('#onglet-file').setAttribute('aria-selected', file ? 'true' : 'false');
  $('#onglet-historique').setAttribute('aria-selected', file ? 'false' : 'true');
  $('#btn-vider').style.display = file ? '' : 'none';
}

async function lancer() {
  if (etat.enCours) return;
  const retour = await pywebview.api.demarrer();
  if (!retour.ok) {
    journaliser('erreur', retour.message);
    setEtat(retour.message, 'erreur');
    return;
  }
  etat.enCours = true;
  majBoutons();
  setEtat('Démarrage...', 'actif');
  if (!$('#journal-contenu').classList.contains('ouvert')) {
    // Le détail reste replié : l'état lisible suffit en façade.
  }
}

function encartInfo(m) {
  return `<div class="encart encart-info">${icone('i-info', 'icone-s')}<span>${ech(m)}</span></div>`;
}
function encartSucces(m) {
  return `<div class="encart encart-succes">${icone('i-coche', 'icone-s')}<span>${ech(m)}</span></div>`;
}
function encartAttention(m) {
  return `<div class="encart encart-attention">${icone('i-alerte', 'icone-s')}<span>${ech(m)}</span></div>`;
}
