# -*- coding: utf-8 -*-
"""Cook performance analysis skill.

Analyzes cook times, geometry growth, and error nodes in a network.
Generates optimization suggestions.
"""

SKILL_INFO = {
    "name": "analyze_cook_performance",
    "label": "Analyze Cook Performance",
    "description": (
        "分析网络中所有节点的 cook 性能。返回按 cook 时间排序的慢节点、"
        "几何体膨胀节点、错误节点，以及优化建议。"
    ),
    "parameters": {
        "network_path": {
            "type": "string",
            "description": "网络路径",
            "required": True,
        },
        "top_n": {
            "type": "integer",
            "description": "返回前 N 个最慢节点（默认 10）",
            "required": False,
        },
        "force_cook": {
            "type": "boolean",
            "description": "是否强制重新 cook 以获取准确时间（默认 false）",
            "required": False,
        },
    },
}


def run(adapter=None, network_path="", top_n=10, force_cook=False, **kwargs):
    """Entry point."""
    hou = _get_hou(adapter)
    if hou is None:
        return _mock_result(network_path, top_n)

    top_n = min(int(top_n), 50)

    network = hou.node(network_path)
    if not network:
        return {"error": f"网络不存在: {network_path}"}

    children = list(network.children())
    if not children:
        return {"network": network_path, "message": "网络没有子节点"}

    import time

    node_stats = []
    for child in children:
        try:
            name = child.name()
            type_name = child.type().name()
            errors = list(child.errors())
            warnings = list(child.warnings())

            # Cook timing
            cook_time_ms = 0.0
            cook_count = 0
            point_count = 0
            prim_count = 0
            time_dependent = False
            input_points = 0

            try:
                time_dependent = child.isTimeDependent()
            except Exception:
                pass

            # Get input geometry point count
            try:
                for i in range(child.numInputs()):
                    inp = child.input(i)
                    if inp:
                        igeo = inp.geometry()
                        if igeo:
                            input_points = len(igeo.points())
                            break
            except Exception:
                pass

            if force_cook:
                try:
                    start = time.perf_counter()
                    child.cook(force=True)
                    elapsed = (time.perf_counter() - start) * 1000
                    cook_time_ms = elapsed
                    cook_count = 1
                except Exception as exc:
                    errors.append(f"Cook failed: {exc}")

            # Get output geometry stats
            try:
                geo = child.geometry()
                if geo:
                    point_count = len(geo.points())
                    prim_count = len(geo.prims())
            except Exception:
                pass

            node_stats.append({
                "name": name,
                "type": type_name,
                "path": child.path(),
                "cook_time_ms": cook_time_ms,
                "cook_count": cook_count,
                "points": point_count,
                "prims": prim_count,
                "input_points": input_points,
                "time_dependent": time_dependent,
                "errors": errors,
                "warnings": warnings,
            })
        except Exception:
            continue

    # Sort by cook time descending
    slow_nodes = sorted(node_stats, key=lambda x: x["cook_time_ms"], reverse=True)[:top_n]

    # Geometry growth detection
    geo_growth = []
    for stat in node_stats:
        if stat["input_points"] > 0 and stat["points"] > stat["input_points"] * 2:
            ratio = stat["points"] / stat["input_points"]
            geo_growth.append({
                "name": stat["name"],
                "type": stat["type"],
                "input_points": stat["input_points"],
                "output_points": stat["points"],
                "ratio": round(ratio, 2),
            })

    # Error nodes
    error_nodes = [s for s in node_stats if s["errors"] or s["warnings"]]

    # Suggestions
    suggestions = _generate_suggestions(node_stats, geo_growth)

    return {
        "network": network_path,
        "total_nodes": len(node_stats),
        "slow_nodes": slow_nodes,
        "geometry_growth": geo_growth,
        "error_nodes": error_nodes,
        "suggestions": suggestions,
    }


def _generate_suggestions(node_stats, geo_growth):
    """Generate optimization suggestions."""
    suggestions = []

    # Time-dependent without cache
    for s in node_stats:
        if s["time_dependent"] and s["type"] != "cache":
            suggestions.append(
                f"节点 {s['name']} ({s['type']}) 是 time-dependent，考虑在其后添加 Cache SOP"
            )

    # Geometry growth
    for g in geo_growth:
        suggestions.append(
            f"节点 {g['name']} 几何体膨胀 {g['ratio']}x，考虑使用 Packed Primitives 或减少细分"
        )

    # Python SOP
    for s in node_stats:
        if s["type"] == "python":
            suggestions.append(
                f"节点 {s['name']} 是 Python SOP，通常比 VEX 慢，考虑用 Wrangle SOP 替代"
            )

    return suggestions


def _get_hou(adapter):
    if adapter is not None and hasattr(adapter, "hou"):
        return adapter.hou
    return None


def _mock_result(network_path, top_n):
    return {
        "network": network_path or "/obj/geo1",
        "total_nodes": 5,
        "slow_nodes": [
            {"name": "scatter1", "type": "scatter", "cook_time_ms": 45.2, "points": 50000, "prims": 0},
            {"name": "vdbfrompolygons1", "type": "vdbfrompolygons", "cook_time_ms": 32.1, "points": 0, "prims": 1},
        ][:top_n],
        "geometry_growth": [],
        "error_nodes": [],
        "suggestions": ["(Mock data - enable force_cook for real measurements)"],
    }
