#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "ntuYang-collaboration-network/1.0 (mailto:example@example.com)"


def clean_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if normalized:
        return normalized[:110]
    return hashlib.sha1(value.encode()).hexdigest()[:12]


def normalize_title(value: str) -> str:
    value = html.unescape(value or "").lower()
    value = re.sub(r"[\u2018\u2019\u201c\u201d\"'`]", "", value)
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def title_similarity(left: str, right: str) -> float:
    left_norm = normalize_title(left)
    right_norm = normalize_title(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def request_json(url: str, cache_path: Path, delay: float) -> dict:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    payload = ""
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                payload = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 5:
                raise
            time.sleep(12 * (attempt + 1))
        except TimeoutError:
            if attempt == 5:
                raise
            time.sleep(6 * (attempt + 1))

    cache_path.write_text(payload)
    if delay:
        time.sleep(delay)
    return json.loads(payload)


def load_kg() -> dict:
    return json.loads((ROOT / "kg-data.json").read_text())


def load_internal_people(data: dict) -> list[dict]:
    return [node for node in data.get("nodes", []) if node.get("type") == "Person"]


def load_publications(data: dict) -> list[dict]:
    pubs = [node for node in data.get("nodes", []) if node.get("type") == "Publication"]
    return sorted(pubs, key=lambda pub: (-int(pub.get("year", 0)), pub.get("label", "")))


def person_aliases(label: str) -> set[str]:
    name = label.replace("Associate Professor ", "").strip()
    parts = [part for part in name.split() if part]
    aliases = {normalize_person_name(name)}
    if len(parts) >= 2:
        first = parts[0]
        last = parts[-1]
        middle = parts[1:-1]
        aliases.add(f"{last.lower()}:{''.join(p[0].lower() for p in [first] + middle)}")
        aliases.add(f"{last.lower()}:{'.'.join(p[0].lower() for p in [first] + middle)}")
        aliases.add(f"{first.lower()}:{''.join(p[0].lower() for p in parts[1:])}")
        aliases.add(f"{first.lower()}:{'.'.join(p[0].lower() for p in parts[1:])}")
        if len(parts) >= 3:
            surname = parts[0]
            given = parts[1:]
            aliases.add(f"{surname.lower()}:{''.join(p[0].lower() for p in given)}")
            aliases.add(f"{surname.lower()}:{'.'.join(p[0].lower() for p in given)}")
    return aliases


def normalize_person_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def citation_author_key(author: str) -> str:
    author = author.replace("*", "").strip(" ,.")
    match = re.match(r"^(.+?),\s*([A-Z][A-Z.\s-]*)$", author)
    if match:
        surname = re.sub(r"[^a-zA-Z]+", "", match.group(1)).lower()
        initials = re.sub(r"[^A-Z]+", "", match.group(2)).lower()
        return f"{surname}:{initials}"
    return normalize_person_name(author)


def display_author(author: str) -> str:
    return re.sub(r"\s+", " ", author.replace("*", "").strip(" ,."))


def parse_authors(authors_raw: str) -> list[dict]:
    value = html.unescape(authors_raw or "")
    value = value.replace(" and ", ", ")
    value = value.replace("; and ", ", ")
    value = re.sub(r"\s+", " ", value)
    pattern = re.compile(
        r"([A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)*),\s*([A-Z](?:\.?\s*[A-Z])*(?:\.|)(?:-[A-Z]\.|))(?![A-Za-z])"
    )
    authors = []
    for match in pattern.finditer(value):
        raw = f"{match.group(1)}, {match.group(2)}"
        authors.append({"raw": display_author(raw), "key": citation_author_key(raw)})
    if ";" in value:
        full_name_pattern = re.compile(r"^\s*([A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)*),\s*([A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)*)\s*$")
        for part in value.split(";"):
            match = full_name_pattern.match(part.strip(" ,-"))
            if not match:
                continue
            surname = match.group(1)
            given = match.group(2)
            raw = f"{surname}, {given}"
            initials = "".join(piece[0].lower() for piece in re.findall(r"[A-Z][A-Za-z'’.-]*", given))
            authors.append({"raw": display_author(raw), "key": f"{surname.lower()}:{initials}"})
    seen = set()
    unique = []
    for author in authors:
        if author["key"] in seen:
            continue
        seen.add(author["key"])
        unique.append(author)
    return unique


def extract_archive_citations() -> list[dict]:
    path = ROOT / "pages" / "personal.ntu.edu.sg_skmoon_publication.html"
    raw = path.read_text(errors="ignore")
    pieces = re.split(r"<h2>(\d{4})</h2>", raw)
    citations = []
    for index in range(1, len(pieces), 2):
        year = int(pieces[index])
        block = pieces[index + 1]
        for part in re.split(r"<p>", block):
            line = clean_text(part)
            line = re.sub(r"^\s*-\s*", "", line).strip()
            if not line:
                continue
            match = re.search(r"[“\"]([^”\"]+)[”\"]", line)
            if not match:
                match = re.search(r"[‘']([^’']+)[’']", line)
            if match:
                title = match.group(1).strip().rstrip(".,")
                authors = line[: match.start()].strip(" ,-")
            elif "“" in line or "‘" in line:
                mark = "“" if "“" in line else "‘"
                authors, rest = line.split(mark, 1)
                title = re.split(
                    r",\s+(?:Virtual and Physical Prototyping|International Journal|Journal of|Materials|Materialia|Additive Manufacturing|IEEE|JOM|Materials Science|Rapid Prototyping|The International|Applied Sciences|ASME|Proceedings|International Conference)",
                    rest,
                    maxsplit=1,
                )[0].strip().rstrip(".,")
                authors = authors.strip(" ,-")
            else:
                # Some archived conference entries omit title quotation marks.
                author_matches = list(
                    re.finditer(
                        r"([A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)*),\s*([A-Z](?:\.[A-Z])*(?:\.|)(?:-[A-Z]\.|))",
                        line,
                    )
                )
                if not author_matches:
                    continue
                authors = line[: author_matches[-1].end()].strip(" ,-")
                rest = line[author_matches[-1].end() :].strip(" ,-")
                title = re.split(
                    r",\s+(?:IEEE|International Conference|Proceedings|ASME|Journal|Vol\.|pp\.)",
                    rest,
                    maxsplit=1,
                )[0].strip(" ,-")
            citations.append(
                {
                    "year": year,
                    "title": title,
                    "authors": authors,
                    "citation": line,
                    "article_no": extract_article_no(line),
                    "paper_no": extract_paper_no(line),
                    "doi": extract_doi(line),
                }
            )
    return citations


def extract_doi(value: str) -> str | None:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", value, flags=re.I)
    return match.group(0).rstrip(".,;)") if match else None


def extract_article_no(value: str) -> str | None:
    match = re.search(r"\b(?:Article|No\.|p\.|pp\.|Paper ID:?)\s*([A-Za-z]?\d{2,}|e\d{5,})\b", value, flags=re.I)
    return match.group(1) if match else None


def extract_paper_no(value: str) -> str | None:
    match = re.search(r"\b(?:IDETC|DETC|IMECE|MSEC|ISFA|CASE|ICED|ICPR|CIRP|SMASIS)[A-Z0-9 -]*\d{3,}\b", value)
    return re.sub(r"\s+", "", match.group(0)) if match else None


def best_archive_match(pub: dict, citations: list[dict]) -> dict:
    title = pub.get("label", "").rstrip(".,")
    year = int(pub.get("year", 0))
    best = {}
    best_score = 0.0
    for citation in citations:
        if citation["year"] != year:
            continue
        if citation["citation"].startswith(title):
            return citation
        score = title_similarity(title, citation["title"])
        if score > best_score:
            best = citation
            best_score = score
    return best if best_score >= 0.9 else {}


def crossref_lookup(pub: dict, archive: dict, delay: float) -> dict:
    title = pub.get("label", "").rstrip(".,")
    first_author = (pub.get("authors_raw") or archive.get("authors") or "").split(",")[0]
    params = {
        "query.bibliographic": " ".join([title, first_author, str(pub.get("year", ""))]),
        "rows": "5",
        "select": "DOI,title,published-print,published-online,published,issued,container-title,URL,type,score",
    }
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    cache = ROOT / ".cache" / "collaboration-network" / "crossref" / f"{slug(title)}.json"
    data = request_json(url, cache, delay)
    best = {}
    best_score = 0.0
    for item in data.get("message", {}).get("items", []):
        candidate_title = (item.get("title") or [""])[0]
        score = title_similarity(title, candidate_title)
        if score > best_score:
            best_score = score
            best = {
                "doi": item.get("DOI"),
                "title": candidate_title,
                "source": "crossref",
                "title_similarity": round(score, 4),
                "venue": (item.get("container-title") or [""])[0],
                "url": item.get("URL"),
            }
    return best


def openalex_lookup(pub: dict, doi: str | None, delay: float) -> dict:
    title = pub.get("label", "").rstrip(".,")
    if doi:
        doi_id = doi.replace("https://doi.org/", "")
        url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi_id)}?mailto=example@example.com"
        cache_name = slug(doi_id)
    else:
        params = {"search": title, "per-page": "5", "mailto": "example@example.com"}
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        cache_name = slug(title)
    cache = ROOT / ".cache" / "collaboration-network" / "openalex" / f"{cache_name}.json"
    try:
        data = request_json(url, cache, delay)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        raise
    if "results" not in data:
        data = {"results": [data]}

    best = {}
    best_score = 0.0
    for item in data.get("results", []):
        candidate_title = item.get("display_name") or item.get("title") or ""
        score = title_similarity(title, candidate_title)
        year_delta = abs((item.get("publication_year") or 0) - int(pub.get("year", 0)))
        if score > best_score and year_delta <= 2:
            best_score = score
            best = item | {"_title_similarity": round(score, 4)}
    return best if best_score >= 0.82 else {}


def add_node(nodes: dict, node: dict) -> None:
    nodes.setdefault(node["id"], node)


def add_edge(edges: dict, source: str, target: str, edge_type: str, evidence: dict | None = None) -> None:
    key = f"{source}|{target}|{edge_type}"
    if key in edges:
        return
    edges[key] = {"source": source, "target": target, "type": edge_type, "evidence": evidence or {}}


def merge_node_metadata(base: dict, incoming: dict) -> dict:
    merged = dict(base)
    for key, value in incoming.items():
        if key == "id" or value in (None, "", []):
            continue
        if key not in merged or merged[key] in (None, "", []):
            merged[key] = value
        elif key in {"source_key", "matched_local_author_key"} and merged[key] != value:
            existing = merged.get("source_keys") or [merged[key]]
            if value not in existing:
                existing.append(value)
            merged["source_keys"] = existing
    merged_from = list(merged.get("merged_from", []))
    if incoming.get("id") and incoming["id"] != merged.get("id") and incoming["id"] not in merged_from:
        merged_from.append(incoming["id"])
    if merged_from:
        merged["merged_from"] = merged_from
    return merged


def merge_external_researcher_nodes(nodes: dict, edges: dict) -> tuple[dict, dict, int]:
    external_nodes = [node for node in nodes.values() if node.get("type") == "ExternalResearcher"]
    canonical_by_oa: dict[str, str] = {}
    alias: dict[str, str] = {}

    for node in external_nodes:
        openalex_id = node.get("openalex_id")
        if not openalex_id:
            continue
        canonical = canonical_by_oa.setdefault(openalex_id, node["id"])
        if canonical != node["id"]:
            alias[node["id"]] = canonical

    key_to_oa_node: dict[str, str] = {}
    for node in external_nodes:
        if not node.get("openalex_id"):
            continue
        for key in [node.get("matched_local_author_key"), *(node.get("source_keys") or [])]:
            if key:
                key_to_oa_node[key.replace(".", "")] = alias.get(node["id"], node["id"])

    for node in external_nodes:
        source_key = node.get("source_key")
        if node.get("openalex_id") or not source_key:
            continue
        canonical = key_to_oa_node.get(source_key.replace(".", ""))
        if canonical and canonical != node["id"]:
            alias[node["id"]] = canonical

    if not alias:
        return nodes, edges, 0

    merged_nodes: dict[str, dict] = {}
    for node_id, node in nodes.items():
        canonical = alias.get(node_id, node_id)
        node_to_merge = node | {"id": canonical}
        if canonical in merged_nodes:
            merged_nodes[canonical] = merge_node_metadata(merged_nodes[canonical], node)
        else:
            merged_nodes[canonical] = node_to_merge

    merged_edges: dict[str, dict] = {}
    for edge in edges.values():
        source = alias.get(edge["source"], edge["source"])
        target = alias.get(edge["target"], edge["target"])
        if source == target:
            continue
        key = f"{source}|{target}|{edge['type']}"
        if key in merged_edges:
            continue
        merged_edges[key] = edge | {"source": source, "target": target}

    return merged_nodes, merged_edges, len(alias)


def merge_named_same_affiliation_nodes(nodes: dict, edges: dict) -> tuple[dict, dict, int]:
    target_names = {"yong jin yoon", "kyung tae kim"}
    affiliation_by_author: dict[str, set[str]] = {}
    for edge in edges.values():
        if edge["type"] != "affiliated_with":
            continue
        source = nodes.get(edge["source"])
        target = nodes.get(edge["target"])
        if not source or not target:
            continue
        if source.get("type") == "ExternalResearcher" and target.get("type") == "Institution":
            affiliation_by_author.setdefault(source["id"], set()).add(target["id"])

    grouped: dict[str, list[dict]] = {name: [] for name in target_names}
    for node in nodes.values():
        if node.get("type") != "ExternalResearcher":
            continue
        name = normalize_person_name(node.get("label", "").replace("‐", "-"))
        if name in grouped:
            grouped[name].append(node)

    alias: dict[str, str] = {}
    for name, group in grouped.items():
        if len(group) < 2:
            continue
        connected_components: list[list[dict]] = []
        remaining = group[:]
        while remaining:
            seed = remaining.pop(0)
            component = [seed]
            changed = True
            while changed:
                changed = False
                for node in remaining[:]:
                    if any(affiliation_by_author.get(node["id"], set()) & affiliation_by_author.get(existing["id"], set()) for existing in component):
                        component.append(node)
                        remaining.remove(node)
                        changed = True
            connected_components.append(component)

        for component in connected_components:
            if len(component) < 2:
                continue
            canonical = sorted(
                component,
                key=lambda node: (
                    0 if node.get("openalex_id") else 1,
                    -sum(1 for edge in edges.values() if edge["source"] == node["id"] and edge["type"] == "authored"),
                    node["id"],
                ),
            )[0]["id"]
            for node in component:
                if node["id"] != canonical:
                    alias[node["id"]] = canonical

    if not alias:
        return nodes, edges, 0

    merged_nodes: dict[str, dict] = {}
    for node_id, node in nodes.items():
        canonical = alias.get(node_id, node_id)
        incoming = node | {"id": canonical}
        if node.get("openalex_id"):
            existing_ids = list(merged_nodes.get(canonical, {}).get("openalex_ids", []))
            if node["openalex_id"] not in existing_ids:
                existing_ids.append(node["openalex_id"])
            incoming["openalex_ids"] = existing_ids
        if canonical in merged_nodes:
            merged_nodes[canonical] = merge_node_metadata(merged_nodes[canonical], node)
            if incoming.get("openalex_ids"):
                merged_nodes[canonical]["openalex_ids"] = sorted(set(merged_nodes[canonical].get("openalex_ids", []) + incoming["openalex_ids"]))
        else:
            merged_nodes[canonical] = incoming

    merged_edges: dict[str, dict] = {}
    for edge in edges.values():
        source = alias.get(edge["source"], edge["source"])
        target = alias.get(edge["target"], edge["target"])
        if source == target:
            continue
        key = f"{source}|{target}|{edge['type']}"
        if key in merged_edges:
            continue
        merged_edges[key] = edge | {"source": source, "target": target}
    return merged_nodes, merged_edges, len(alias)


def match_internal_author(author_key: str, people_aliases: dict[str, str]) -> str | None:
    compact = author_key.replace(".", "")
    direct = people_aliases.get(author_key) or people_aliases.get(compact)
    if direct or ":" not in compact:
        return direct
    surname, initials = compact.split(":", 1)
    if not initials:
        return None
    candidates = set()
    for alias, person_id in people_aliases.items():
        alias_compact = alias.replace(".", "")
        if ":" not in alias_compact:
            continue
        alias_surname, alias_initials = alias_compact.split(":", 1)
        if alias_surname == surname and alias_initials.startswith(initials):
            candidates.add(person_id)
    return next(iter(candidates)) if len(candidates) == 1 else None


def openalex_author_key(name: str) -> str:
    parts = normalize_person_name(name).split()
    if len(parts) < 2:
        return normalize_person_name(name)
    return f"{parts[-1]}:{''.join(part[0] for part in parts[:-1])}"


def build_network(enrich: bool, delay: float, limit: int | None) -> tuple[dict, list[dict]]:
    kg = load_kg()
    people = load_internal_people(kg)
    publications = load_publications(kg)
    if limit:
        publications = publications[:limit]
    archive_citations = extract_archive_citations()

    people_aliases = {}
    for person in people:
        for alias in person_aliases(person["label"]):
            people_aliases[alias.replace(".", "")] = person["id"]
            people_aliases[alias] = person["id"]

    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    rows: list[dict] = []

    lab_institution_id = "institution:nanyang-technological-university"
    add_node(nodes, {"id": lab_institution_id, "label": "Nanyang Technological University", "type": "Institution", "kind": "lab"})
    for person in people:
        add_node(nodes, person | {"kind": "internal"})
        add_edge(edges, person["id"], lab_institution_id, "member_of", {"source": "site people page"})

    for index, pub in enumerate(publications, start=1):
        archive = best_archive_match(pub, archive_citations)
        title = archive.get("title") or pub.get("label", "").rstrip(".,")
        lookup_pub = pub | {"label": title}
        local_doi = archive.get("doi")
        crossref = crossref_lookup(lookup_pub, archive, delay) if enrich else {}
        crossref_conf = crossref.get("title_similarity", 0)
        doi = local_doi or (crossref.get("doi") if crossref_conf >= 0.9 else None)
        openalex = openalex_lookup(lookup_pub, doi, delay) if enrich else {}
        openalex_doi = (openalex.get("doi") or "").replace("https://doi.org/", "") or None
        if not doi and openalex.get("_title_similarity", 0) >= 0.9:
            doi = openalex_doi

        pub_node = {
            **pub,
            "label": title,
            "doi": doi,
            "doi_url": f"https://doi.org/{doi}" if doi else "",
            "openalex_id": openalex.get("id"),
            "article_no": archive.get("article_no"),
            "paper_no": archive.get("paper_no"),
            "kind": "publication",
        }
        add_node(nodes, pub_node)

        parsed_authors = parse_authors(pub.get("authors_raw") or archive.get("authors", ""))
        parsed_author_keys = {author["key"]: author for author in parsed_authors}
        author_nodes_for_pub = set()

        for author in parsed_authors:
            internal_id = match_internal_author(author["key"], people_aliases)
            if internal_id:
                add_edge(edges, internal_id, pub["id"], "authored", {"source": "local citation author list", "author": author["raw"]})
                author_nodes_for_pub.add(internal_id)
            else:
                external_id = f"external-author:{slug(author['key'])}"
                add_node(nodes, {"id": external_id, "label": author["raw"], "type": "ExternalResearcher", "kind": "external", "source_key": author["key"]})
                add_edge(edges, external_id, pub["id"], "authored", {"source": "local citation author list"})
                author_nodes_for_pub.add(external_id)

        if openalex:
            for authorship in openalex.get("authorships", []):
                author = authorship.get("author") or {}
                display = author.get("display_name") or ""
                if not display:
                    continue
                oa_key = openalex_author_key(display)
                internal_id = match_internal_author(oa_key, people_aliases)
                matched_key = None
                if oa_key in parsed_author_keys:
                    matched_key = oa_key
                else:
                    compact_oa_key = oa_key.replace(".", "")
                    matched_key = next((key for key in parsed_author_keys if key.replace(".", "") == compact_oa_key), None)
                author_id = internal_id or f"external-author:{slug(author.get('id') or display)}"
                if internal_id:
                    add_edge(edges, internal_id, pub["id"], "authored", {"source": "OpenAlex authorship", "openalex_author_id": author.get("id")})
                else:
                    add_node(
                        nodes,
                        {
                            "id": author_id,
                            "label": display,
                            "type": "ExternalResearcher",
                            "kind": "external",
                            "openalex_id": author.get("id"),
                            "matched_local_author_key": matched_key,
                        },
                    )
                    add_edge(edges, author_id, pub["id"], "authored", {"source": "OpenAlex authorship"})
                author_nodes_for_pub.add(author_id)

                for institution in authorship.get("institutions", []):
                    institution_name = institution.get("display_name")
                    if not institution_name:
                        continue
                    institution_id = f"institution:{slug(institution.get('id') or institution_name)}"
                    add_node(
                        nodes,
                        {
                            "id": institution_id,
                            "label": institution_name,
                            "type": "Institution",
                            "kind": "institution",
                            "openalex_id": institution.get("id"),
                            "country_code": institution.get("country_code"),
                        },
                    )
                    add_edge(edges, author_id, institution_id, "affiliated_with", {"source": "OpenAlex authorship institution"})
                    add_edge(edges, pub["id"], institution_id, "associated_institution", {"source": "OpenAlex authorship institution"})

        rows.append(
            {
                "local_id": pub["id"],
                "year": pub.get("year"),
                "title": title,
                "doi": doi or "",
                "openalex_id": openalex.get("id") or "",
                "paper_no": archive.get("paper_no") or "",
                "article_no": archive.get("article_no") or "",
                "crossref_candidate_doi": crossref.get("doi") or "",
                "crossref_title_similarity": crossref.get("title_similarity", ""),
                "openalex_title_similarity": openalex.get("_title_similarity", ""),
                "local_author_count": len(parsed_authors),
                "network_author_nodes": len(author_nodes_for_pub),
            }
        )
        print(f"[{index:03d}/{len(publications):03d}] doi={doi or '-'} oa={openalex.get('id') or '-'} authors={len(author_nodes_for_pub)}")

    nodes, edges, merged_external_nodes = merge_external_researcher_nodes(nodes, edges)
    nodes, edges, merged_named_same_affiliation_nodes = merge_named_same_affiliation_nodes(nodes, edges)

    graph = {
        "metadata": {
            "description": "Researcher-publication-institution collaboration network for NTU Design Sciences Laboratory.",
            "sources": ["kg-data.json", "pages/personal.ntu.edu.sg_skmoon_publication.html", "Crossref API", "OpenAlex API"],
            "enriched": enrich,
            "merged_external_researcher_nodes": merged_external_nodes,
            "merged_named_same_affiliation_nodes": merged_named_same_affiliation_nodes,
        },
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "stats": {},
    }
    graph["stats"] = {
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "publications": sum(1 for n in graph["nodes"] if n.get("type") == "Publication"),
        "internal_researchers": sum(1 for n in graph["nodes"] if n.get("type") == "Person"),
        "external_researchers": sum(1 for n in graph["nodes"] if n.get("type") == "ExternalResearcher"),
        "institutions": sum(1 for n in graph["nodes"] if n.get("type") == "Institution"),
        "doi_count": sum(1 for row in rows if row["doi"]),
        "openalex_count": sum(1 for row in rows if row["openalex_id"]),
        "paper_no_count": sum(1 for row in rows if row["paper_no"]),
        "article_no_count": sum(1 for row in rows if row["article_no"]),
    }
    return graph, rows


def write_outputs(graph: dict, rows: list[dict]) -> None:
    (ROOT / "collaboration-network.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n")
    with (ROOT / "publication-identifiers.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (ROOT / "publication-identifiers.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")


def refresh_graph_stats(graph: dict, rows: list[dict] | None = None) -> None:
    graph["stats"] = {
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "publications": sum(1 for n in graph["nodes"] if n.get("type") == "Publication"),
        "internal_researchers": sum(1 for n in graph["nodes"] if n.get("type") == "Person"),
        "external_researchers": sum(1 for n in graph["nodes"] if n.get("type") == "ExternalResearcher"),
        "institutions": sum(1 for n in graph["nodes"] if n.get("type") == "Institution"),
        "doi_count": sum(1 for row in rows or [] if row.get("doi")),
        "openalex_count": sum(1 for row in rows or [] if row.get("openalex_id")),
        "paper_no_count": sum(1 for row in rows or [] if row.get("paper_no")),
        "article_no_count": sum(1 for row in rows or [] if row.get("article_no")),
    }


def merge_existing_outputs() -> tuple[dict, list[dict]]:
    graph = json.loads((ROOT / "collaboration-network.json").read_text())
    rows = json.loads((ROOT / "publication-identifiers.json").read_text())
    nodes = {node["id"]: node for node in graph["nodes"]}
    edges = {f"{edge['source']}|{edge['target']}|{edge['type']}": edge for edge in graph["edges"]}
    nodes, edges, merged_external_nodes = merge_external_researcher_nodes(nodes, edges)
    nodes, edges, merged_named_same_affiliation_nodes = merge_named_same_affiliation_nodes(nodes, edges)
    graph["nodes"] = list(nodes.values())
    graph["edges"] = list(edges.values())
    graph.setdefault("metadata", {})["merged_external_researcher_nodes"] = merged_external_nodes
    graph.setdefault("metadata", {})["merged_named_same_affiliation_nodes"] = merged_named_same_affiliation_nodes

    authors_by_publication: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        if edge["type"] != "authored":
            continue
        authors_by_publication.setdefault(edge["target"], set()).add(edge["source"])
    for row in rows:
        row["network_author_nodes"] = len(authors_by_publication.get(row["local_id"], set()))

    refresh_graph_stats(graph, rows)
    write_outputs(graph, rows)
    return graph, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-enrich", action="store_true", help="Skip Crossref/OpenAlex API lookups.")
    parser.add_argument("--merge-existing", action="store_true", help="Merge duplicate external researcher nodes in existing outputs.")
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.merge_existing:
        graph, _rows = merge_existing_outputs()
        print(json.dumps(graph["stats"], indent=2))
        return
    graph, rows = build_network(not args.no_enrich, args.delay, args.limit)
    write_outputs(graph, rows)
    print(json.dumps(graph["stats"], indent=2))


if __name__ == "__main__":
    main()
