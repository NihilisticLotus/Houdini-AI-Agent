# -*- coding: utf-8 -*-
"""Find dead nodes skill.

Detects orphan nodes (no connections) and unused end nodes in a network.
"""

SKILL_INFO = {
    "name": "find_dead_nodes",
    "label": "Find Dead Nodes",
    "description": (
        "查找网络中的死节点。区分孤立节点（无输入无输出）和"
        "链末端未使用节点（有输入无输出且非 display/render）。"
    ),
    "parameters": {
        "network_path": {
            "type": "string",
            "description": "网络路径",
            "required": True,
        },
    },
}


def run(adapter=None, network_path="", **kwargs):
    """Entry point."""
    hou = _get_hou(adapter)
    if hou is None:
        return _mock_result(network_path)

    network = hou.node(network_path)
    if not network:
        return {"error": f"网络不存在: {network_path}"}

    children = list(network.children())
    orphans = []
    unused_ends = []

    display_node = None
    render_node = None
    try:
        display_node = network.displayNode()
        if display_node:
            display_node = display_node.path()
    except Exception:
        pass
    try:
        render_node = network.renderNode()
        if render_node:
            render_node = render_node.path()
    except Exception:
        pass

    for child in children:
        try:
            path = child.path()
            name = child.name()
            type_name = child.type().name()

            num_inputs = child.numInputs()
            outputs = list(child.outputs())
            num_outputs = len(outputs)

            is_display = (path == display_node) if display_node else False
            is_render = (path == render_node) if render_node else False

            # Skip display/render nodes
            if is_display or is_render:
                continue

            if num_inputs == 0 and num_outputs == 0:
                orphans.append({
                    "name": name,
                    "type": type_name,
                    "path": path,
                })
            elif num_outputs == 0 and num_inputs > 0:
                unused_ends.append({
                    "name": name,
                    "type": type_name,
                    "path": path,
                    "inputs": num_inputs,
                })
        except Exception:
            continue

    return {
        "network": network_path,
        "total_nodes": len(children),
        "display_node": display_node,
        "render_node": render_node,
        "orphan_nodes": orphans,
        "unused_end_nodes": unused_ends,
        "total_dead": len(orphans) + len(unused_ends),
    }


def _get_hou(adapter):
    if adapter is not None and hasattr(adapter, "hou"):
        return adapter.hou
    return None


def _mock_result(network_path):
    return {
        "network": network_path or "/obj/geo1",
        "total_nodes": 8,
        "display_node": "/obj/geo1/OUT",
        "render_node": "/obj/geo1/OUT",
        "orphan_nodes": [
            {"name": "old_transform1", "type": "xform", "path": f"{network_path}/old_transform1"},
        ],
        "unused_end_nodes": [],
        "total_dead": 1,
    }
