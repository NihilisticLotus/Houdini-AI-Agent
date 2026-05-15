# -*- coding: utf-8 -*-
"""Connectivity analysis skill.

Analyzes how many connected components exist in geometry using Union-Find.
"""

SKILL_INFO = {
    "name": "analyze_connectivity",
    "label": "Analyze Connectivity",
    "description": (
        "分析几何体的连通分量数量。优先使用已有的 class 属性（connectivity 节点生成的），"
        "否则使用并查集算法通过面顶点建立连接。返回各分量的点数/面数/占比。"
    ),
    "parameters": {
        "node_path": {
            "type": "string",
            "description": "节点路径",
            "required": True,
        },
    },
}


def run(adapter=None, node_path="", **kwargs):
    """Entry point."""
    hou = _get_hou(adapter)
    if hou is None:
        return _mock_result(node_path)

    node = hou.node(node_path)
    if not node:
        return {"error": f"节点不存在: {node_path}"}

    try:
        geo = node.geometry()
    except Exception as exc:
        return {"error": f"无法读取几何体: {exc}"}
    if geo is None:
        return {"error": "节点无几何体数据"}

    total_points = len(geo.points())
    total_prims = len(geo.prims())

    # Strategy 1: Use existing 'class' attribute
    class_attr = geo.findPointAttrib("class")
    if class_attr is not None:
        return _analyze_with_class_attr(geo, class_attr, total_points, total_prims)

    # Strategy 2: Union-Find via prim vertices
    return _analyze_with_union_find(geo, total_points, total_prims)


def _analyze_with_class_attr(geo, class_attr, total_points, total_prims):
    """Analyze using existing class attribute."""
    components = {}
    for pt in geo.points():
        try:
            val = pt.attribValue(class_attr)
            cls_id = int(val) if not isinstance(val, (int, float)) else int(val)
            if cls_id not in components:
                components[cls_id] = {"points": 0, "prims": 0}
            components[cls_id]["points"] += 1
        except Exception:
            continue

    # Count prims per component
    prim_class_attr = geo.findPrimAttrib("class")
    if prim_class_attr is not None:
        for prim in geo.prims():
            try:
                val = prim.attribValue(prim_class_attr)
                cls_id = int(val) if not isinstance(val, (int, float)) else int(val)
                if cls_id in components:
                    components[cls_id]["prims"] += 1
            except Exception:
                continue

    parts = []
    for cls_id, data in sorted(components.items()):
        parts.append({
            "class": cls_id,
            "points": data["points"],
            "prims": data["prims"],
            "point_percent": round(data["points"] / max(total_points, 1) * 100, 2),
        })

    return {
        "method": "class_attribute",
        "total_components": len(components),
        "total_points": total_points,
        "total_prims": total_prims,
        "components": parts,
    }


def _analyze_with_union_find(geo, total_points, total_prims):
    """Analyze using Union-Find algorithm."""
    parent = list(range(total_points))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Build connections through prim vertices
    point_map = {}
    for i, pt in enumerate(geo.points()):
        point_map[pt.number()] = i

    for prim in geo.prims():
        try:
            verts = list(prim.vertices())
            for idx in range(len(verts)):
                pt_a = verts[idx].point()
                pt_b = verts[(idx + 1) % len(verts)].point()
                a = point_map.get(pt_a.number())
                b = point_map.get(pt_b.number())
                if a is not None and b is not None:
                    union(a, b)
        except Exception:
            continue

    # Count components
    comp_points = {}
    for i in range(total_points):
        root = find(i)
        comp_points.setdefault(root, 0)
        comp_points[root] += 1

    parts = []
    for i, (root, count) in enumerate(sorted(comp_points.items(), key=lambda x: -x[1])):
        parts.append({
            "class": i,
            "points": count,
            "prims": 0,
            "point_percent": round(count / max(total_points, 1) * 100, 2),
        })

    return {
        "method": "union_find",
        "total_components": len(comp_points),
        "total_points": total_points,
        "total_prims": total_prims,
        "components": parts,
    }


def _get_hou(adapter):
    if adapter is not None and hasattr(adapter, "hou"):
        return adapter.hou
    return None


def _mock_result(node_path):
    return {
        "method": "mock",
        "total_components": 1,
        "total_points": 1000,
        "total_prims": 500,
        "components": [
            {"class": 0, "points": 1000, "prims": 500, "point_percent": 100.0},
        ],
    }
