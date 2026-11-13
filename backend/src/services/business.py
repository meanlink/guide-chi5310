"""场馆导览方案的独立性核验与分区转化口径。"""
import math
import random
import numpy as np
from scipy import stats

# 口径版本写入每份结果，便于结果页与简报核对；历史结果不因代码升级而被改写。
RULE_VERSION = "v2-zone-standardized"
RULE_LABEL = "按展区两方案合计客流占比校正"
ADJUSTMENT_METHOD = (
    "以同时具备 A/B 方案记录的展区为校正集，权重=该展区两方案合计进区人数/校正集合计进区人数；"
    "校正完成率=Σ(权重×该展区各方案完成率)。缺少任一方案的展区单列原因、不纳入校正，"
    "仍保留在原始汇总中。"
)


def metadata():
    return {"name": "场馆导览转化核验", "short": "guide-chi", "tagline": "把进区人数与完成讲解分开，核验导览方案的关联强度。", "client": "拾光科学馆 · 24 人运营团队，比较两套自助导览提示", "workflow": "运营员汇总分区入场和完成讲解人数，以转化率高低选择导览牌。", "pains": ["高客流分区掩盖其他区域", "未核对列联表期望频数", "把关联误写成方案因果效果"], "upstream": "匿名分区客流 SG_guide_counts.csv", "downstream": "展陈运营组据分区证据安排随机导览试点",
            "entities": ["分区导览计数", "独立性核验", "展陈评审简报"], "dataset_name": "三展区 · 20 日 A/B 导览计数",
            "columns": [{"key": "record", "label": "记录", "type": "string"}, {"key": "zone", "label": "展区", "type": "string"}, {"key": "arm", "label": "导览方案", "type": "string"}, {"key": "visitors", "label": "进区人数", "type": "number"}, {"key": "completed", "label": "完成讲解人数", "type": "number"}],
            "parameters": [{"key": "zone", "label": "分析展区", "type": "select", "default": "全部", "options": [{"value": x, "label": x} for x in ["全部", "星空厅", "水世界", "机械坊"]]}, {"key": "alpha", "label": "显著性水平", "type": "select", "default": "0.05", "options": [{"value": str(x), "label": str(x)} for x in [.01, .05, .1]]}],
            "workbench_title": "导览列联核验", "action_label": "构建列联表并检验", "unit": "人", "accent": "oklch(56% 0.15 18)", "style": "gallery",
            "rule_version": RULE_VERSION, "rule_label": RULE_LABEL,
            "seed_story": ["08:30 导入 SG_guide_counts.csv，三展区共 120 条日计数。", "08:45 核对完成数不超过进区人数。", "09:00 选择全部展区，显著性水平 0.05。", "09:05 运行核验，查看完成/未完成列联表。", "09:20 检查最小期望频数及 Cramer V。", "09:40 分别选水世界与机械坊，比较分区差异。", "10:00 导出评审简报，计划按访客随机分组的后续试点。"],
            "method": "汇总 A/B×完成/未完成 2×2 列联表，Pearson χ² 不使用连续性校正；Cramer V=√(χ²/N)；最小期望频数低于 5 时提示近似条件不足。另以同时具备 A/B 记录的展区为校正集，按各展区两方案合计进区人数占比加权计算校正完成率；缺少任一方案的展区单列原因，不纳入校正，原始汇总仍包含全部展区。", "limitations": ["按日汇总可能存在访客重复和聚类", "全部展区汇总可能受分区构成影响", "构成校正只消除展区客流占比差异，未控制日期、访客重复和混淆因素", "关联不等同于因果提升"]}


def seed_records():
    rng = random.Random(1005)
    rows = []
    for zone, base, uplift in [("星空厅", .42, .10), ("水世界", .63, .025), ("机械坊", .31, -.015)]:
        for day in range(20):
            for arm in ("A", "B"):
                visitors = rng.randint(55, 100)
                p = base + (uplift if arm == "B" else 0)
                completed = sum(rng.random() < p for _ in range(visitors))
                rows.append({"record": f"{zone}-{day+1:02}-{arm}", "zone": zone, "arm": arm, "visitors": visitors, "completed": completed})
    return rows


def _direction(diff):
    if diff is None:
        return "不可计算"
    if abs(diff) < 1e-9:
        return "持平"
    return "B 高" if diff > 0 else "A 高"


def _sum_visitors(entries):
    return {"A": sum(e["visitors"]["A"] for e in entries),
            "B": sum(e["visitors"]["B"] for e in entries),
            "total": sum(e["visitors"]["total"] for e in entries)}


def analyze(records, params):
    zone = str(params.get("zone", "全部"))
    try:
        alpha = float(params.get("alpha", .05))
    except (ValueError, TypeError):
        raise ValueError("显著性水平必须为 0.01/0.05/0.1")
    if alpha not in (.01, .05, .1) or zone not in ("全部", "星空厅", "水世界", "机械坊"):
        raise ValueError("未知展区或显著性水平")
    total = {"A": [0, 0], "B": [0, 0]}
    zone_stats = {}
    for r in records:
        try:
            v, c = float(r["visitors"]), float(r["completed"])
            name, arm = str(r["zone"]), str(r["arm"])
            if arm not in total or not all(math.isfinite(x) and x.is_integer() for x in (v, c)) or v <= 0 or not 0 <= c <= v:
                raise ValueError()
            if zone != "全部" and zone != name:
                continue
            total[arm][0] += int(c)
            total[arm][1] += int(v - c)
            bucket = zone_stats.setdefault(name, {}).setdefault(arm, [0, 0])
            bucket[0] += int(v)
            bucket[1] += int(c)
        except (ValueError, TypeError, KeyError):
            raise ValueError("方案须为 A/B，人数为整数，且 0≤完成≤进区")
    observed = np.array([total["A"], total["B"]], dtype=float)
    if np.any(observed.sum(axis=0) == 0) or np.any(observed.sum(axis=1) == 0):
        raise ValueError("两方案与两结果类别均须有样本")
    chi, p, df, expected = stats.chi2_contingency(observed, correction=False)
    n, min_expected = int(observed.sum()), float(expected.min())
    v = math.sqrt(float(chi) / n)
    rates = {a: total[a][0] / sum(total[a]) * 100 for a in ("A", "B")}
    rows = [{"zone": name, "arm": arm, "visitors": counts[0], "completed": counts[1], "incomplete": counts[0] - counts[1], "rate": round(counts[1] / counts[0] * 100, 4)} for name in sorted(zone_stats) for arm, counts in sorted(zone_stats[name].items())]

    # 分区构成校正：仅纳入同时具备 A/B 方案记录的展区；缺臂展区单列，不混入权重。
    included, excluded, zone_rows = [], [], []
    for name in sorted(zone_stats):
        stats_by_arm = zone_stats[name]
        missing = [a for a in ("A", "B") if a not in stats_by_arm]
        visitors = {a: int(stats_by_arm.get(a, [0, 0])[0]) for a in ("A", "B")}
        visitors["total"] = visitors["A"] + visitors["B"]
        completed = {a: int(stats_by_arm.get(a, [0, 0])[1]) for a in ("A", "B")}
        entry = {"zone": name, "missing_arms": missing, "visitors": visitors, "completed": completed}
        if missing:
            reason = "缺少 " + "、".join(missing) + " 方案记录"
            entry["reason"] = reason
            excluded.append(entry)
            status = "排除"
        else:
            reason = "两方案均有记录"
            entry["reason"] = reason
            entry["raw_rate"] = {a: completed[a] / visitors[a] * 100 for a in ("A", "B")}
            included.append(entry)
            status = "纳入"
        zone_rows.append({
            "zone": name, "status": status, "missing": "、".join(missing) or "—", "reason": reason,
            "visitors_a": visitors["A"], "visitors_b": visitors["B"], "visitors_total": visitors["total"],
            "share_pct": None,
            "rate_a": round(completed["A"] / visitors["A"] * 100, 4) if visitors["A"] else None,
            "rate_b": round(completed["B"] / visitors["B"] * 100, 4) if visitors["B"] else None,
        })
    included_visitors = _sum_visitors(included)
    excluded_visitors = _sum_visitors(excluded)
    overall_visitors = _sum_visitors(list(included) + list(excluded))
    pooled_diff = rates["B"] - rates["A"]
    computable = bool(included) and included_visitors["total"] > 0
    adjusted = None
    adjusted_diff = None
    direction_reversed = False
    if computable:
        for entry, row in zip(included, [r for r in zone_rows if r["status"] == "纳入"]):
            entry["share"] = entry["visitors"]["total"] / included_visitors["total"]
            row["share_pct"] = round(entry["share"] * 100, 4)
        adjusted_a = sum(e["share"] * e["raw_rate"]["A"] for e in included)
        adjusted_b = sum(e["share"] * e["raw_rate"]["B"] for e in included)
        adjusted_diff = adjusted_b - adjusted_a
        direction_reversed = (_direction(pooled_diff) != "持平" and _direction(adjusted_diff) != "持平"
                              and _direction(pooled_diff) != _direction(adjusted_diff))
        adjusted = {"label": "校正后", "a_rate": round(adjusted_a, 4), "b_rate": round(adjusted_b, 4),
                    "diff_pp": round(adjusted_diff, 4), "direction": _direction(adjusted_diff)}
    pooled = {"label": "原始汇总", "a_rate": round(rates["A"], 4), "b_rate": round(rates["B"], 4),
              "diff_pp": round(pooled_diff, 4), "direction": _direction(pooled_diff)}
    if computable:
        if direction_reversed:
            adjustment_summary = (f"原始汇总 B−A 为 {pooled_diff:+.3f} 个百分点（{pooled['direction']}）；"
                                  f"按各展区两方案合计客流占比校正后为 {adjusted_diff:+.3f} 个百分点"
                                  f"（{adjusted['direction']}），方向反转。")
        else:
            adjustment_summary = (f"原始汇总 B−A 为 {pooled_diff:+.3f} 个百分点（{pooled['direction']}）；"
                                  f"校正后为 {adjusted_diff:+.3f} 个百分点（{adjusted['direction']}），方向未反转。")
    else:
        adjustment_summary = "没有同时具备 A/B 方案记录的展区，未执行构成校正；原始汇总保留全部展区。"
    adjustment = {
        "rule_version": RULE_VERSION, "method": ADJUSTMENT_METHOD, "computable": computable,
        "included_zones": [e["zone"] for e in included],
        "excluded_zones": [{"zone": e["zone"], "missing_arms": e["missing_arms"], "reason": e["reason"], "visitors": e["visitors"]} for e in excluded],
        "visitors": {"included": included_visitors, "excluded": excluded_visitors, "overall": overall_visitors},
        "pooled": pooled,
        "adjusted": adjusted,
        "direction_reversed": direction_reversed,
        "summary": adjustment_summary,
        "table": {"columns": [{"key": "zone", "label": "展区"}, {"key": "status", "label": "校正状态"}, {"key": "missing", "label": "缺失方案"}, {"key": "reason", "label": "原因"}, {"key": "visitors_a", "label": "A 进区"}, {"key": "visitors_b", "label": "B 进区"}, {"key": "visitors_total", "label": "合计进区"}, {"key": "share_pct", "label": "权重 %"}, {"key": "rate_a", "label": "A 完成率 %"}, {"key": "rate_b", "label": "B 完成率 %"}],
                  "rows": zone_rows},
        "chart": ({"type": "bar", "labels": ["A 方案", "B 方案"], "series": [
            {"name": "原始汇总完成率 %", "values": [pooled["a_rate"], pooled["b_rate"]]},
            {"name": "校正完成率 %", "values": [adjusted["a_rate"], adjusted["b_rate"]]}]} if computable else None),
    }

    warnings = ["汇总分析未控制分区和日期的访客构成，不能直接归因于导览设计。"]
    if min_expected < 5:
        warnings.append("至少一个期望频数小于 5；χ² 渐近 p 值可靠性不足，请扩大样本或采用精确检验。")
    if excluded:
        detail = "、".join(f"{e['zone']}（{e['reason']}）" for e in excluded)
        warnings.append(f"以下展区未纳入构成校正，仅保留在原始汇总中：{detail}。")
    if computable and direction_reversed:
        warnings.append("构成校正后方案优劣方向发生反转；原始汇总的合并人数可能误导选择，请以校正比较和分区明细复核。")
    if not computable:
        warnings.append("没有同时具备 A/B 方案记录的展区，未执行构成校正。")
    elif len(included) == 1:
        warnings.append("仅一个展区纳入构成校正，校正完成率与该展区原始完成率一致。")
    findings = [f"A 完成 {total['A'][0]} / {sum(total['A'])}，B 完成 {total['B'][0]} / {sum(total['B'])}。",
                f"有效样本 N={n}，自由度={int(df)}；检验 α={alpha:g}。",
                f"构成校正纳入 {len(included)} 个展区（A 进区 {included_visitors['A']} / B 进区 {included_visitors['B']} / 合计 {included_visitors['total']} 人），排除 {len(excluded)} 个展区（合计 {excluded_visitors['total']} 人）。",
                "逐展区复核构成差异后再设计下一轮随机试点。"]
    return {"rule_version": RULE_VERSION, "rule_label": RULE_LABEL,
            "summary": f"{zone}：B−A 完成率差 {rates['B']-rates['A']:.3f} 个百分点，χ²={chi:.3f}，{'检出关联' if p < alpha else '未检出关联'}。",
            "metrics": [{"label": "Pearson χ²", "value": round(float(chi), 5)}, {"label": "p 值", "value": float(f"{p:.6g}")}, {"label": "Cramer V", "value": round(v, 5)}, {"label": "最小期望频数", "value": round(min_expected, 3)}],
            "table": {"columns": [{"key": "zone", "label": "展区"}, {"key": "arm", "label": "方案"}, {"key": "visitors", "label": "进区"}, {"key": "completed", "label": "完成"}, {"key": "incomplete", "label": "未完成"}, {"key": "rate", "label": "完成率 %"}], "rows": rows},
            "chart": {"type": "bar", "labels": ["A 方案", "B 方案"], "series": [{"name": "完成率 %", "values": [round(rates["A"], 4), round(rates["B"], 4)]}]},
            "adjustment": adjustment,
            "findings": findings, "method": metadata()["method"], "warnings": warnings}
