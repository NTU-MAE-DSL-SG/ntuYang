#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TOPIC_PATTERNS = {
    "Additive Manufacturing": [
        r"\badditive manufacturing\b",
        r"\b3d[- ]?printing\b",
        r"\b3d printed\b",
        r"\bmaterial extrusion\b",
        r"\bfused deposition\b",
        r"\bfused filament\b",
        r"\bded\b",
        r"\bdirect energy deposition\b",
        r"\blaser[- ]?directed energy deposition\b",
        r"\blaser aided additive\b",
        r"\blaser additive\b",
    ],
    "Digital Twins": [
        r"\bdigital twin",
        r"\bdigital twins",
        r"\bsmart factory\b",
        r"\bsoftware-defined factory\b",
        r"\bproduction digital twin",
    ],
    "AI/ML": [
        r"\bai/ml\b",
        r"\bmachine learning\b",
        r"\bdeep learning\b",
        r"\bvision-language\b",
        r"\bdata-driven\b",
        r"\bartificial intelligence\b",
        r"\banomaly detection\b",
    ],
    "Optimization": [
        r"\boptimization\b",
        r"\boptimisation\b",
        r"\bmulti-objective\b",
        r"\bdecision-making\b",
        r"\bdecision making\b",
        r"\boperations research\b",
        r"\bsimulation\b",
    ],
    "Sensors and Monitoring": [
        r"\bsensor",
        r"\bsensors",
        r"\bmonitoring\b",
        r"\bin-situ\b",
        r"\binspection\b",
        r"\bpredictive maintenance\b",
        r"\bdefect detection\b",
    ],
    "Robotics": [
        r"\brobotics\b",
        r"\brobotic\b",
        r"\bautonomous mobile robot",
    ],
    "Sustainable Design": [
        r"\bsustainable\b",
        r"\bremanufacturing\b",
        r"\bgreen technolog",
        r"\blife cycle\b",
        r"\bend-of-life\b",
    ],
    "Product and Service Systems": [
        r"\bproduct platform\b",
        r"\bproduct family\b",
        r"\bmodular\b",
        r"\bcustomi[sz]",
        r"\bproduct-service\b",
        r"\bservice system\b",
    ],
}


def clean_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:90] or hashlib.sha1(value.encode()).hexdigest()[:10]


def extract_people() -> list[dict]:
    source = (ROOT / "landing-classic.html").read_text(errors="ignore")
    people_html = re.search(
        r'<section class="section" id="people">(.*?)</section>\s*<section',
        source,
        flags=re.S,
    )
    section = people_html.group(1) if people_html else source
    matches = re.findall(r'<a href="(pages/[^"]+)">([^<]+)</a>', section)

    people = []
    seen = set()
    current_role = "Member"
    for part in re.split(r'(<h3>.*?</h3>|<p class="role">.*?</p>|<summary>.*?</summary>|<a href="pages/[^"]+">[^<]+</a>)', section, flags=re.S):
        h3 = re.match(r"<h3>(.*?)</h3>", part, flags=re.S)
        role = re.match(r'<p class="role">(.*?)</p>', part, flags=re.S)
        summary = re.match(r"<summary>(.*?)</summary>", part, flags=re.S)
        link = re.match(r'<a href="(pages/[^"]+)">([^<]+)</a>', part)
        if role:
            current_role = clean_text(role.group(1))
        elif h3:
            nested_link = re.search(r'<a href="(pages/[^"]+)">([^<]+)</a>', h3.group(1))
            if nested_link:
                page, name = nested_link.groups()
                name = clean_text(name)
                if name and name not in seen:
                    seen.add(name)
                    people.append(
                        {
                            "id": f"person:{slug(name)}",
                            "name": name,
                            "role": current_role,
                            "page": page,
                        }
                    )
            else:
                current_role = clean_text(h3.group(1))
        elif summary:
            current_role = clean_text(summary.group(1))
        elif link:
            page, name = link.groups()
            name = clean_text(name)
            if not name or name in seen:
                continue
            seen.add(name)
            people.append(
                {
                    "id": f"person:{slug(name)}",
                    "name": name,
                    "role": current_role,
                    "page": page,
                }
            )

    if not people:
        for page, name in matches:
            name = clean_text(name)
            if name not in seen:
                seen.add(name)
                people.append({"id": f"person:{slug(name)}", "name": name, "role": "Member", "page": page})
    return people


def alias_variants(name: str) -> list[str]:
    name = name.replace("Associate Professor ", "").strip()
    parts = name.split()
    variants = set()
    if len(parts) >= 2:
        surname = parts[0]
        given = parts[1:]
        initials = ".".join(p[0] for p in given if p) + "."
        variants.add(f"{surname}, {initials}")
        variants.add(f"{surname}, {initials.replace('.', '')}")

        first = parts[0]
        last = parts[-1]
        middles = parts[1:-1]
        western_initials = ".".join(p[0] for p in [first] + middles if p) + "."
        variants.add(f"{last}, {western_initials}")
        variants.add(f"{last}, {western_initials.replace('.', '')}")
    return sorted(variants, key=len, reverse=True)


def extract_interests(person: dict) -> list[str]:
    path = ROOT / person["page"]
    if not path.exists():
        return []
    raw = path.read_text(errors="ignore")

    # Modern Prof. Moon page uses topic chips.
    chips = re.findall(r'<span>([^<]+)</span>', raw)
    if person["name"].endswith("Moon Seung Ki") and chips:
        return [clean_text(c) for c in chips if clean_text(c)]

    plain = clean_text(raw)
    match = re.search(
        r"Research Interests?:\s*(.*?)(?:\bPublication:|\bPublications:|\bPhone:|Praesent|$)",
        plain,
        flags=re.I,
    )
    if not match:
        return []
    value = match.group(1).strip(" :-")
    value = re.sub(r"\s*/p>\s*", " ", value)
    parts = re.split(r",|;|•|\band\b|\n", value)
    return [p.strip(" .:-") for p in parts if p.strip(" .:-")]


def normalize_topics(text: str) -> list[str]:
    found = []
    lower = text.lower()
    for topic, patterns in TOPIC_PATTERNS.items():
        if any(re.search(pattern, lower, flags=re.I) for pattern in patterns):
            found.append(topic)
    return found


def extract_publications() -> list[dict]:
    raw = (ROOT / "publications.html").read_text(errors="ignore")
    publications = []
    for section_match in re.finditer(r'<section class="publication-year" id="(\d{4})">(.*?)(?=<section class="publication-year"|</main>)', raw, flags=re.S):
        year = section_match.group(1)
        body = section_match.group(2)
        for li in re.findall(r"<li>(.*?)</li>", body, flags=re.S):
            line = clean_text(li)
            if not line:
                continue
            title_match = re.search(r"[“\"]([^”\"]+)[”\"]", line)
            title = title_match.group(1).strip() if title_match else line[:140]
            authors = line[: title_match.start()].strip(" ,-") if title_match else ""
            digest = hashlib.sha1(line.encode()).hexdigest()[:12]
            publications.append(
                {
                    "id": f"publication:{year}:{digest}",
                    "title": title,
                    "year": year,
                    "authors_raw": authors,
                    "citation": line,
                    "source_file": "publications.html",
                }
            )
    return publications


def build_graph() -> dict:
    people = extract_people()
    publications = extract_publications()

    nodes = []
    edges = []
    node_seen = set()

    def add_node(node: dict) -> None:
        if node["id"] in node_seen:
            return
        node_seen.add(node["id"])
        nodes.append(node)

    for person in people:
        add_node(
            {
                "id": person["id"],
                "label": person["name"],
                "type": "Person",
                "role": person["role"],
                "page": person["page"],
            }
        )

    topic_ids = {topic: f"topic:{slug(topic)}" for topic in TOPIC_PATTERNS}
    for topic, topic_id in topic_ids.items():
        add_node({"id": topic_id, "label": topic, "type": "ResearchTopic"})

    for pub in publications:
        add_node(
            {
                "id": pub["id"],
                "label": pub["title"],
                "type": "Publication",
                "year": pub["year"],
                "authors_raw": pub["authors_raw"],
            }
        )

    edge_seen = set()

    def add_edge(source: str, target: str, relation: str, confidence: float, evidence: str, source_file: str) -> None:
        key = (source, target, relation)
        if key in edge_seen:
            return
        edge_seen.add(key)
        edges.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "confidence": confidence,
                "evidence": evidence,
                "source_file": source_file,
            }
        )

    for person in people:
        interests = extract_interests(person)
        for interest in interests:
            for topic in normalize_topics(interest):
                add_edge(
                    person["id"],
                    topic_ids[topic],
                    "has_interest",
                    0.9,
                    interest,
                    person["page"],
                )

    for pub in publications:
        for person in people:
            aliases = alias_variants(person["name"])
            if aliases and any(alias in pub["citation"] for alias in aliases):
                add_edge(
                    person["id"],
                    pub["id"],
                    "authored",
                    0.95,
                    pub["citation"],
                    pub["source_file"],
                )

        topic_text = f"{pub['title']} {pub['citation']}"
        for topic in normalize_topics(topic_text):
            add_edge(
                pub["id"],
                topic_ids[topic],
                "about",
                0.78,
                pub["title"],
                pub["source_file"],
            )

    connected_ids = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
    nodes = [node for node in nodes if node["id"] in connected_ids or node["type"] == "ResearchTopic"]

    return {
        "metadata": {
            "title": "Design Sciences Laboratory Knowledge Graph",
            "generated_from": [
                "landing-classic.html",
                "pages/personal.ntu.edu.sg_skmoon_*.html",
                "publications.html",
            ],
            "method": "Evidence-first graph: author initials, personal research interests, and publication keyword topics.",
        },
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "people": sum(1 for n in nodes if n["type"] == "Person"),
            "publications": sum(1 for n in nodes if n["type"] == "Publication"),
            "topics": sum(1 for n in nodes if n["type"] == "ResearchTopic"),
            "edges": len(edges),
        },
    }


def write_dashboard(graph: dict) -> None:
    dashboard = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Knowledge Graph | Design Sciences Laboratory</title>
    <link rel="stylesheet" href="styles.css">
    <style>
      body { background: #f7f8fa; }
      .kg-shell { width: min(100% - 40px, 1320px); margin: 0 auto; padding: 32px 0 54px; }
      .kg-header { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 24px; align-items: end; margin-bottom: 22px; }
      .kg-header h1 { max-width: 780px; margin-bottom: 8px; font-size: clamp(38px, 5vw, 72px); }
      .kg-header p { max-width: 780px; color: var(--muted); }
      .kg-back { color: var(--accent); font-weight: 700; }
      .kg-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
      .kg-stat { padding: 18px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
      .kg-stat strong { display: block; color: var(--accent); font-size: 28px; line-height: 1.1; }
      .kg-stat span { color: var(--muted); font-size: 13px; font-weight: 700; text-transform: uppercase; }
      .kg-controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 16px; padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
      .kg-controls label { display: inline-flex; align-items: center; gap: 7px; color: var(--muted); font-size: 14px; font-weight: 700; }
      .kg-controls input[type="search"] { min-width: min(420px, 100%); flex: 1; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; font: inherit; }
      .kg-grid { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 16px; align-items: stretch; }
      .kg-panel { min-height: 680px; border: 1px solid var(--line); border-radius: 8px; background: #fff; overflow: hidden; }
      #graph { width: 100%; height: 720px; display: block; background: radial-gradient(circle at 20% 20%, rgba(11,87,208,.08), transparent 30%), #fff; }
      .kg-detail { padding: 20px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
      .kg-detail h2 { font-size: 24px; }
      .kg-detail p, .kg-detail li { color: var(--muted); font-size: 14px; }
      .kg-legend { display: grid; gap: 8px; margin: 16px 0 24px; }
      .kg-legend span { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: 14px; }
      .dot { width: 12px; height: 12px; border-radius: 999px; display: inline-block; }
      .kg-list { display: grid; gap: 10px; max-height: 340px; overflow: auto; padding-right: 4px; }
      .kg-list button { text-align: left; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--ink); cursor: pointer; }
      .kg-list small { display: block; color: var(--muted); }
      .node { cursor: pointer; stroke: #fff; stroke-width: 1.5; }
      .edge { stroke: #a8b1c2; stroke-opacity: .36; }
      .node-label { pointer-events: none; fill: #3c4043; font-size: 11px; paint-order: stroke; stroke: white; stroke-width: 3px; stroke-linejoin: round; }
      @media (max-width: 980px) {
        .kg-header, .kg-grid, .kg-stats { grid-template-columns: 1fr; }
        .kg-panel { min-height: 520px; }
        #graph { height: 560px; }
      }
    </style>
  </head>
  <body>
    <main class="kg-shell">
      <header class="kg-header">
        <div>
          <p class="eyebrow">Knowledge Graph Dashboard</p>
          <h1>Design Sciences Laboratory Knowledge Graph</h1>
          <p>First-pass evidence graph connecting people, publications, and research topics from the archived lab pages.</p>
        </div>
        <a class="kg-back" href="index.html">Back to homepage options</a>
      </header>

      <section class="kg-stats" aria-label="Graph summary">
        <div class="kg-stat"><strong id="stat-people">0</strong><span>People</span></div>
        <div class="kg-stat"><strong id="stat-pubs">0</strong><span>Publications</span></div>
        <div class="kg-stat"><strong id="stat-topics">0</strong><span>Topics</span></div>
        <div class="kg-stat"><strong id="stat-edges">0</strong><span>Edges</span></div>
      </section>

      <section class="kg-controls" aria-label="Graph filters">
        <input id="search" type="search" placeholder="Search people, topics, publications">
        <label><input type="checkbox" value="authored" checked> Authored</label>
        <label><input type="checkbox" value="has_interest" checked> Interests</label>
        <label><input type="checkbox" value="about" checked> Publication topics</label>
      </section>

      <section class="kg-grid">
        <div class="kg-panel">
          <svg id="graph" role="img" aria-label="Knowledge graph network"></svg>
        </div>
        <aside class="kg-detail">
          <h2 id="detail-title">Select a node</h2>
          <p id="detail-body">Click a person, publication, or topic to inspect its connections and evidence.</p>
          <div class="kg-legend">
            <span><i class="dot" style="background:#0b57d0"></i>Person</span>
            <span><i class="dot" style="background:#1e8e3e"></i>Research topic</span>
            <span><i class="dot" style="background:#fbbc04"></i>Publication</span>
          </div>
          <h3>Connected Evidence</h3>
          <div id="edge-list" class="kg-list"></div>
        </aside>
      </section>
    </main>

    <script id="kg-data" type="application/json">__GRAPH_JSON__</script>
    <script>
      const graph = JSON.parse(document.getElementById('kg-data').textContent);
      const colors = { Person: '#0b57d0', ResearchTopic: '#1e8e3e', Publication: '#fbbc04' };
      const radius = { Person: 8, ResearchTopic: 12, Publication: 5 };
      const svg = document.getElementById('graph');
      const edgeList = document.getElementById('edge-list');
      const detailTitle = document.getElementById('detail-title');
      const detailBody = document.getElementById('detail-body');
      const search = document.getElementById('search');
      const checks = [...document.querySelectorAll('.kg-controls input[type="checkbox"]')];

      document.getElementById('stat-people').textContent = graph.stats.people;
      document.getElementById('stat-pubs').textContent = graph.stats.publications;
      document.getElementById('stat-topics').textContent = graph.stats.topics;
      document.getElementById('stat-edges').textContent = graph.stats.edges;

      let selected = null;
      let positions = new Map();

      function visibleGraph() {
        const active = new Set(checks.filter(c => c.checked).map(c => c.value));
        const q = search.value.trim().toLowerCase();
        let edges = graph.edges.filter(e => active.has(e.relation));
        let ids = new Set(edges.flatMap(e => [e.source, e.target]));
        let nodes = graph.nodes.filter(n => ids.has(n.id));
        if (q) {
          const matching = new Set(nodes.filter(n => (n.label || '').toLowerCase().includes(q)).map(n => n.id));
          edges = edges.filter(e => matching.has(e.source) || matching.has(e.target));
          ids = new Set(edges.flatMap(e => [e.source, e.target]));
          matching.forEach(id => ids.add(id));
          nodes = graph.nodes.filter(n => ids.has(n.id));
        }
        return { nodes, edges };
      }

      function simulate(nodes, edges, width, height) {
        const nodeMap = new Map(nodes.map((node, i) => {
          const old = positions.get(node.id);
          const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
          return [node.id, {
            ...node,
            x: old?.x ?? width / 2 + Math.cos(angle) * width * 0.28,
            y: old?.y ?? height / 2 + Math.sin(angle) * height * 0.28,
            vx: 0,
            vy: 0,
          }];
        }));
        const links = edges.map(e => ({ ...e, sourceNode: nodeMap.get(e.source), targetNode: nodeMap.get(e.target) })).filter(e => e.sourceNode && e.targetNode);
        const nodeValues = [...nodeMap.values()];
        for (let tick = 0; tick < 220; tick++) {
          for (let i = 0; i < nodeValues.length; i++) {
            for (let j = i + 1; j < nodeValues.length; j++) {
              const a = nodeValues[i], b = nodeValues[j];
              let dx = a.x - b.x, dy = a.y - b.y;
              let d2 = dx * dx + dy * dy || 0.01;
              const force = Math.min(900 / d2, 1.8);
              dx = dx || 0.1;
              dy = dy || 0.1;
              a.vx += dx * force * 0.012; a.vy += dy * force * 0.012;
              b.vx -= dx * force * 0.012; b.vy -= dy * force * 0.012;
            }
          }
          for (const link of links) {
            const a = link.sourceNode, b = link.targetNode;
            const dx = b.x - a.x, dy = b.y - a.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const target = link.relation === 'authored' ? 92 : 118;
            const force = (dist - target) * 0.004;
            const fx = dx / dist * force, fy = dy / dist * force;
            a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
          }
          for (const n of nodeValues) {
            n.vx += (width / 2 - n.x) * 0.002;
            n.vy += (height / 2 - n.y) * 0.002;
            n.vx *= 0.84; n.vy *= 0.84;
            n.x = Math.max(18, Math.min(width - 18, n.x + n.vx));
            n.y = Math.max(18, Math.min(height - 18, n.y + n.vy));
          }
        }
        positions = new Map(nodeValues.map(n => [n.id, { x: n.x, y: n.y }]));
        return { nodes: nodeValues, edges: links };
      }

      function draw() {
        const { nodes, edges } = visibleGraph();
        const rect = svg.getBoundingClientRect();
        const width = Math.max(rect.width, 640);
        const height = Math.max(rect.height, 480);
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        const layout = simulate(nodes, edges, width, height);
        svg.innerHTML = '';
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        svg.appendChild(g);

        for (const e of layout.edges) {
          const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          line.setAttribute('x1', e.sourceNode.x); line.setAttribute('y1', e.sourceNode.y);
          line.setAttribute('x2', e.targetNode.x); line.setAttribute('y2', e.targetNode.y);
          line.setAttribute('class', 'edge');
          line.setAttribute('stroke-width', e.relation === 'authored' ? 1.1 : 1.6);
          g.appendChild(line);
        }

        const showLabels = layout.nodes.length < 140;
        for (const n of layout.nodes) {
          const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', n.x); circle.setAttribute('cy', n.y);
          circle.setAttribute('r', radius[n.type] || 6);
          circle.setAttribute('fill', colors[n.type] || '#5f6368');
          circle.setAttribute('class', 'node');
          circle.addEventListener('click', () => selectNode(n));
          g.appendChild(circle);
          if (showLabels || n.type !== 'Publication') {
            const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            label.setAttribute('x', n.x + 10); label.setAttribute('y', n.y + 4);
            label.setAttribute('class', 'node-label');
            label.textContent = n.label.length > 34 ? n.label.slice(0, 32) + '...' : n.label;
            g.appendChild(label);
          }
        }
        if (selected) selectNode(selected, false);
      }

      function selectNode(node, redrawEdges = true) {
        selected = node;
        const related = graph.edges.filter(e => e.source === node.id || e.target === node.id);
        detailTitle.textContent = node.label;
        detailBody.textContent = `${node.type}${node.role ? ' · ' + node.role : ''}${node.year ? ' · ' + node.year : ''}`;
        edgeList.innerHTML = '';
        if (!related.length) {
          edgeList.innerHTML = '<p>No visible evidence edges.</p>';
          return;
        }
        for (const edge of related.slice(0, 80)) {
          const otherId = edge.source === node.id ? edge.target : edge.source;
          const other = graph.nodes.find(n => n.id === otherId);
          const btn = document.createElement('button');
          btn.innerHTML = `<strong>${edge.relation}</strong> <small>${other ? other.label : otherId}</small><small>confidence ${edge.confidence} · ${edge.source_file}</small>`;
          btn.title = edge.evidence;
          if (other) btn.addEventListener('click', () => selectNode(other));
          edgeList.appendChild(btn);
        }
      }

      checks.forEach(c => c.addEventListener('change', draw));
      search.addEventListener('input', () => draw());
      window.addEventListener('resize', () => draw());
      draw();
    </script>
  </body>
</html>
"""
    payload = json.dumps(graph, ensure_ascii=False)
    dashboard = dashboard.replace("__GRAPH_JSON__", payload.replace("</", "<\\/"))
    (ROOT / "knowledge-graph.html").write_text(dashboard, encoding="utf-8")


def main() -> None:
    graph = build_graph()
    (ROOT / "kg-data.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    write_dashboard(graph)
    print(json.dumps(graph["stats"], indent=2))


if __name__ == "__main__":
    main()
