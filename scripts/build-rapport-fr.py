"""Rapport de synthèse en français (35 pages au maximum).

Synthèse française du même projet que documentation/FINAL-REPORT.pdf (rapport
complet en anglais), organisée par risques traités plutôt que par étape. Tous
les chiffres viennent d'une seule exécution de référence (REFERENCE_RUN) ; les
valeurs sont recopiées de ses rapports d'outils, sauf mention contraire.

Usage : python scripts/build-rapport-fr.py [--pdf] [--chrome CHEMIN]
"""
import argparse
import base64
import html
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "documentation/screenshots"
REPO = "https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6"
RUNS = REPO + "/actions/runs/"
REFERENCE_RUN = "43082725820"   # exécution de référence sur master, 11 novembre 2026
AZURE_RUN = "42108525318"       # dernière livraison réussie sur Azure, 5 novembre 2026
MAX_PAGES = 35

# Chiffres clés de l'exécution de référence (rapports devsecops-security-reports de REFERENCE_RUN).
KPIS = [
    ("10 min 15 s", "du push au courriel de statut"),
    ("16 / 17", "contrôles réussis, 1 point d'attention"),
    ("0", "vulnérabilité élevée ou critique dans l'image"),
    ("108", "paquets Java inventoriés (SBOM)"),
    ("0", "échec Checkov (27 et 43 contrôles)"),
    ("41,5 %", "de couverture de code (6 tests)"),
    ("11", "problèmes SonarQube encore ouverts"),
    ("13", "mises à jour Dependabot en attente"),
]

# Matrice des risques : risque, contrôle, outil, résultat mesuré, effet sur la chaîne.
RISKS = [
    ("Secret publié dans le dépôt", "Analyse de tout l'historique Git et du contenu indexé avant commit", "Gitleaks, pre-commit", "Aucune fuite", "Bloquant"),
    ("Code applicatif vulnérable", "Analyse statique à chaque push, porte de qualité avant livraison", "Semgrep, SonarQube", "19 fichiers, 0 alerte Semgrep ; porte SonarQube franchie, 11 problèmes ouverts", "Bloquant"),
    ("Bibliothèque vulnérable", "Analyse du POM avant compilation, inventaire CycloneDX", "Trivy", "108 paquets, 0 vulnérabilité élevée ou critique", "Bloquant"),
    ("Infrastructure mal configurée", "Politiques Terraform, règle maison contre SSH ouvert à Internet", "Checkov", "27 et 43 contrôles réussis sur deux configurations, 0 échec", "Bloquant"),
    ("Image conteneur vulnérable", "Analyse de l'image finale construite à partir du JAR testé", "Trivy", "0 vulnérabilité élevée ou critique", "Bloquant"),
    ("Artefact substitué", "Somme SHA-1 du JAR stocké comparée au JAR testé ; déploiement par empreinte immuable", "Nexus, registre OCI", "SHA-1 identiques (91d61c45…)", "Bloquant"),
    ("Port exposé par erreur", "Balayage TCP de 1 041 ports depuis l'interface réseau et la boucle locale", "Nmap", "Seuls le SSH du runner et les 4 ports attendus sont ouverts", "Bloquant"),
    ("Régression fonctionnelle", "Tests unitaires et HTTP, puis requête réelle sur l'API déployée", "Maven, JUnit, JaCoCo", "6 tests réussis ; l'API renvoie des données de la base", "Bloquant"),
    ("Panne non détectée", "Collecte de métriques et tableaux de bord pendant l'exécution", "Prometheus, Grafana", "2 cibles sur 2 actives, 30 requêtes sur 30 réussies", "Bloquant"),
    ("Dépendances qui vieillissent", "Propositions hebdomadaires de mise à jour pour 5 écosystèmes", "Dependabot", "13 propositions ouvertes, alertes de sécurité désactivées", "Signalé"),
]

# Chronologie réelle de l'exécution de référence (heures UTC, journal GitHub Actions).
TIMELINE = [
    ("18:58:01", "Push sur master", "Déclenchement automatique de la chaîne."),
    ("18:58:04", "Contrôles de développement", "Hooks, Semgrep, Gitleaks, Trivy (POM) et Checkov en parallèle, terminés à 18:59:20, avant toute compilation."),
    ("18:59:22", "Préparation du runner", "Libération d'espace disque, puis démarrage de SonarQube et Nexus à 19:01:03."),
    ("19:01:33", "Compilation et tests", "Maven, 6 tests JUnit et mesure de couverture JaCoCo."),
    ("19:03:19", "Qualité puis artefact", "Analyse SonarQube et porte de qualité, puis publication et vérification dans Nexus à 19:04:00."),
    ("19:04:13", "Image et registre", "Construction de l'image, analyse Trivy, puis publication dans le registre à 19:04:47."),
    ("19:04:57", "Acceptation", "Démarrage du laboratoire Docker Compose, puis balayage Nmap de 19:05:39 à 19:06:21."),
    ("19:06:21", "Production", "Vérification de l'empreinte de l'image en service et d'une requête réelle à l'API."),
    ("19:06:22", "Exploitation", "Métriques Prometheus et tableaux Grafana, jusqu'à 19:07:22."),
    ("19:07:30", "Maintenance des dépendances", "Relevé des propositions Dependabot et de l'état des alertes."),
    ("19:08:09", "Courriel de statut", "Résultat de chaque étape et lien vers l'exécution, envoyés à 19:08:16."),
]

FIGURES = [
    ("run43082725820_sonarqube-issues.png", "SonarQube : 11 problèmes ouverts, dont 6 de sévérité élevée liés à la liaison directe d'entités JPA dans les contrôleurs."),
    ("run43082725820_swagger-api.png", "L'API déployée dans le laboratoire éphémère, documentée par Swagger."),
    ("run43082725820_prometheus-targets.png", "Prometheus : l'API et le Node Exporter du runner sont actifs (le job conserve son nom historique « azure-nodes »).", 62),
    ("run43082725820_grafana-student-api-dashboard.png", "Grafana : disponibilité, débit, latence et mémoire de l'API pendant l'exécution."),
    ("email_commit_security_run43080079320.png", "Courriel de statut reçu dans la boîte de réception (exécution 43080079320), adresse masquée."),
]

INCIDENTS = [
    ("Octobre 2026", "Trivy bloque la première image : 11 vulnérabilités élevées ou critiques.", "Versions de Spring Boot, Tomcat et Jackson dépassées.", "Passage à Spring Boot 4 et forçage de Jackson 3.1.7 ; nouvelle analyse à 0."),
    ("Octobre 2026", "Checkov refuse le port HTTP 80 ouvert à Internet (CKV_AZURE_160).", "Le port servait à la validation des certificats.", "Port fermé, validation TLS-ALPN sur le port 443 ; nouvelle analyse réussie."),
    ("23 octobre 2026", "Le premier déploiement Compose sur Azure échoue.", "Ports non publiés sur des réseaux internes, fichiers de configuration illisibles.", "Réseau de pont dédié, fichiers de configuration rendus lisibles (mode 0644) ; déploiement réussi."),
    ("Octobre 2026", "Nexus signale l'utilisation de sa clé de chiffrement par défaut.", "Clé privée non configurée à l'installation.", "Clé de 32 octets générée et montée en lecture seule, secrets rechiffrés."),
    ("11 novembre 2026", "Nmap refuse la première exécution sur le runner GitHub.", "Le runner expose son propre service SSH (port 22).", "Politique ajustée pour ce seul port ; les ports du laboratoire restent contrôlés."),
]

ACTIONS = [
    ("Élevée", "Remplacer les entités JPA exposées par des DTO de requête", "Supprime les 6 problèmes élevés SonarQube"),
    ("Élevée", "Activer les alertes et mises à jour de sécurité Dependabot", "Les vulnérabilités connues seraient signalées automatiquement"),
    ("Moyenne", "Ajouter l'authentification et l'autorisation à l'API", "Indispensable avant toute donnée réelle"),
    ("Moyenne", "Traiter les 13 propositions de mise à jour, dont 8 majeures", "Réduit la dette de dépendances"),
    ("Moyenne", "Étendre les tests au-delà de 41,5 % de couverture", "Mieux protéger contre les régressions"),
    ("Faible", "Rendre la règle de branche master active", "Bloque toute fusion sans contrôles réussis"),
]


def image(name):
    return "data:image/png;base64," + base64.b64encode((SHOTS / name).read_bytes()).decode("ascii")


def referenced_files():
    return {figure[0] for figure in FIGURES}


def diagram():
    phases = [("Développement", "hooks · SAST · secrets", "SBOM · IaC"), ("Acceptation", "tests · qualité · artefact", "image · Nmap"),
              ("Production", "empreinte de l'image", "requête API"), ("Exploitation", "Prometheus", "Grafana"),
              ("Maintenance", "Dependabot", "courriel")]
    boxes, x, width, gap = [], 4, 132, 16
    for index, (name, line1, line2) in enumerate(phases):
        boxes.append(f"<rect x='{x}' y='14' width='{width}' height='88' rx='10' fill='#0f4c5c'/>"
                     f"<text x='{x + width / 2}' y='44' text-anchor='middle' fill='#fff' font-size='14' font-weight='bold'>{html.escape(name)}</text>"
                     f"<text x='{x + width / 2}' y='66' text-anchor='middle' fill='#cfe6ea' font-size='10'>{html.escape(line1)}</text>"
                     f"<text x='{x + width / 2}' y='82' text-anchor='middle' fill='#cfe6ea' font-size='10'>{html.escape(line2)}</text>")
        if index < len(phases) - 1:
            boxes.append(f"<path d='M{x + width + 2} 58 h{gap - 9}' stroke='#e09f3e' stroke-width='3' marker-end='url(#arrow)'/>")
        x += width + gap
    return (f"<svg viewBox='0 0 {x} 116' role='img' aria-label='Les cinq phases de la chaîne' style='width:100%'>"
            "<defs><marker id='arrow' markerWidth='6' markerHeight='6' refX='3' refY='3' orient='auto'><path d='M0,0 L6,3 L0,6 z' fill='#e09f3e'/></marker></defs>"
            + "".join(boxes) + "</svg>")


def revision_label():
    """Nomme HEAD seulement si les entrées du rapport (ce script, les captures) sont commitées."""
    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    head = git("rev-parse", "--short", "HEAD") or "inconnue"
    dirty = [line for line in git("status", "--porcelain", "--", "scripts/build-rapport-fr.py", "documentation/screenshots").splitlines() if line]
    if dirty:
        return f"copie de travail basée sur <code>{head}</code>, avec {len(dirty)} entrée(s) non commitée(s)"
    return f"<code>{head}</code>"


def build(commit="inconnue", revision=None):
    esc = html.escape
    css = """
    @page{size:A4;margin:18mm 16mm 20mm;@bottom-left{content:'Synthèse DevSecOps — O. Koudhai';font:8pt Georgia,serif;color:#5b6b73}
      @bottom-right{content:counter(page) ' / ' counter(pages);font:8pt Georgia,serif;color:#5b6b73}}
    @page:first{margin:0;@bottom-left{content:none}@bottom-right{content:none}}
    body{font:10.5pt/1.55 'Segoe UI',Arial,sans-serif;color:#1d2b33;margin:0}
    h1,h2,h3{font-family:Georgia,'Times New Roman',serif;color:#0f4c5c}
    h2{font-size:19pt;margin:0 0 10px;padding-bottom:6px;border-bottom:3px solid #e09f3e;break-after:avoid}
    h3{font-size:12.5pt;margin:16px 0 6px;break-after:avoid}
    section{break-before:page}
    .cover{height:297mm;display:flex;flex-direction:column;justify-content:space-between;background:#0f4c5c;color:#fff;padding:28mm 22mm;box-sizing:border-box}
    .cover .title{font:bold 30pt/1.15 Georgia,'Times New Roman',serif;color:#fff;margin:0 0 14px}.cover .band{height:6px;width:90px;background:#e09f3e;margin:18px 0}
    .cover .meta{font-size:11pt;line-height:1.8}.cover .note{background:rgba(255,255,255,.1);padding:12px 14px;border-left:4px solid #e09f3e;font-size:9.5pt}
    .toc ol{font-size:12pt;line-height:2.1}.lead{font-size:11.5pt}
    .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin:14px 0}
    .kpi{border:1px solid #c8d6da;border-top:5px solid #0f4c5c;padding:10px;border-radius:6px;break-inside:avoid}
    .kpi b{display:block;font:bold 17pt Georgia,serif;color:#0f4c5c;white-space:nowrap}.kpi span{font-size:8.5pt;color:#4a5a62}
    .kpi.warn{border-top-color:#e09f3e}.kpi.warn b{color:#a35f00}
    table{border-collapse:collapse;width:100%;font-size:9pt;margin:8px 0}th{background:#0f4c5c;color:#fff;text-align:left;padding:6px}
    td{padding:6px;border-bottom:1px solid #d5e0e3;vertical-align:top}tr:nth-child(even) td{background:#f4f8f9}tr{break-inside:avoid}
    .tag{font-size:8pt;padding:1px 6px;border-radius:8px;background:#dcefe6;color:#1d6b46;white-space:nowrap}.tag.soft{background:#fde9c8;color:#8a5200}
    .timeline{border-left:3px solid #e09f3e;margin:12px 0 0 6px;padding-left:16px}.step{margin:0 0 12px;break-inside:avoid}
    .step time{font:bold 10pt Georgia,serif;color:#0f4c5c;margin-right:8px}.step strong{color:#1d2b33}
    figure{margin:10px 0 18px;break-inside:avoid}figure img{width:100%;max-height:120mm;object-fit:contain;border:1px solid #c8d6da}
    figcaption{font-size:8.8pt;color:#4a5a62;margin-top:4px}figcaption b{color:#0f4c5c}
    .callout{background:#f4f8f9;border-left:4px solid #0f4c5c;padding:10px 12px;margin:10px 0}
    .callout.warn{border-left-color:#e09f3e;background:#fff7ea}a{color:#0f4c5c}
    """
    kpis = "".join(f"<div class='kpi{' warn' if label in ('problèmes SonarQube encore ouverts', 'mises à jour Dependabot en attente') else ''}'>"
                   f"<b>{esc(value)}</b><span>{esc(label)}</span></div>" for value, label in KPIS)
    risks = "".join(f"<tr><td><b>{esc(r)}</b></td><td>{esc(c)}</td><td>{esc(t)}</td><td>{esc(m)}</td>"
                    f"<td><span class='tag{'' if e == 'Bloquant' else ' soft'}'>{esc(e)}</span></td></tr>" for r, c, t, m, e in RISKS)
    timeline = "".join(f"<div class='step'><time>{esc(t)}</time><strong>{esc(a)}</strong><br>{esc(d)}</div>" for t, a, d in TIMELINE)
    def crop(figure):  # optional 3rd value: visible height in mm, top of the capture kept
        return f" style='height:{figure[2]}mm;object-fit:cover;object-position:top'" if len(figure) > 2 else ""
    figures = "".join(f"<figure><img src='{image(f[0])}' alt='{esc(f[1])}'{crop(f)}><figcaption><b>Figure {i}.</b> {esc(f[1])}</figcaption></figure>"
                      for i, f in enumerate(FIGURES, start=1))
    incidents = "".join(f"<tr><td>{esc(d)}</td><td>{esc(s)}</td><td>{esc(c)}</td><td>{esc(f)}</td></tr>" for d, s, c, f in INCIDENTS)
    actions = "".join(f"<tr><td><span class='tag{' soft' if p != 'Faible' else ''}'>{esc(p)}</span></td><td>{esc(a)}</td><td>{esc(g)}</td></tr>" for p, a, g in ACTIONS)
    return f"""<!doctype html><html lang="fr"><meta charset="utf-8"><title>Synthèse DevSecOps — rapport en français</title><style>{css}</style>
<div class="cover"><div><div style="font-size:10pt;letter-spacing:.2em;text-transform:uppercase;color:#e09f3e">Esprit · 4NIDS6 · Module DevOps</div>
<div class="band"></div><div class="title">Sécuriser et livrer une API Spring Boot&nbsp;: une chaîne DevSecOps de bout en bout</div>
<div style="font-size:13pt;color:#cfe6ea">Rapport de synthèse en français</div></div>
<div class="meta">Oussama Koudhai<br>Application de gestion des étudiants<br>12 novembre 2026<br>Exécution de référence&nbsp;: n° {REFERENCE_RUN}</div>
<div class="note">Ce document est la synthèse française du rapport complet en anglais (<i>documentation/FINAL-REPORT.pdf</i>) consacré au même projet.
Il présente les résultats par risque traité ; le rapport complet détaille chaque étape et contient les rapports d'outils originaux.</div></div>

<section class="toc"><h2>Sommaire</h2><ol><li>L'essentiel en une page</li><li>Contexte et contraintes</li><li>Organisation de la chaîne</li>
<li>Les risques traités</li><li>Une exécution réelle, minute par minute</li><li>Preuves sélectionnées</li><li>Incidents rencontrés et corrections</li>
<li>Limites et plan d'action</li><li>Conclusion</li></ol>
<div class="callout">Toutes les valeurs proviennent de l'exécution GitHub Actions <a href="{RUNS}{REFERENCE_RUN}">n° {REFERENCE_RUN}</a> sur la branche master,
sauf la partie historique Azure et les incidents datés.</div></section>

<section><h2>1. L'essentiel en une page</h2>
<p class="lead">À chaque push sur <i>master</i>, une chaîne automatisée contrôle le code et l'infrastructure, construit et analyse l'application,
la déploie dans un environnement de test éphémère, vérifie son exposition réseau et sa supervision, puis envoie un courriel de statut.</p>
<div class="kpis">{kpis}</div>
<div class="callout"><b>Ce qui fonctionne.</b> Seize contrôles automatisés réussissent et le dix-septième, Dependabot, signale des points d'attention sans bloquer ;
chaque outil produit son propre rapport, conservé 30 jours
avec l'exécution ; un même artefact testé est analysé, stocké, déployé par empreinte et vérifié.</div>
<div class="callout warn"><b>Ce qui reste à faire.</b> Six problèmes de sécurité de sévérité élevée signalés par SonarQube restent ouverts, les alertes
de sécurité Dependabot sont désactivées et l'API n'a pas d'authentification&nbsp;: elle ne doit contenir que des données fictives.</div></section>

<section><h2>2. Contexte et contraintes</h2>
<p>Le point de départ est une API REST Spring Boot de gestion des étudiants, des départements et des inscriptions, initialement livrée avec Jenkins et Minikube.
Le projet l'a étendue en chaîne DevSecOps&nbsp;: contrôles de sécurité avant compilation, qualité, artefacts, images analysées, déploiement, acceptation réseau,
supervision et maintenance des dépendances.</p>
<h3>Deux environnements successifs</h3>
<table><tr><th>Période</th><th>Environnement</th><th>Statut</th></tr>
<tr><td>Jusqu'au 5 novembre 2026</td><td>Deux machines virtuelles Azure (application, puis SonarQube et Nexus), provisionnées par Terraform</td>
<td>Livraison complète réussie (exécution <a href="{RUNS}{AZURE_RUN}">n° {AZURE_RUN}</a>)</td></tr>
<tr><td>Depuis le 11 novembre 2026</td><td>Runner GitHub gratuit (4 processeurs, 16 Go)&nbsp;: tous les outils sont démarrés pour l'exécution puis détruits</td>
<td>Exécutions réussies sur master</td></tr></table>
<p>Le changement a été imposé par la fin de l'abonnement Azure for Students&nbsp;: la machine des outils est devenue injoignable. Plutôt que de payer
deux machines virtuelles en continu, la chaîne recrée à chaque exécution SonarQube, Nexus, un registre d'images et l'application, avec les mêmes
fichiers Docker Compose que sur Azure.</p>
<div class="callout"><b>Conséquence à garder en tête.</b> Il n'existe plus d'adresse permanente à ouvrir&nbsp;: les preuves sont les rapports,
les captures et le courriel produits par chaque exécution. La «&nbsp;production&nbsp;» est un contrôle final sur la même pile éphémère, pas un
environnement séparé.</div></section>

<section><h2>3. Organisation de la chaîne</h2>
<p>La chaîne suit les phases du cours. Chaque phase ne démarre que si la précédente a réussi, à l'exception de la maintenance des dépendances,
du rapport combiné et du courriel, qui s'exécutent dans tous les cas pour rendre compte.</p>
{diagram()}
<h3>Rôle de chaque outil</h3>
<table><tr><th>Phase</th><th>Outils</th><th>Ce qu'ils garantissent</th></tr>
<tr><td>Développement</td><td>pre-commit, Gitleaks, Semgrep, Trivy, Checkov, modèle de menaces STRIDE</td><td>Rien n'est compilé si un secret, une faille simple, une dépendance vulnérable ou une erreur d'infrastructure est détecté.</td></tr>
<tr><td>Acceptation</td><td>Maven, JUnit, JaCoCo, SonarQube, Nexus, Docker, Trivy, registre OCI, Docker Compose, Nmap</td><td>Le même JAR testé devient une image analysée, déployée par empreinte immuable, dont l'exposition réseau est vérifiée.</td></tr>
<tr><td>Production</td><td>Inspection Docker, requête API</td><td>L'image en service est bien celle qui a été analysée, et l'API lit la base de données.</td></tr>
<tr><td>Exploitation</td><td>Prometheus, Node Exporter, Grafana</td><td>Les métriques de l'application et de l'hôte sont collectées et visibles.</td></tr>
<tr><td>Maintenance</td><td>Dependabot, courriel SMTP</td><td>Les mises à jour en attente et le résultat de chaque exécution sont signalés.</td></tr></table></section>

<section><h2>4. Les risques traités</h2>
<p>Plutôt qu'une liste d'outils, cette matrice part des risques&nbsp;: pour chacun, le contrôle qui le réduit, l'outil, et ce que l'exécution de référence a mesuré.</p>
<table><tr><th style="width:17%">Risque</th><th style="width:28%">Contrôle</th><th style="width:15%">Outil</th><th style="width:28%">Mesure</th><th>Effet</th></tr>{risks}</table>
<p style="font-size:9pt;color:#4a5a62">« Bloquant »&nbsp;: un échec arrête la chaîne avant la livraison. « Signalé »&nbsp;: le résultat est mis en évidence dans le rapport sans bloquer.</p></section>

<section><h2>5. Une exécution réelle, minute par minute</h2>
<p>Exécution <a href="{RUNS}{REFERENCE_RUN}">n° {REFERENCE_RUN}</a> du 11 novembre 2026 (heures UTC). Durée totale&nbsp;: <b>10 minutes 15 secondes</b>.</p>
<div class="timeline">{timeline}</div>
<div class="callout">Le job principal dure 8 minutes, dont 1 min 41 s de préparation du runner. SonarQube et Nexus y sont démarrés pendant la
compilation, puis arrêtés après leurs étapes pour libérer la mémoire avant le déploiement de l'application.</div></section>

<section><h2>6. Preuves sélectionnées</h2>
<p>Captures réalisées automatiquement par l'exécution elle-même (navigateur sans interface, adresses locales du runner), sauf le courriel.
Pour Nexus, la preuve retenue n'est pas une capture mais la comparaison des sommes SHA-1&nbsp;: le JAR stocké
(<code>91d61c4591c967e7…</code>) est identique au JAR testé.</p>{figures}</section>

<section><h2>7. Incidents rencontrés et corrections</h2>
<p>Ces incidents réels montrent que les contrôles ont effectivement arrêté la chaîne, et comment chacun a été corrigé.</p>
<table><tr><th style="width:15%">Date</th><th style="width:30%">Constat</th><th style="width:25%">Cause</th><th>Correction</th></tr>{incidents}</table></section>

<section><h2>8. Limites et plan d'action</h2>
<h3>Limites assumées</h3><ul>
<li>L'environnement est éphémère&nbsp;: aucune donnée ni tableau de bord ne survit à l'exécution.</li>
<li>Dans ce runner jetable, la consultation anonyme en lecture seule est activée sur SonarQube, Nexus et Grafana pour permettre les captures ; la licence
de Nexus Community Edition est acceptée automatiquement à chaque exécution, à la demande du propriétaire du projet.</li>
<li>La porte de qualité SonarQube porte sur le nouveau code&nbsp;: la franchir ne prouve pas l'absence de problèmes dans le code existant.</li>
<li>Le balayage Nmap ne couvre que TCP et une liste de ports définie ; UDP n'est pas testé.</li></ul>
<h3>Plan d'action</h3>
<table><tr><th style="width:14%">Priorité</th><th style="width:46%">Action</th><th>Bénéfice attendu</th></tr>{actions}</table></section>

<section><h2>9. Conclusion</h2>
<p class="lead">La chaîne réalisée applique les principes DevSecOps de bout en bout&nbsp;: les contrôles de sécurité interviennent avant la compilation,
un seul artefact traverse toutes les étapes, chaque outil laisse une trace vérifiable et l'équipe est informée à chaque exécution.</p>
<p>La fin de l'abonnement Azure a été transformée en une version sans coût qui conserve toutes les étapes. Les prochaines améliorations ne portent plus sur la
chaîne elle-même mais sur ce qu'elle a révélé&nbsp;: corriger les six problèmes de sécurité élevés, activer les alertes Dependabot et protéger l'API.</p>
<div class="callout">Pour le détail de chaque étape, les rapports d'outils originaux et les journaux&nbsp;: rapport complet en anglais,
<i>documentation/FINAL-REPORT.pdf</i>. Dépôt&nbsp;: <a href="{REPO}">{REPO}</a>. Révision de ce document&nbsp;: {revision or f"<code>{esc(commit)}</code>"}.</div></section>
</html>"""


def count_pages(pdf):
    try:
        import pymupdf
        with pymupdf.open(pdf) as document:
            return document.page_count
    except ImportError:
        return len(re.findall(rb"/Type\s*/Page[^s]", Path(pdf).read_bytes()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", action="store_true")
    parser.add_argument("--chrome", default="C:/Program Files/Google/Chrome/Application/chrome.exe")
    args = parser.parse_args()
    missing = sorted(n for n in referenced_files() if not (SHOTS / n).is_file())
    if missing:
        raise SystemExit("Captures manquantes : " + ", ".join(missing))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip() or "inconnue"
    target = ROOT / "documentation/RAPPORT-SYNTHESE-FR.html"
    target.write_text(build(commit, revision_label()), encoding="utf-8")
    print(f"Écrit : {target}")
    if args.pdf:
        pdf = ROOT / "documentation/RAPPORT-SYNTHESE-FR.pdf"
        with tempfile.TemporaryDirectory() as directory:
            draft = Path(directory) / "rapport.pdf"
            subprocess.run([args.chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--generate-pdf-document-outline",
                            f"--user-data-dir={Path(directory) / 'chrome'}", f"--print-to-pdf={draft}", target.as_uri()],
                           capture_output=True, check=True)
            pages = count_pages(draft)
            if pages > MAX_PAGES:
                raise SystemExit(f"Le rapport fait {pages} pages, au-delà de la limite de {MAX_PAGES}")
            draft.replace(pdf)
        print(f"Écrit : {pdf} ({pages} pages)")


if __name__ == "__main__":
    sys.exit(main())
