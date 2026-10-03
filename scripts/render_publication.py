#!/usr/bin/env python3
"""Render the bilingual publication from content/{ru,en}.json.

Uses only the Python standard library. Run with --check to compare generated
Markdown with the checked-in files, or without it to regenerate them.
An optional --report PATH writes transfer and anchor checks outside the reader
documents. Excerpts, translations, context and commentary keep their source
labels; the renderer does not infer or rewrite them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://beforeword.xyz"
LABELS = {
    "ru": {
        "contents": "Содержание", "version": "Версия", "date": "Дата",
        "author": "Автор", "full": "Полный документ", "sources": "Материалы и источники",
        "statements": "Публичные заявления об ИИ", "example": "Законченный пример",
        "sourceIntro": "Здесь отдельно показаны названия материалов, ссылки, фрагменты и пояснения beforeword. Цитата сохраняет язык исходного текста; перевод обозначен отдельно. Указание источника не превращает его слова в описываемое.",
        "sourceNote": "Материалы приведены по состоянию на 3 октября 2026 года. Даты редакций и область рассматриваемых фрагментов указаны в соответствующих записях.",
        "excerpt": "Фрагмент исходного текста", "translation": "Перевод beforeword",
        "analysis": "Разбор beforeword", "home": "О репозитории", "site": "На сайте",
    },
    "en": {
        "contents": "Contents", "version": "Version", "date": "Date",
        "author": "Author", "full": "Full document", "sources": "Materials and sources",
        "statements": "Public statements about AI", "example": "Worked example",
        "sourceIntro": "Titles, links, excerpts and beforeword commentary appear separately here. Excerpts retain the language of the source; translations are identified. Naming a source does not turn its words into what they describe.",
        "sourceNote": "Materials are presented as accessed on 3 October 2026. Relevant editions and the scope of the excerpts examined are identified in the individual entries.",
        "excerpt": "Source excerpt", "translation": "beforeword translation",
        "analysis": "beforeword commentary", "home": "About this repository", "site": "On the website",
    },
}


def text(value: str) -> str:
    """Escape syntax without changing the text displayed by Markdown."""
    value = value.replace("&", "&amp;")
    value = re.sub(r"([\\`*_{}\[\]<>|])", r"\\\1", value)
    value = re.sub(r"(?m)^(\s*)([#>+\-])", r"\1\\\2", value)
    value = re.sub(r"(?m)^(\s*\d+)([.)])(?=\s)", r"\1\\\2", value)
    return value


def url(value: str) -> str:
    if value.startswith("/"):
        value = ORIGIN + value
    return quote(value, safe=":/#?&=%@+,;~.-_")


def anchor(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"Unsafe anchor: {value}")
    return f'<a name="{value}"></a>'


def link(label: str, target: str) -> str:
    return f"[{text(label)}]({url(target)})"


class Renderer:
    def __init__(self, lang: str, data: dict):
        self.lang = lang
        self.data = data
        self.labels = LABELS[lang]
        self.atoms: list[dict] = []

    def atom(self, value: str, path: str) -> str:
        result = text(value)
        self.atoms.append({"path": path, "text": value, "encoded": result})
        return result

    def block(self, block: dict, path: str, level: int = 3) -> str:
        kind = block["type"]
        atom = lambda value, key: self.atom(value, path + "." + key)
        if kind == "p":
            return atom(block["text"], "text")
        if kind == "heading":
            prefix = anchor(block["id"]) + "\n\n" if block.get("id") else ""
            return prefix + "#" * level + " " + atom(block["text"], "text")
        if kind == "example":
            parts = ["**" + atom(block["label"], "label") + "**"]
            # Separate quoted paragraphs preserve each supplied line while
            # allowing long excerpts to wrap on narrow screens.
            lines = []
            for i, value in enumerate(block["lines"]):
                lines.append("> " + atom(value, f"lines[{i}]").replace("\n", "\n> "))
            parts.append("\n>\n".join(lines))
            if block.get("caption"):
                parts.append(atom(block["caption"], "caption"))
            return "\n\n".join(parts)
        if kind == "list":
            rows = []
            for i, value in enumerate(block["items"]):
                prefix = f"{i + 1}. " if block.get("ordered") else "- "
                rows.append(prefix + atom(value, f"items[{i}]").replace("\n", "\n  "))
            return "\n\n".join(rows)
        if kind == "table":
            width = len(block["headers"])
            if any(len(row) != width for row in block["rows"]):
                raise ValueError(f"Unequal table widths at {path}")
            def cell(value: str, key: str) -> str:
                return atom(value, key).replace("\n", "<br>")
            rows = ["| " + " | ".join(cell(v, f"headers[{i}]") for i, v in enumerate(block["headers"])) + " |",
                    "| " + " | ".join("---" for _ in range(width)) + " |"]
            for i, row in enumerate(block["rows"]):
                rows.append("| " + " | ".join(cell(v, f"rows[{i}][{j}]") for j, v in enumerate(row)) + " |")
            rendered = "\n".join(rows)
            return (atom(block["caption"], "caption") + "\n\n" if block.get("caption") else "") + rendered
        if kind == "links":
            rows = []
            for i, item in enumerate(block["items"]):
                title = atom(item["title"], f"items[{i}].title")
                self.atoms.append({"path": f"{path}.items[{i}].url", "text": item["url"], "encoded": url(item["url"])})
                row = f"- [{title}]({url(item['url'])})"
                if item.get("description"):
                    row += "\n\n  " + atom(item["description"], f"items[{i}].description").replace("\n", "\n  ")
                rows.append(row)
            return "\n\n".join(rows)
        raise ValueError(f"Unsupported block {kind} at {path}")

    def blocks(self, blocks: list[dict], path: str, level: int = 3) -> str:
        return "\n\n".join(self.block(block, f"{path}[{i}]", level) for i, block in enumerate(blocks))

    def nav(self, kind: str) -> str:
        lang = self.lang
        other = "en" if lang == "ru" else "ru"
        base = "../docs/" if kind == "example" else ""
        sibling = f"worked-case.{other}.md" if kind == "example" else f"{kind}.{other}.md"
        entries = [link("English" if lang == "ru" else "Русский", sibling),
                   link(self.labels["home"], "../README.ru.md" if lang == "ru" else "../README.md")]
        for key, label in [("proposal", "full"), ("sources", "sources"), ("public-statements", "statements")]:
            if kind != key:
                entries.append(link(self.labels[label], base + f"{key}.{lang}.md"))
        if kind != "example":
            entries.append(link(self.labels["example"], f"../examples/worked-case.{lang}.md"))
        return " · ".join(entries)

    def metadata(self) -> str:
        return " · ".join([self.atom(self.data["status"], "status"),
            f'{self.labels["version"]} {self.atom(self.data["version"], "version")}',
            self.atom(self.data["date"], "date"),
            self.atom(self.data["author"], "author")])

    def proposal(self) -> str:
        parts = ["# " + self.atom(self.data["title"], "title"), self.nav("proposal"), self.metadata(),
                 self.atom(self.data["subtitle"], "subtitle"), self.atom(self.data["deck"], "deck"),
                 "## " + self.labels["contents"]]
        parts.append("\n".join(f'- [{i:02} · {text(s["title"])}](#{s["id"]})' for i, s in enumerate(self.data["sections"])))
        for i, section in enumerate(self.data["sections"]):
            path = f"sections[{i}]"
            parts.extend([anchor(section["id"]), f'## {i:02} · {self.atom(section["title"], path + ".title")}',
                          self.blocks(section["blocks"], path + ".blocks")])
        return "\n\n".join(parts) + "\n"

    def sources(self) -> str:
        parts = ["# " + self.labels["sources"], self.nav("sources"), self.metadata(),
                 self.atom(self.data["title"], "title"), self.labels["sourceIntro"], self.labels["sourceNote"],
                 "\n".join(f'- [{text(s["title"])}](#{s["id"]})' for s in self.data["sources"])]
        for i, source in enumerate(self.data["sources"]):
            path = f"sources[{i}]"
            a = lambda key: self.atom(source[key], path + "." + key)
            parts.extend([anchor(source["id"]), "## " + a("title"), a("type")])
            if source.get("note"):
                parts.append(a("note"))
            self.atoms.append({"path": path + ".url", "text": source["url"], "encoded": url(source["url"])})
            parts.append(f'<{url(source["url"])}>')
            for key in ("excerpt", "translation", "analysis"):
                if source.get(key):
                    parts.extend(["**" + self.labels[key] + "**", ("> " if key != "analysis" else "") + a(key)])
        return "\n\n".join(parts) + "\n"

    def statements(self) -> str:
        dossier = self.data["dossier"]
        parts = ["# " + self.atom(dossier["title"], "dossier.title"), self.nav("public-statements"), self.metadata(),
                 self.atom(dossier["deck"], "dossier.deck"), self.blocks(dossier["intro"], "dossier.intro"),
                 "## " + self.labels["contents"],
                 "\n".join(f'- [{text(case["title"])}](#{case["id"]})' for case in dossier["cases"])]
        for i, case in enumerate(dossier["cases"]):
            path = f"dossier.cases[{i}]"
            parts.extend([anchor(case["id"]), "## " + self.atom(case["title"], path + ".title"),
                          self.blocks(case["blocks"], path + ".blocks")])
        parts.append(self.blocks(dossier["closing"], "dossier.closing", 2))
        return "\n\n".join(parts) + "\n"

    def example(self) -> str:
        section = next(s for s in self.data["sections"] if s["id"] == "14-cases")
        start = next(i for i, b in enumerate(section["blocks"]) if b.get("id") == "14-worked-case")
        title = section["blocks"][start]
        parts = [anchor(title["id"]), "# " + self.atom(title["text"], f"sections[14].blocks[{start}].text"),
                 self.nav("example"), self.metadata()]
        # This note belongs to the standalone reading route, not to the frozen
        # publication excerpt. Keep it visibly separate from the source blocks.
        if self.lang == "ru":
            parts.extend([
                "**Пояснение к чтению · редакторская вставка**",
                "В [R8 ниже](#14-worked-outcome) прямо указано, что для этого составленного примера принято положение 4 из "
                "[раздела 13](../docs/proposal.ru.md#13-proposal). Оно начинается словами: "
                "«Не требовать признать себя написанным описанием.» Ссылки на положение 4 в дальнейшем разборе относятся к этому условию примера.",
                "---",
                "**[Текст примера · публикация 1.4, раздел 14](../docs/proposal.ru.md#14-worked-case)**",
            ])
        else:
            parts.extend([
                "**Reading note · editorial addition**",
                "[R8 below](#14-worked-outcome) explicitly states that this constructed example adopts Provision 4 from "
                "[section 13](../docs/proposal.en.md#13-proposal). Its opening requirement reads: "
                "“Do not require anyone to accept that they are the written description.” References to Provision 4 in the examination below apply that condition within the example.",
                "---",
                "**[Example text · publication 1.4, section 14](../docs/proposal.en.md#14-worked-case)**",
            ])
        parts.extend(self.block(b, f"sections[14].blocks[{i}]", 2)
                     for i, b in enumerate(section["blocks"]) if i > start)
        return "\n\n".join(parts) + "\n"


def validate(content: str, atoms: list[dict], path: str) -> dict:
    missing = [a["path"] for a in atoms if a["encoded"] not in content]
    names = re.findall(r'<a name="([^"]+)"></a>', content)
    duplicate_anchors = sorted({name for name in names if names.count(name) > 1})
    local_anchors = re.findall(r'\]\(#([^)]*)\)', content)
    missing_anchors = sorted(set(local_anchors) - set(names))
    if missing or duplicate_anchors or missing_anchors:
        raise ValueError(f"{path}: missing strings {missing}; duplicate anchors {duplicate_anchors}; missing anchors {missing_anchors}")
    return {"path": path, "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "transferred_string_count": len(atoms), "anchors": names,
            "strings": [{"source_path": a["path"], "sha256": hashlib.sha256(a["text"].encode()).hexdigest()} for a in atoms],
            "missing_strings": missing, "duplicate_anchors": duplicate_anchors, "missing_anchors": missing_anchors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check generated files without modifying them")
    parser.add_argument("--report", type=Path, help="Write a transfer report to the specified path")
    args = parser.parse_args()
    report = {"publication_version": "1.4", "source_files": {}, "documents": []}
    section_ids = {}
    for lang in ("ru", "en"):
        source = ROOT / "content" / f"{lang}.json"
        raw = source.read_bytes()
        data = json.loads(raw)
        if data["lang"] != lang or data["version"] != "1.4":
            raise ValueError("Expected publication version 1.4 with matching language")
        report["source_files"][f"content/{lang}.json"] = hashlib.sha256(raw).hexdigest()
        section_ids[lang] = [s["id"] for s in data["sections"]]
        if len(section_ids[lang]) != 21:
            raise ValueError("Expected 21 publication sections")
        for method, filename in [("proposal", f"docs/proposal.{lang}.md"), ("sources", f"docs/sources.{lang}.md"),
                                 ("statements", f"docs/public-statements.{lang}.md"), ("example", f"examples/worked-case.{lang}.md")]:
            renderer = Renderer(lang, data)
            content = getattr(renderer, method)()
            result = validate(content, renderer.atoms, filename)
            report["documents"].append(result)
            destination = ROOT / filename
            if args.check:
                if not destination.exists() or destination.read_text(encoding="utf-8") != content:
                    raise ValueError(f"Generated content differs: {filename}")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
    if section_ids["ru"] != section_ids["en"]:
        raise ValueError("The RU and EN section identifiers differ")
    report["matching_section_ids"] = section_ids["ru"]
    report["mode"] = "check" if args.check else "render"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f'{"Checked" if args.check else "Rendered"} {len(report["documents"])} documents; 21 matching sections; '
          f'{sum(d["transferred_string_count"] for d in report["documents"])} transferred strings.')


if __name__ == "__main__":
    main()
