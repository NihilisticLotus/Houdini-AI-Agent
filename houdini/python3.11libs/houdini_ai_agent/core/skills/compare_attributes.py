# -*- coding: utf-8 -*-
"""Attribute comparison skill.

Compares attributes between two nodes across all attribute classes.
"""

SKILL_INFO = {
    "name": "compare_attributes",
    "label": "Compare Attributes",
    "description": (
        "对比两个节点的属性差异。覆盖 point/vertex/prim/detail 四种类别。"
        "返回各节点属性数量、独有属性、共同属性和类型差异。"
    ),
    "parameters": {
        "node_path_a": {
            "type": "string",
            "description": "第一个节点路径",
            "required": True,
        },
        "node_path_b": {
            "type": "string",
            "description": "第二个节点路径",
            "required": True,
        },
    },
}


def run(adapter=None, node_path_a="", node_path_b="", **kwargs):
    """Entry point."""
    hou = _get_hou(adapter)
    if hou is None:
        return _mock_result(node_path_a, node_path_b)

    node_a = hou.node(node_path_a)
    node_b = hou.node(node_path_b)
    if not node_a:
        return {"error": f"节点不存在: {node_path_a}"}
    if not node_b:
        return {"error": f"节点不存在: {node_path_b}"}

    try:
        geo_a = node_a.geometry()
        geo_b = node_b.geometry()
    except Exception as exc:
        return {"error": f"无法读取几何体: {exc}"}

    if geo_a is None or geo_b is None:
        return {"error": "至少一个节点无几何体数据"}

    classes = ["point", "vertex", "prim", "detail"]
    class_attrib_getters = {
        "point": ("pointAttribs", "point"),
        "vertex": ("vertexAttribs", "vertex"),
        "prim": ("primAttribs", "prim"),
        "detail": ("globalAttribs", "detail"),
    }

    results = {}
    total_only_a = 0
    total_only_b = 0
    total_common = 0
    total_type_diff = 0

    for cls_name in classes:
        getter_a = getattr(geo_a, class_attrib_getters[cls_name][0])
        getter_b = getattr(geo_b, class_attrib_getters[cls_name][0])

        attrs_a = {attr.name(): attr for attr in getter_a()}
        attrs_b = {attr.name(): attr for attr in getter_b()}

        names_a = set(attrs_a.keys())
        names_b = set(attrs_b.keys())

        only_a = names_a - names_b
        only_b = names_b - names_a
        common = names_a & names_b

        type_diffs = []
        for name in common:
            ta = _type_str(attrs_a[name])
            tb = _type_str(attrs_b[name])
            if ta != tb:
                type_diffs.append({"name": name, "type_a": ta, "type_b": tb})

        total_only_a += len(only_a)
    total_only_b += len(only_b)
    total_common += len(common)
    total_type_diff += len(type_diffs)

    results[cls_name] = {
        "count_a": len(attrs_a),
        "count_b": len(attrs_b),
        "only_in_a": sorted(only_a),
        "only_in_b": sorted(only_b),
        "common": len(common),
        "type_differences": type_diffs,
    }

    identical = (total_only_a == 0 and total_only_b == 0 and total_type_diff == 0)

    return {
        "node_a": node_path_a,
        "node_b": node_path_b,
        "classes": results,
        "total_only_in_a": total_only_a,
        "total_only_in_b": total_only_b,
        "total_common": total_common,
        "total_type_differences": total_type_diff,
        "identical": identical,
    }


def _type_str(attr):
    try:
        return f"{attr.dataType().name()}({attr.size()})"
    except Exception:
        return "Unknown"


def _get_hou(adapter):
    if adapter is not None and hasattr(adapter, "hou"):
        return adapter.hou
    return None


def _mock_result(node_path_a, node_path_b):
    return {
        "node_a": node_path_a,
        "node_b": node_path_b,
        "classes": {
            "point": {"count_a": 3, "count_b": 4, "only_in_a": [], "only_in_b": ["uv"],
                      "common": 3, "type_differences": []},
        },
        "total_only_in_a": 0,
        "total_only_in_b": 1,
        "total_common": 3,
        "total_type_differences": 0,
        "identical": False,
    }
