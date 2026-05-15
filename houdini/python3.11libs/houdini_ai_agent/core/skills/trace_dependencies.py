# -*- coding: utf-8 -*-
"""Trace node dependencies skill.

Traces upstream dependency tree or downstream impact scope with visualization.
"""

SKILL_INFO = {
    "name": "trace_node_dependencies",
    "label": "Trace Node Dependencies",
    "description": (
        "追溯节点的上游依赖树或下游影响范围。upstream: 查看依赖了哪些上游节点；"
        "downstream: 查看修改该节点会影响哪些下游。返回层级分组和可视化树形文本。"
    ),
    "parameters": {
        "node_path": {
            "type": "string",
            "description": "节点路径",
            "required": True,
        },
        "direction": {
            "type": "string",
            "description": "追溯方向: upstream(上游依赖) 或 downstream(下游影响)",
            "required": False,
            "enum": ["upstream", "downstream"],
        },
        "max_depth": {
            "type": "integer",
            "description": "最大追溯深度（默认 10，最大 50）",
            "required": False,
        },
    },
}


def run(adapter=None, node_path="", direction="upstream", max_depth=10, **kwargs):
    """Entry point."""
    hou = _get_hou(adapter)
    if hou is None:
        return _mock_result(node_path, direction)

    node = hou.node(node_path)
    if not node:
        return {"error": f"节点不存在: {node_path}"}

    max_depth = min(int(max_depth), 50)
    if direction not in ("upstream", "downstream"):
        return {"error": f"无效方向: {direction}，可选 upstream / downstream"}

    visited = set()
    levels = []

    def traverse(n, depth):
        if depth > max_depth or n.path() in visited:
            return None
        visited.add(n.path())

        connected = n.inputs() if direction == "upstream" else n.outputs()

        children = {}
        for conn in connected:
            if conn:
                child_tree = traverse(conn, depth + 1)
                if child_tree is not None:
                    children[conn.name()] = child_tree

        while len(levels) <= depth:
            levels.append([])
        levels[depth].append({
            "name": n.name(),
            "type": n.type().name(),
            "path": n.path(),
        })

        return {
            "type": n.type().name(),
            "path": n.path(),
            "connections": children,
        }

    def tree_to_text(t, indent=0):
        if t is None:
            return ""
        lines = []
        name = t["path"].split("/")[-1]
        prefix = "  " * indent + ("└─ " if indent > 0 else "")
        lines.append(f"{prefix}{name} ({t['type']})")
        for _child_name, child_tree in t.get("connections", {}).items():
            lines.append(tree_to_text(child_tree, indent + 1))
        return "\n".join(lines)

    tree = traverse(node, 0)

    return {
        "root": node.name(),
        "direction": direction,
        "total_nodes": len(visited),
        "max_depth": len(levels) - 1 if levels else 0,
        "levels": levels,
        "tree_text": tree_to_text(tree),
    }


def _get_hou(adapter):
    if adapter is not None and hasattr(adapter, "hou"):
        return adapter.hou
    return None


def _mock_result(node_path, direction):
    return {
        "root": node_path.split("/")[-1] if node_path else "node",
        "direction": direction,
        "total_nodes": 4,
        "max_depth": 3,
        "levels": [
            [{"name": "OUT", "type": "null", "path": node_path}],
            [{"name": "wrangle1", "type": "attribwrangle", "path": f"{node_path.rsplit('/', 1)[0]}/wrangle1"}],
            [{"name": "mountain1", "type": "mountain", "path": f"{node_path.rsplit('/', 1)[0]}/mountain1"}],
            [{"name": "grid1", "type": "grid", "path": f"{node_path.rsplit('/', 1)[0]}/grid1"}],
        ],
        "tree_text": f"{node_path.split('/')[-1]} (null)\n  └─ wrangle1 (attribwrangle)\n    └─ mountain1 (mountain)\n      └─ grid1 (grid)",
    }
