"""Houdini document lightweight index system (RAG).

O(1) dict-hash lookup for node/vex/hom, TXT knowledge base with
keyword scoring, auto-retrieval for injecting docs into AI context.
No external dependencies.
"""
from __future__ import annotations

import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class NodeDoc:
    node_type: str; context: str; title: str
    description: str; parameters: list

@dataclass
class VexDoc:
    name: str; signature: str; description: str; category: str

@dataclass
class HomDoc:
    name: str; doc_type: str; signature: str; description: str

@dataclass
class KnowledgeChunk:
    title: str; content: str; source: str; keywords: List[str]


class HoudiniDocIndex:
    """Houdini document index with O(1) dict lookup."""

    _STOP_WORDS = frozenset({
        "the","a","an","is","are","was","were","be","been","being","have","has",
        "had","do","does","did","will","would","could","should","may","might",
        "can","shall","to","of","in","for","on","with","at","by","from","as",
        "into","through","about","after","before","between","under","above",
        "up","down","out","off","over","then","than","so","no","not","only",
        "very","just","that","this","but","and","or","if","it","its","all",
        "each","every","both","few","more","most","some","any","how","what",
        "which","who","when","where","why","i","you","he","she","we","they",
        "me","him","her","us","my","your","his","our","their","new","use",
        "get","set","run","add","create","make","node","want","need","try",
        "like","also","now","one","two","using","used","function","point",
        "points","value","values","type","name","input","output","result",
        "data","file","string","int","float","vector","matrix","array","list",
        "true","false","none","null","self","return",
    })

    _KB_HINTS = frozenset({
        "attribute","vex","@P","@N","@Cd","pscale","orient","snippet",
        "wrangle","noise","copy","scatter","run over","nearpoint","pcfind",
        "addpoint","setpointattrib","hou.","python","hscript",
        "heightfield","terrain","height","erosion","mask","layer",
        "copernicus","cop","image","texture","composite","filter","gpu",
        "mpm","simulation","solver","snow","soil","mud","concrete","rubber",
        "jello","sand","machine learning","onnx","labs","sidefx labs",
        "game","gamedev","baker","bake","lod","impostor","flowmap","osm",
        "photogrammetry","wfc","wave function","tree","pivot painter",
        "unreal","fbx",
    })

    def __init__(self, help_dir: Optional[str] = None):
        self._help_dir = self._resolve_help_dir(help_dir)
        self.node_index: Dict[str, NodeDoc] = {}
        self.vex_index: Dict[str, VexDoc] = {}
        self.hom_index: Dict[str, HomDoc] = {}
        self.knowledge_chunks: List[KnowledgeChunk] = []
        self._node_aliases: Dict[str, str] = {}
        self._vex_categories: Dict[str, List[str]] = {}
        self._all_node_types: Optional[Set[str]] = None
        self._cache_dir = Path.home() / ".houdini_ai_agent" / "cache" / "doc_index"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._doc_dir = Path(__file__).parent.parent.parent / "Doc"
        self._load_or_build()
        self._load_knowledge_base()

    # ----------------------------------------------------------
    # Help directory discovery
    # ----------------------------------------------------------

    @staticmethod
    def _resolve_help_dir(help_dir: Optional[str]) -> Optional[Path]:
        zips = ("nodes.zip", "vex.zip", "hom.zip")
        def _ok(d: Path) -> bool:
            return d.is_dir() and any((d / z).exists() for z in zips)

        if help_dir and _ok(Path(help_dir)):
            return Path(help_dir)
        bundled = Path(__file__).parent.parent.parent / "Doc"
        if _ok(bundled):
            return bundled
        hfs = os.environ.get("HFS")
        if hfs and _ok(Path(hfs) / "houdini" / "help"):
            return Path(hfs) / "houdini" / "help"
        try:
            import hou  # type: ignore
            hfs_val = hou.getenv("HFS", "")
            if hfs_val and _ok(Path(hfs_val) / "houdini" / "help"):
                return Path(hfs_val) / "houdini" / "help"
        except Exception:
            pass
        for drive in ("C", "D", "E"):
            base = Path(f"{drive}:/Program Files/Side Effects Software")
            if base.is_dir():
                for v in sorted(base.glob("Houdini*"), reverse=True):
                    p = v / "houdini" / "help"
                    if _ok(p):
                        return p
        return None

    # ----------------------------------------------------------
    # Index load / build / cache
    # ----------------------------------------------------------

    def _load_or_build(self) -> None:
        cf = self._cache_dir / "houdini_doc_index.json"
        if cf.exists():
            try:
                data = json.loads(cf.read_text("utf-8"))
                if data.get("help_dir") == str(self._help_dir) and data.get("version") == 2:
                    self._load_from_cache(data)
                    print(f"[DocIndex] Cache: {len(self.node_index)} nodes, "
                          f"{len(self.vex_index)} VEX, {len(self.hom_index)} HOM")
                    return
            except Exception as e:
                print(f"[DocIndex] Cache failed: {e}")
        if not self._help_dir:
            print("[DocIndex] No help dir found, index empty")
            return
        print(f"[DocIndex] Building: {self._help_dir} ...")
        self._build_indexes()
        try:
            self._save_to_cache(cf)
            print(f"[DocIndex] Cached: {len(self.node_index)} nodes, "
                  f"{len(self.vex_index)} VEX, {len(self.hom_index)} HOM")
        except Exception as e:
            print(f"[DocIndex] Cache save failed: {e}")

    def _build_indexes(self) -> None:
        for name, builder in [("nodes.zip", self._build_node_index),
                               ("vex.zip", self._build_vex_index),
                               ("hom.zip", self._build_hom_index)]:
            zp = self._help_dir / name
            if zp.exists():
                print(f"[DocIndex]   Parsing {name} ...")
                builder(zp)
        self._build_aliases()

    # ----------------------------------------------------------
    # Wiki format parser
    # ----------------------------------------------------------

    @staticmethod
    def _parse_wiki(text: str) -> dict:
        doc: Dict[str, Any] = {"title":"","type":"","context":"","internal":"",
                               "description":"","body":"","sections":{}}
        lines = text.split("\n"); i = 0; n = len(lines)
        while i < n and not lines[i].strip(): i += 1
        if i < n:
            m = re.match(r"^=\s+(.+?)\s+=\s*$", lines[i])
            if m: doc["title"] = m.group(1).strip(); i += 1
        while i < n:
            line = lines[i].strip()
            if not line: i += 1; continue
            m = re.match(r"^#(\w+):\s*(.*)", line)
            if m:
                k, v = m.group(1).lower(), m.group(2).strip()
                if k in doc: doc[k] = v
                i += 1
            else: break
        while i < n and not lines[i].strip(): i += 1
        if i < n and lines[i].strip().startswith('"""'):
            dl = lines[i].strip()
            if dl.endswith('"""') and len(dl) > 6:
                doc["description"] = dl[3:-3].strip(); i += 1
            else:
                parts = [dl[3:]]; i += 1
                while i < n:
                    if '"""' in lines[i]:
                        parts.append(lines[i].split('"""')[0]); i += 1; break
                    parts.append(lines[i]); i += 1
                doc["description"] = "\n".join(parts).strip()
        cur_sec = "_body"; buf: List[str] = []
        while i < n:
            s = lines[i].strip()
            if s.startswith("@") and len(s) > 1 and s[1:].split()[0].isalpha():
                tb = "\n".join(buf).strip()
                if tb:
                    if cur_sec == "_body": doc["body"] = tb
                    else: doc["sections"][cur_sec] = tb
                cur_sec = s[1:].split()[0]; buf = []
            else: buf.append(lines[i])
            i += 1
        tb = "\n".join(buf).strip()
        if tb:
            if cur_sec == "_body": doc["body"] = tb
            else: doc["sections"][cur_sec] = tb
        return doc

    # ----------------------------------------------------------
    # Parameter parsing
    # ----------------------------------------------------------

    @staticmethod
    def _parse_parameters(text: str) -> list:
        params: list = []
        if not text: return params
        cur_name = ""; cur_desc: List[str] = []
        for line in text.split("\n"):
            s = line.strip()
            if not s: continue
            if s.startswith(":include") or s.startswith("#include"): continue
            if s.endswith(":") and not line.startswith((" ", "\t")):
                if cur_name and not cur_name.startswith(":"):
                    params.append([cur_name, " ".join(cur_desc)[:150]])
                cur_name = s[:-1].strip(); cur_desc = []
            elif cur_name and (line.startswith("    ") or line.startswith("\t")):
                cur_desc.append(s)
        if cur_name and not cur_name.startswith(":"):
            params.append([cur_name, " ".join(cur_desc)[:150]])
        return params

    # ----------------------------------------------------------
    # Node index builder
    # ----------------------------------------------------------

    def _build_node_index(self, zip_path: Path) -> None:
        count = 0
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if not name.endswith(".txt") or "/_" in name or name.startswith("_"):
                        continue
                    try:
                        raw = zf.read(name).decode("utf-8", errors="ignore")
                        doc = self._parse_wiki(raw)
                        internal = doc.get("internal", "")
                        context = doc.get("context", "")
                        if not internal:
                            parts = name.replace("\\", "/").split("/")
                            internal = Path(parts[-1]).stem
                            if not context and len(parts) >= 3:
                                context = parts[-2] if parts[-2] != "nodes" else ""
                        if not internal: continue
                        params = self._parse_parameters(
                            doc.get("sections", {}).get("parameters", ""))
                        nd = NodeDoc(internal, context, doc.get("title", internal),
                                     doc.get("description", "")[:300], params[:15])
                        prio = {"sop": 0, "obj": 1, "dop": 2, "cop2": 3}
                        existing = self.node_index.get(internal)
                        if existing is None or prio.get(context, 99) < prio.get(existing.context, 99):
                            self.node_index[internal] = nd
                        if context:
                            self.node_index[f"{context}/{internal}"] = nd
                        count += 1
                    except Exception: continue
        except Exception as e:
            print(f"[DocIndex] nodes.zip failed: {e}")
        print(f"[DocIndex]   -> {count} nodes")

    # ----------------------------------------------------------
    # VEX index builder
    # ----------------------------------------------------------

    def _build_vex_index(self, zip_path: Path) -> None:
        count = 0
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if not name.endswith(".txt") or "/_" in name: continue
                    try:
                        raw = zf.read(name).decode("utf-8", errors="ignore")
                        doc = self._parse_wiki(raw)
                        fn = doc.get("internal", "") or Path(name).stem
                        if not fn or fn.startswith("_"): continue
                        sig_src = doc.get("body","") + "\n" + doc.get("sections",{}).get("usage","")
                        sig_m = re.search(r"`([^`]+)`", sig_src)
                        sig = sig_m.group(1) if sig_m else ""
                        parts = name.replace("\\", "/").split("/")
                        cat = parts[-2] if len(parts) >= 2 and parts[-2] != "vex" else ""
                        self.vex_index[fn] = VexDoc(fn, sig[:200],
                                                     doc.get("description","")[:200], cat)
                        if cat: self._vex_categories.setdefault(cat, []).append(fn)
                        count += 1
                    except Exception: continue
        except Exception as e:
            print(f"[DocIndex] vex.zip failed: {e}")
        print(f"[DocIndex]   -> {count} VEX functions")

    # ----------------------------------------------------------
    # HOM index builder
    # ----------------------------------------------------------

    def _build_hom_index(self, zip_path: Path) -> None:
        count = 0
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if not name.endswith(".txt") or "/_" in name: continue
                    try:
                        raw = zf.read(name).decode("utf-8", errors="ignore")
                        doc = self._parse_wiki(raw)
                        title = doc.get("title", "") or "hou." + Path(name).stem
                        self.hom_index[title] = HomDoc(
                            title, doc.get("type","") or "class", "",
                            doc.get("description","")[:300])
                        count += 1
                        mt = doc.get("sections", {}).get("methods", "")
                        if mt: count += self._extract_hom_methods(title, mt)
                    except Exception: continue
        except Exception as e:
            print(f"[DocIndex] hom.zip failed: {e}")
        print(f"[DocIndex]   -> {count} HOM entries")

    def _extract_hom_methods(self, parent: str, text: str) -> int:
        count = 0
        for m in re.finditer(r"::`(\w+)\(([^)]*)\)`\s*:", text):
            mn, ma = m.group(1), m.group(2)
            full = f"{parent}.{mn}"
            pos = m.end(); desc: List[str] = []
            for line in text[pos:].split("\n"):
                s = line.strip()
                if not s: continue
                if line.startswith(("    ", "\t")):
                    desc.append(s)
                    if len(desc) >= 2: break
                else: break
            self.hom_index[full] = HomDoc(full, "method", f"{mn}({ma})",
                                           " ".join(desc)[:200])
            count += 1
        return count

    # ----------------------------------------------------------
    # Aliases
    # ----------------------------------------------------------

    def _build_aliases(self) -> None:
        self._node_aliases.clear()
        for ntype, doc in self.node_index.items():
            if "/" in ntype: continue
            self._node_aliases[doc.title.lower().replace(" ", "")] = ntype
            self._node_aliases[ntype.lower()] = ntype
        self._all_node_types = {k for k in self.node_index if "/" not in k}

    # ----------------------------------------------------------
    # Lookup API
    # ----------------------------------------------------------

    def lookup_node(self, node_type: str) -> Optional[NodeDoc]:
        doc = self.node_index.get(node_type)
        if doc: return doc
        alias = self._node_aliases.get(node_type.lower().replace(" ", ""))
        return self.node_index.get(alias) if alias else None

    def lookup_vex(self, func_name: str) -> Optional[VexDoc]:
        return self.vex_index.get(func_name) or self.vex_index.get(func_name.lower())

    def lookup_hom(self, name: str) -> Optional[HomDoc]:
        return self.hom_index.get(name)

    # ----------------------------------------------------------
    # Cache serialization
    # ----------------------------------------------------------

    def _save_to_cache(self, path: Path) -> None:
        data = {"help_dir": str(self._help_dir), "version": 2,
                "nodes": {k: {"node_type": v.node_type, "context": v.context,
                               "title": v.title, "description": v.description,
                               "parameters": v.parameters}
                          for k, v in self.node_index.items() if "/" not in k},
                "vex": {k: {"name": v.name, "signature": v.signature,
                            "description": v.description, "category": v.category}
                        for k, v in self.vex_index.items()},
                "hom": {k: {"name": v.name, "doc_type": v.doc_type,
                            "signature": v.signature, "description": v.description}
                        for k, v in self.hom_index.items()}}
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",",":")), "utf-8")

    def _load_from_cache(self, data: dict) -> None:
        for k, v in data.get("nodes", {}).items():
            doc = NodeDoc(**v); self.node_index[k] = doc
            if v.get("context"): self.node_index[f"{v['context']}/{k}"] = doc
        for k, v in data.get("vex", {}).items():
            self.vex_index[k] = VexDoc(**v)
            if v.get("category"): self._vex_categories.setdefault(v["category"], []).append(k)
        for k, v in data.get("hom", {}).items():
            self.hom_index[k] = HomDoc(**v)
        self._build_aliases()

    # ----------------------------------------------------------
    # Knowledge base
    # ----------------------------------------------------------

    def _load_knowledge_base(self) -> None:
        if not self._doc_dir.is_dir(): return
        txt_files = sorted(self._doc_dir.rglob("*.txt"))
        if not txt_files: return
        kb_cache = self._cache_dir / "knowledge_base_cache.json"
        fps = {str(p.relative_to(self._doc_dir)): p.stat().st_mtime for p in txt_files}
        if kb_cache.exists():
            try:
                cd = json.loads(kb_cache.read_text("utf-8"))
                if cd.get("fingerprints", {}) == fps:
                    for c in cd.get("chunks", []):
                        self.knowledge_chunks.append(KnowledgeChunk(**c))
                    print(f"[DocIndex] KB cache: {len(self.knowledge_chunks)} chunks")
                    return
                print("[DocIndex] KB files changed, re-parsing...")
            except Exception as e:
                print(f"[DocIndex] KB cache failed: {e}")
        for tp in txt_files:
            try:
                text = tp.read_text("utf-8")
                source = str(tp.relative_to(self._doc_dir).with_suffix("")).replace("\\", "/")
                self.knowledge_chunks.extend(self._parse_txt_sections(text, source))
            except Exception: pass
        if self.knowledge_chunks:
            print(f"[DocIndex] KB: {len(self.knowledge_chunks)} chunks")
            try:
                kb_cache.write_text(json.dumps(
                    {"fingerprints": fps, "chunks": [
                        {"title": c.title, "content": c.content,
                         "source": c.source, "keywords": c.keywords}
                        for c in self.knowledge_chunks]},
                    ensure_ascii=False, separators=(",",":")), "utf-8")
            except Exception: pass

    @staticmethod
    def _parse_txt_sections(text: str, source: str) -> List[KnowledgeChunk]:
        chunks: List[KnowledgeChunk] = []
        cur_title = ""; cur_lines: List[str] = []
        def _flush():
            if cur_title and cur_lines:
                content = "\n".join(cur_lines).strip()
                if len(content) > 30:
                    kw_en = [w.lower() for w in re.findall(r"[a-zA-Z_@][a-zA-Z0-9_@.]*",
                              cur_title + " " + content) if len(w) >= 2]
                    kw_cn = re.findall(r"[\u4e00-\u9fff]{2,}", cur_title)
                    chunks.append(KnowledgeChunk(cur_title, content[:2000], source,
                                                 list(set(kw_en + kw_cn))[:50]))
        for line in text.split("\n"):
            m = re.match(r"^##\s+(.+)", line)
            if m:
                t = m.group(1).strip()
                if re.match(r"^[=\-#*~]{3,}$", t): continue
                _flush(); cur_title = t; cur_lines = []
            else: cur_lines.append(line)
        _flush()
        return chunks

    def search_knowledge(self, query: str, top_k: int = 3) -> List[dict]:
        if not self.knowledge_chunks: return []
        ql = query.lower()
        qw = set(re.findall(r"[a-zA-Z_@][a-zA-Z0-9_@.]*", ql))
        qcn = set(re.findall(r"[\u4e00-\u9fff]{2,}", query))
        scored: List[tuple] = []
        for chunk in self.knowledge_chunks:
            s = 0.0
            s += len(qw & set(chunk.keywords)) * 0.3
            for cn in qcn:
                if cn in chunk.title or cn in chunk.content[:200]: s += 0.5
            for w in qw:
                if len(w) >= 3 and w in chunk.title.lower(): s += 0.8
            if s > 0.2: scored.append((s, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for sc, chunk in scored[:top_k]:
            snip = chunk.content[:300]
            if len(chunk.content) > 300: snip += "..."
            results.append({"type": "knowledge", "name": chunk.title,
                            "snippet": f"[KB] {chunk.title}\n{snip}",
                            "score": min(sc, 1.0), "source": chunk.source})
        return results

    # ----------------------------------------------------------
    # Search API
    # ----------------------------------------------------------

    def search(self, query: str, top_k: int = 5, **_kw) -> List[dict]:
        results: List[dict] = []
        ql = query.lower().strip()
        # Exact
        node = self.lookup_node(ql)
        if node: results.append({"type":"node","name":node.node_type,
                                  "snippet":self._fmt_node(node),"score":1.0})
        vex = self.lookup_vex(ql)
        if vex: results.append({"type":"vex","name":vex.name,
                                 "snippet":self._fmt_vex(vex),"score":1.0})
        hom = self.lookup_hom(query)
        if hom: results.append({"type":"hom","name":hom.name,
                                 "snippet":self._fmt_hom(hom),"score":1.0})
        # Substring
        if len(results) < top_k:
            words = {w for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", ql)}
            seen = {r["name"] for r in results}
            for w in words:
                if len(results) >= top_k: break
                for nt in (self._all_node_types or set()):
                    if w in nt.lower() and nt not in seen:
                        d = self.node_index[nt]
                        results.append({"type":"node","name":nt,
                                        "snippet":self._fmt_node(d),"score":0.5})
                        seen.add(nt)
                        if len(results) >= top_k: break
                for fn, d in self.vex_index.items():
                    if w in fn.lower() and fn not in seen:
                        results.append({"type":"vex","name":fn,
                                        "snippet":self._fmt_vex(d),"score":0.4})
                        seen.add(fn)
                        if len(results) >= top_k: break
                for hn, d in self.hom_index.items():
                    if w in hn.lower() and hn not in seen:
                        results.append({"type":"hom","name":hn,
                                        "snippet":self._fmt_hom(d),"score":0.4})
                        seen.add(hn)
                        if len(results) >= top_k: break
        # Knowledge base
        if len(results) < top_k:
            for kr in self.search_knowledge(query, top_k - len(results)):
                if kr["name"] not in {r["name"] for r in results}:
                    results.append(kr)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ----------------------------------------------------------
    # Auto-retrieval
    # ----------------------------------------------------------

    def auto_retrieve(self, user_message: str, max_chars: int = 1200) -> str:
        if not any((self.node_index, self.vex_index, self.hom_index)): return ""
        snippets: List[str] = []; seen: set = set(); total = 0
        def _add(s: str, key: str):
            nonlocal total
            if key in seen or total + len(s) > max_chars: return
            seen.add(key); snippets.append(s); total += len(s)
        # hou.XXX
        for ref in re.findall(r"hou\.([a-zA-Z_][a-zA-Z0-9_.]*)", user_message):
            doc = self.lookup_hom(f"hou.{ref}")
            if doc: _add(self._fmt_hom(doc), f"hou.{ref}")
        # English words
        for w in set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", user_message)):
            wl = w.lower()
            if wl in self._STOP_WORDS or len(wl) < 3: continue
            vd = self.vex_index.get(wl) or self.vex_index.get(w)
            if vd: _add(self._fmt_vex(vd), vd.name)
            nd = self.node_index.get(wl) or self.node_index.get(w)
            if nd: _add(self._fmt_node(nd), nd.node_type)
        # Chinese keywords
        for kw in re.findall(r"[\u4e00-\u9fff]{2,}", user_message)[:3]:
            for nt, nd in self.node_index.items():
                if "/" in nt: continue
                if kw in nd.title or kw in nd.description:
                    _add(self._fmt_node(nd), nd.node_type); break
        # Knowledge base
        if self.knowledge_chunks:
            ml = user_message.lower()
            if any(h in ml for h in self._KB_HINTS):
                for kr in self.search_knowledge(user_message, top_k=2):
                    if kr["score"] > 0.3: _add(kr["snippet"], kr["name"])
        if not snippets: return ""
        return "[Houdini Doc Reference]\n" + "\n".join(snippets)

    # ----------------------------------------------------------
    # Formatting
    # ----------------------------------------------------------

    @staticmethod
    def _fmt_node(d: NodeDoc) -> str:
        s = f"[doc] {d.title} ({d.context}/{d.node_type})"
        if d.description: s += f": {d.description[:120]}"
        if d.parameters: s += f"\n   Params: {', '.join(p[0] for p in d.parameters[:6])}"
        return s

    @staticmethod
    def _fmt_vex(d: VexDoc) -> str:
        s = f"[VEX] {d.name}"
        return s + f": {d.signature}" if d.signature else (s + f": {d.description[:120]}" if d.description else s)

    @staticmethod
    def _fmt_hom(d: HomDoc) -> str:
        s = f"[HOM] {d.name}"
        if d.signature: s += f" -> {d.signature}"
        if d.description: s += f": {d.description[:120]}"
        return s

    # ----------------------------------------------------------
    # Stats
    # ----------------------------------------------------------

    def stats(self) -> dict:
        return {
            "nodes": len(self.node_index),
            "vex_functions": len(self.vex_index),
            "hom_entries": len(self.hom_index),
            "knowledge_chunks": len(self.knowledge_chunks),
            "help_dir": str(self._help_dir) if self._help_dir else None,
        }


# ============================================================
# Global singleton
# ============================================================

_index_instance: Optional[HoudiniDocIndex] = None


def get_doc_index(help_dir: Optional[str] = None) -> HoudiniDocIndex:
    """Get or create the global document index singleton."""
    global _index_instance
    if _index_instance is None:
        _index_instance = HoudiniDocIndex(help_dir)
    return _index_instance


# Backward-compatible alias
get_doc_rag = get_doc_index
