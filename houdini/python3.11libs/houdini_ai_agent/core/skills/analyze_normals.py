# -*- coding: utf-8 -*-
"""Normal quality analysis skill.

Detects NaN/Inf/zero/unnormalized normals and flipped faces in geometry.
"""

import math

SKILL_INFO = {
    "name": "analyze_normals",
    "label": "Analyze Normals",
    "description": (
        "分析节点几何体的法线质量。检测 NaN、Inf、零向量、未归一化法线和翻转面。"
        "返回各类问题数量和详细信息。"
    ),
    "parameters": {
        "node_path": {
            "type": "string",
            "description": "节点路径",
            "required": True,
        },
        "tolerance": {
            "type": "float",
            "description": "归一化容差（默认 0.001）",
            "required": False,
        },
        "flip_angle_threshold": {
            "type": "float",
            "description": "翻转面检测角度阈值（度，默认 120）",
            "required": False,
        },
        "max_sample": {
            "type": "integer",
            "description": "最大采样数（默认 200000）",
            "required": False,
        },
    },
}


def run(adapter=None, node_path="", tolerance=0.001, flip_angle_threshold=120.0,
        max_sample=200000, **kwargs):
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

    max_sample = min(int(max_sample), 500000)
    tolerance = float(tolerance)
    flip_rad = math.radians(float(flip_angle_threshold))

    issues = []
    normals = []
    prim_normals = []

    # Check if N attribute exists
    n_attr = geo.findPointAttrib("N")
    if n_attr is None:
        issues.append({
            "type": "NO_NORMAL",
            "severity": "WARNING",
            "message": "几何体没有法线属性 N",
        })
        return {"node": node_path, "issues": issues, "total_points": len(geo.points())}

    points = list(geo.points())
    total = len(points)
    sampled = points[:max_sample] if total > max_sample else points

    nan_count = 0
    inf_count = 0
    zero_count = 0
    non_normalized_count = 0

    for pt in sampled:
        try:
            raw = pt.attribValue(n_attr)
            nx, ny, nz = float(raw[0]), float(raw[1]), float(raw[2])
            if math.isnan(nx) or math.isnan(ny) or math.isnan(nz):
                nan_count += 1
                continue
            if math.isinf(nx) or math.isinf(ny) or math.isinf(nz):
                inf_count += 1
                continue
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            if length < 1e-10:
                zero_count += 1
                continue
            if abs(length - 1.0) > tolerance:
                non_normalized_count += 1
            normals.append((nx, ny, nz))
        except Exception:
            continue

    if nan_count > 0:
        issues.append({"type": "NAN_NORMAL", "severity": "ERROR", "count": nan_count,
                        "message": f"{nan_count} 点法线含 NaN"})
    if inf_count > 0:
        issues.append({"type": "INF_NORMAL", "severity": "ERROR", "count": inf_count,
                        "message": f"{inf_count} 点法线含 Inf"})
    if zero_count > 0:
        issues.append({"type": "ZERO_NORMAL", "severity": "WARNING", "count": zero_count,
                        "message": f"{zero_count} 点法线为零向量"})
    if non_normalized_count > 0:
        issues.append({"type": "NON_NORMALIZED", "severity": "INFO", "count": non_normalized_count,
                        "message": f"{non_normalized_count} 点法线未归一化"})

    # Flipped face detection
    flipped_count = 0
    try:
        flipped_count = _detect_flipped_faces(geo, flip_rad, max_sample)
        if flipped_count > 0:
            issues.append({"type": "FLIPPED_FACES", "severity": "WARNING", "count": flipped_count,
                            "message": f"检测到 {flipped_count} 个可能翻转的面"})
    except Exception:
        pass

    return {
        "node": node_path,
        "total_points": total,
        "sampled_points": len(sampled),
        "valid_normals": len(normals),
        "issues": issues,
        "summary": f"{len(issues)} issue(s) found" if issues else "法线质量正常",
    }


def _detect_flipped_faces(geo, angle_threshold, max_sample):
    """Detect flipped faces by checking neighboring face normal angles."""
    n_attr = geo.findPointAttrib("N")
    if n_attr is None:
        return 0

    points = list(geo.points())
    prims = list(geo.prims())

    # Build point -> prims adjacency
    point_prims = {}
    for prim in prims:
        try:
            for vert in prim.vertices():
                pt = vert.point()
                pt_num = pt.number()
                if pt_num not in point_prims:
                    point_prims[pt_num] = []
                point_prims[pt_num].append(prim)
        except Exception:
            continue

    flipped = 0
    checked = set()
    for prim in prims[:max_sample]:
        try:
            prim_id = prim.number()
            if prim_id in checked:
                continue
            checked.add(prim_id)

            # Get prim normal
            pn = prim.normal()
            pnx, pny, pnz = float(pn[0]), float(pn[1]), float(pn[2])

            # Find adjacent prims
            neighbor_prims = set()
            for vert in prim.vertices():
                pt = vert.point()
                for adj_prim in point_prims.get(pt.number(), []):
                    adj_id = adj_prim.number()
                    if adj_id != prim_id and adj_id not in checked:
                        neighbor_prims.add(adj_prim)

            for adj_id in neighbor_prims:
                adj_prim = geo.prim(adj_id)
                if adj_prim is None:
                    continue
                an = adj_prim.normal()
                anx, any_, anz = float(an[0]), float(an[1]), float(an[2])

                dot = pnx * anx + pny * any_ + pnz * anz
                dot = max(-1.0, min(1.0, dot))
                angle = math.acos(dot)

                if angle > angle_threshold:
                    flipped += 1
        except Exception:
            continue

    return flipped


def _get_hou(adapter):
    if adapter is not None and hasattr(adapter, "hou"):
        return adapter.hou
    return None


def _mock_result(node_path):
    return {
        "node": node_path,
        "total_points": 1000,
        "sampled_points": 1000,
        "valid_normals": 998,
        "issues": [
            {"type": "NON_NORMALIZED", "severity": "INFO", "count": 2,
             "message": "2 点法线未归一化"},
        ],
        "summary": "1 issue(s) found (mock data)",
    }
