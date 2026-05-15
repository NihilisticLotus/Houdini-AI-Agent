# -*- coding: utf-8 -*-
"""Bounding box information skill.

Returns bounding box metrics: min/max/center/size/diagonal/volume/surface area.
"""

import math

SKILL_INFO = {
    "name": "get_bounding_info",
    "label": "Get Bounding Box Info",
    "description": (
        "获取几何体的边界盒信息：min/max/center/size/对角线长度/体积/"
        "表面积/最长轴/最短轴/长宽比。"
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

    bbox = geo.boundingBox()
    min_v = bbox.min()
    max_v = bbox.max()
    center = bbox.center()
    size = bbox.size()

    min_vals = (min_v.x(), min_v.y(), min_v.z())
    max_vals = (max_v.x(), max_v.y(), max_v.z())
    center_vals = (center.x(), center.y(), center.z())
    size_vals = (size.x(), size.y(), size.z())

    diagonal = math.sqrt(sum(s * s for s in size_vals))

    # Volume and surface area
    volume = size_vals[0] * size_vals[1] * size_vals[2]
    sa = 2 * (size_vals[0] * size_vals[1] + size_vals[1] * size_vals[2] + size_vals[0] * size_vals[2])

    # Longest and shortest axis
    axis_names = ["X", "Y", "Z"]
    longest_idx = size_vals.index(max(size_vals))
    shortest_idx = size_vals.index(min(size_vals))

    # Aspect ratio (longest / shortest)
    min_size = min(s for s in size_vals if s > 0) if any(s > 0 for s in size_vals) else 0
    max_size = max(size_vals) if max(size_vals) > 0 else 1
    aspect = max_size / min_size if min_size > 0 else float("inf")

    return {
        "node": node_path,
        "min": list(min_vals),
        "max": list(max_vals),
        "center": list(center_vals),
        "size": list(size_vals),
        "diagonal": round(diagonal, 6),
        "volume": round(volume, 6),
        "surface_area": round(sa, 6),
        "longest_axis": axis_names[longest_idx],
        "shortest_axis": axis_names[shortest_idx],
        "aspect_ratio": round(aspect, 4),
        "is_valid": all(s >= 0 for s in size_vals),
    }


def _get_hou(adapter):
    if adapter is not None and hasattr(adapter, "hou"):
        return adapter.hou
    return None


def _mock_result(node_path):
    return {
        "node": node_path,
        "min": [-0.5, -0.5, -0.5],
        "max": [0.5, 0.5, 0.5],
        "center": [0.0, 0.0, 0.0],
        "size": [1.0, 1.0, 1.0],
        "diagonal": 1.732051,
        "volume": 1.0,
        "surface_area": 6.0,
        "longest_axis": "X",
        "shortest_axis": "X",
        "aspect_ratio": 1.0,
        "is_valid": True,
    }
