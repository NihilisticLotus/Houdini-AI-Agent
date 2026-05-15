# -*- coding: utf-8 -*-
"""Find attribute references skill.

Searches for references to a specific attribute across VEX code, expressions,
and string parameters in a network.
"""

SKILL_INFO = {
    "name": "find_attribute_references",
    "label": "Find Attribute References",
    "description": (
        "查找网络中所有引用了指定属性的节点。搜索 VEX 代码（wrangle snippet）、"
        "参数表达式和字符串参数值。支持递归搜索子网络。"
    ),
    "parameters": {
        "network_path": {
            "type": "string",
            "description": "网络路径",
            "required": True,
        },
        "attr_name": {
            "type": "string",
            "description": "属性名（如 Cd, N, uv）",
            "required": True,
        },
        "recursive": {
            "type": "boolean",
            "description": "是否递归搜索子网络（默认 false）",
            "required": False,
        },
    },
}


def run(adapter=None, network_path="", attr_name="", recursive=False, **kwargs):
    """Entry point."""
    hou = _get_hou(adapter)
    if hou is None:
        return _mock_result(network_path, attr_name)

    if not attr_name:
        return {"error": "attr_name is required"}

    network = hou.node(network_path)
    if not network:
        return {"error": f"网络不存在: {network_path}"}

    nodes = list(network.allSubChildren()) if recursive else list(network.children())
    references = []

    for node in nodes:
        try:
            path = node.path()
            name = node.name()
            type_name = node.type().name()

            # Search VEX code parameters
            for parm_name in ("snippet", "snippet1", "vexpression", "code"):
                parm = node.parm(parm_name)
                if parm is None:
                    continue
                try:
                    code = parm.unexpandedString()
                except Exception:
                    try:
                        code = parm.evalAsString()
                    except Exception:
                        continue

                if attr_name in code:
                    lines = []
                    for i, line in enumerate(code.split("\n"), 1):
                        if attr_name in line:
                            lines.append({"line": i, "text": line.strip()})

                    references.append({
                        "node": path,
                        "type": type_name,
                        "parameter": parm_name,
                        "match_type": "vex_code",
                        "matches": lines[:10],
                    })

            # Search all string parameters
            for parm in node.parms():
                try:
                    pt = parm.parmTemplate()
                    if pt is None:
                        continue
                    # Only search string-type parms
                    type_name_pt = pt.type().name()
                    if type_name_pt not in ("String", "StringMenu", "StringReplace"):
                        continue

                    raw_val = parm.unexpandedString()
                    if attr_name in raw_val:
                        # Avoid duplicating VEX code matches
                        if parm.name() in ("snippet", "snippet1", "vexpression", "code"):
                            continue
                        references.append({
                            "node": path,
                            "type": type_name,
                            "parameter": parm.name(),
                            "match_type": "parameter_value",
                            "value_preview": raw_val[:100],
                        })
                except Exception:
                    continue

        except Exception:
            continue

    return {
        "network": network_path,
        "attr_name": attr_name,
        "recursive": recursive,
        "nodes_scanned": len(nodes),
        "references": references,
        "total_references": len(references),
    }


def _get_hou(adapter):
    if adapter is not None and hasattr(adapter, "hou"):
        return adapter.hou
    return None


def _mock_result(network_path, attr_name):
    return {
        "network": network_path or "/obj/geo1",
        "attr_name": attr_name or "Cd",
        "recursive": False,
        "nodes_scanned": 5,
        "references": [
            {"node": f"{network_path}/attribwrangle1", "type": "attribwrangle",
             "parameter": "snippet", "match_type": "vex_code",
             "matches": [{"line": 3, "text": f"@{attr_name}.r = 1.0;"}]},
        ],
        "total_references": 1,
    }
