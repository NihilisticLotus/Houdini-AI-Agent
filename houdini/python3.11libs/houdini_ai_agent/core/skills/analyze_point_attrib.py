# -*- coding: utf-8 -*-
"""Analyze geometry attributes (point/vertex/prim/detail).

Provides statistical analysis of geometry attributes including min/max/mean/std,
NaN/Inf counts, and value distributions. Supports sampling for large datasets.
"""

SKILL_INFO = {
    "name": "analyze_geometry_attribs",
    "label": "Analyze Geometry Attributes",
    "description": (
        "分析节点的几何属性统计信息。不指定属性名时列出该类别的所有属性；"
        "指定属性名时返回 min/max/mean/std/nan_count/inf_count 统计。"
        "支持 point/vertex/prim/detail 四种属性类别。"
    ),
    "parameters": {
        "node_path": {
            "type": "string",
            "description": "节点路径，如 /obj/geo1/OUT",
            "required": True,
        },
        "attrib_name": {
            "type": "string",
            "description": "属性名（可选，不指定则列出该类别所有属性）",
            "required": False,
        },
        "attrib_class": {
            "type": "string",
            "description": "属性类别: point/vertex/prim/detail",
            "required": False,
            "enum": ["point", "vertex", "prim", "detail"],
        },
        "max_sample": {
            "type": "integer",
            "description": "最大采样数（默认 100000）",
            "required": False,
        },
    },
}


def run(adapter=None, node_path="", attrib_name="", attrib_class="point", max_sample=100000, **kwargs):
    """Entry point."""
    hou = _get_hou(adapter)
    if hou is None:
        return _mock_result(node_path, attrib_name, attrib_class)

    node = hou.node(node_path)
    if not node:
        return {"error": f"节点不存在: {node_path}"}

    try:
        geo = node.geometry()
    except Exception as exc:
        return {"error": f"无法读取几何体: {exc}"}

    if geo is None:
        return {"error": f"节点无几何体数据（可能未 cook 或没有 display flag）: {node_path}"}

    attrib_class = attrib_class or "point"
    max_sample = min(int(max_sample), 500000)

    # If no attrib_name specified, list all attributes of the class
    if not attrib_name:
        return _list_attribs(geo, attrib_class)

    # Analyze specific attribute
    return _analyze_attrib(geo, attrib_name, attrib_class, max_sample)


def _get_hou(adapter):
    """Get hou module from adapter if available."""
    if adapter is not None and hasattr(adapter, "hou"):
        return adapter.hou
    return None


def _list_attribs(geo, attrib_class):
    """List all attributes of a given class."""
    class_map = {
        "point": ("point", geo.pointAttribs),
        "vertex": ("vertex", geo.vertexAttribs),
        "prim": ("primitive", geo.primAttribs),
        "detail": ("detail", geo.globalAttribs),
    }
    entry = class_map.get(attrib_class)
    if entry is None:
        return {"error": f"Invalid attrib_class: {attrib_class}"}

    label, get_attribs = entry
    attribs = []
    try:
        for attr in get_attribs():
            info = {
                "name": attr.name(),
                "size": attr.size(),
                "type": _attrib_type_name(attr),
            }
            attribs.append(info)
    except Exception as exc:
        return {"error": f"Failed to list {label} attributes: {exc}"}

    return {
        "attrib_class": attrib_class,
        "count": len(attribs),
        "attributes": attribs,
    }


def _analyze_attrib(geo, attrib_name, attrib_class, max_sample):
    """Analyze a specific attribute."""
    # Find attribute
    find_map = {
        "point": geo.findPointAttrib,
        "vertex": geo.findVertexAttrib,
        "prim": geo.findPrimAttrib,
        "detail": geo.findGlobalAttrib,
    }
    finder = find_map.get(attrib_class)
    if finder is None:
        return {"error": f"Invalid attrib_class: {attrib_class}"}

    attr = finder(attrib_name)
    if attr is None:
        return {"error": f"属性不存在: {attrib_name} ({attrib_class})"}

    attr_type = _attrib_type_name(attr)
    size = attr.size()

    # Get elements
    if attrib_class == "point":
        elements = list(geo.points())
    elif attrib_class == "vertex":
        elements = list(geo.vertices())
    elif attrib_class == "prim":
        elements = list(geo.prims())
    else:
        elements = [None]  # detail has one value

    total = len(elements)
    import random
    if total > max_sample:
        indices = random.sample(range(total), max_sample)
        sampled = [elements[i] for i in indices]
    else:
        sampled = elements

    # String type
    if attr_type == "String" or attr.dataType().name() == "String":
        values = set()
        for elem in sampled:
            try:
                val = elem.attribValue(attr) if elem is not None else geo.attribValue(attr)
                if isinstance(val, bytes):
                    val = val.decode("utf-8", errors="replace")
                values.add(str(val))
            except Exception:
                continue
        return {
            "attrib_name": attrib_name,
            "attrib_class": attrib_class,
            "type": "String",
            "total_elements": total,
            "unique_values": len(values),
            "sample_values": sorted(values)[:20],
        }

    # Numeric type
    import math
    values = []
    nan_count = 0
    inf_count = 0
    for elem in sampled:
        try:
            raw = elem.attribValue(attr) if elem is not None else geo.attribValue(attr)
            if isinstance(raw, (tuple, list)):
                vals = [float(v) for v in raw]
            else:
                vals = [float(raw)]
            for v in vals:
                if math.isnan(v):
                    nan_count += 1
                elif math.isinf(v):
                    inf_count += 1
                else:
                    values.append(v)
        except Exception:
            continue

    if not values:
        return {
            "attrib_name": attrib_name,
            "attrib_class": attrib_class,
            "type": attr_type,
            "total_elements": total,
            "error": "No valid numeric values found",
        }

    values.sort()
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0
    std = math.sqrt(variance)

    return {
        "attrib_name": attrib_name,
        "attrib_class": attrib_class,
        "type": attr_type,
        "size": size,
        "total_elements": total,
        "sampled": n,
        "min": values[0],
        "max": values[-1],
        "mean": mean,
        "std": std,
        "median": values[n // 2],
        "nan_count": nan_count,
        "inf_count": inf_count,
    }


def _attrib_type_name(attr):
    """Get human-readable attribute type name."""
    try:
        return attr.dataType().name()
    except Exception:
        return "Unknown"


def _mock_result(node_path, attrib_name, attrib_class):
    """Return mock data when hou is not available."""
    if not attrib_name:
        return {
            "attrib_class": attrib_class,
            "count": 3,
            "attributes": [
                {"name": "P", "size": 3, "type": "Float"},
                {"name": "N", "size": 3, "type": "Float"},
                {"name": "Cd", "size": 3, "type": "Float"},
            ],
        }
    return {
        "attrib_name": attrib_name,
        "attrib_class": attrib_class,
        "type": "Float",
        "total_elements": 1000,
        "min": 0.0,
        "max": 1.0,
        "mean": 0.5,
        "std": 0.29,
        "nan_count": 0,
        "inf_count": 0,
    }
