#!/usr/bin/env python3
"""
Generate HTML report from energy_report.json.

Usage:
  python scripts/visualize.py
  python scripts/visualize.py path/to/report.json
"""

import json
import math
import sys
import os


def load_report(path="reports/energy_report.json"):
    if not os.path.exists(path):
        print(f"[ERROR] Report not found: {path}")
        sys.exit(1)
    with open(path) as f:
        data = json.load(f)
    try:
        return data["report"]["functions"]
    except KeyError:
        print("[ERROR] Invalid report format")
        sys.exit(1)


def _fmt(val):
    if abs(val - round(val)) < 0.005:
        return f"{val:.0f}"
    return f"{val:.2f}"


def _heat_bg(ratio):
    if ratio <= 0:
        return "#1e1e1e"
    elif ratio <= 0.25:
        return "#1a472a"
    elif ratio <= 0.50:
        return "#7d6608"
    elif ratio <= 0.75:
        return "#7b241c"
    else:
        return "#c0392b"


def _heat_fg(ratio):
    return "#a0aec0" if ratio <= 0 else "#e2e8f0"


def generate_html(functions, output_path="reports/energy_report.html"):
    grand_total = sum(f["total_energy"] for f in functions)
    total_blocks = sum(len(f["blocks"]) for f in functions)

    css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  background: #f5f5f5; color: #222; padding: 20px 12px;
  line-height: 1.5;
}
.container { max-width: 1000px; margin: 0 auto; }
h1 { font-size: 1.4rem; margin-bottom: 4px; }
h2 { font-size: 1.1rem; margin-bottom: 8px; }
.subtitle { color: #666; font-size: 0.9rem; margin-bottom: 20px; }
.card {
  background: #fff; border-radius: 6px; border: 1px solid #ddd;
  margin-bottom: 16px; overflow: hidden;
}
.card-title {
  padding: 10px 16px; border-bottom: 1px solid #eee;
  font-weight: 600; font-size: 0.9rem; background: #fafafa;
}
.card-body { padding: 12px 16px; }
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
th { text-align: left; padding: 6px 8px; font-weight: 600;
     color: #666; font-size: 0.78rem; border-bottom: 2px solid #ddd; }
td { padding: 6px 8px; border-bottom: 1px solid #eee; }
tr.max td { background: #fff0f0; }

.section-title {
  font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; color: #666; margin: 14px 0 6px;
}

/* Hotspot cards */
.hspot-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.hspot-card {
  flex: 1; min-width: 180px; border-radius: 5px; padding: 12px 14px;
  border: 1px solid #ddd;
}
.hspot-rank {
  display: inline-block; width: 26px; height: 26px; border-radius: 50%;
  color: #fff; font-weight: 700; font-size: 0.8rem;
  text-align: center; line-height: 26px; margin-bottom: 6px;
}
.hspot-name { font-weight: 700; font-size: 0.9rem; margin-bottom: 4px; }
.hspot-row { display: flex; justify-content: space-between; font-size: 0.85rem; }
.hspot-label { color: #888; }
.hspot-val { font-weight: 600; }

/* Advisor cards */
.advice-list { display: flex; flex-direction: column; gap: 8px; }
.advice {
  padding: 10px 14px; border-radius: 5px;
  border-left: 4px solid #2b6cb0; background: #f7fafc;
}
.advice .obs { font-size: 0.85rem; color: #555; }
.advice .rec { font-size: 0.92rem; font-weight: 600; margin-top: 3px; }
.advice .ben { font-size: 0.82rem; color: #2f855a; margin-top: 2px; }

/* Heatmap */
.heatmap {
  background: #1e1e1e; border-radius: 5px; padding: 8px 0;
  overflow-x: auto; font-family: "Consolas", "Courier New", monospace;
  font-size: 0.82rem; line-height: 1.6;
}
.heatmap-line {
  display: flex; padding: 0 12px; white-space: pre;
}
.heatmap-line:hover { filter: brightness(1.25); }
.heatmap-ln {
  color: #555; min-width: 3.4em; text-align: right;
  padding-right: 12px; user-select: none; flex-shrink: 0;
}
.heatmap-src { flex: 1; }
.legend {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-top: 8px; padding: 6px 12px;
  font-size: 0.78rem; color: #666;
}
.legend-swatch {
  display: inline-block; width: 12px; height: 12px; border-radius: 2px;
  border: 1px solid rgba(0,0,0,0.1); vertical-align: middle;
}

.footer {
  text-align: center; color: #888; font-size: 0.8rem;
  margin: 24px 0 8px; padding-top: 16px;
  border-top: 1px solid #ddd;
}
"""

    html = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>LLVM Energy Report</title>",
        f"<style>{css}</style></head><body>",
        "<div class='container'>",
        "<h1>Energy Analysis Report</h1>",
        f"<div class='subtitle'>{len(functions)} function(s) &middot; "
        f"{_fmt(grand_total)} total energy &middot; "
        f"{total_blocks} blocks</div>",
    ]

    # Function summary table
    html.append("<div class='card'><div class='card-title'>Function Summary</div>"
                "<div class='card-body'>")
    html.append("<table><tr><th>Function</th><th>Blocks</th>"
                "<th>Total Energy</th><th>Avg/Block</th></tr>")
    for f in functions:
        nb = len(f["blocks"])
        avg = f["total_energy"] / nb if nb else 0
        html.append(
            f"<tr><td><strong>{f['name']}</strong></td>"
            f"<td>{nb}</td>"
            f"<td><strong>{_fmt(f['total_energy'])}</strong></td>"
            f"<td>{_fmt(avg)}</td></tr>")
    html.append("</table></div></div>")

    # Per-function sections
    for func in functions:
        name = func["name"]
        total = func["total_energy"]
        blocks = func["blocks"]
        max_en = max((b["energy"] for b in blocks), default=0)
        hotspots = func.get("hotspots", [])
        advisories = func.get("advisories", [])

        html.append(f"<div class='card'>")
        html.append(f"<div class='card-title'>{name} &mdash; {_fmt(total)} total</div>")
        html.append(f"<div class='card-body'>")

        # Block table
        html.append("<table><tr><th>Block</th><th>Frequency</th><th>Energy</th></tr>")
        for b in blocks:
            hl = " class='max'" if b["energy"] == max_en else ""
            html.append(f"<tr{hl}><td>{b['name']}</td>"
                        f"<td>{_fmt(b['frequency'])}</td>"
                        f"<td>{_fmt(b['energy'])}</td></tr>")
        html.append("</table>")

        # Hotspots
        if hotspots:
            html.append("<div class='section-title'>Hotspots</div>"
                        "<div class='hspot-grid'>")
            colors = ["#e53e3e", "#dd6b20", "#d69e2e"]
            for rank, h in enumerate(hotspots, 1):
                c = colors[rank - 1] if rank <= 3 else "#888"
                html.append(
                    f"<div class='hspot-card'"
                    f" style='border-left:4px solid {c};'>"
                    f"<div class='hspot-rank' style='background:{c};'>{rank}</div>"
                    f"<div class='hspot-name'>{h['name']}</div>"
                    f"<div class='hspot-row'>"
                    f"<span class='hspot-label'>Energy</span>"
                    f"<span class='hspot-val'>{_fmt(h['energy'])}</span></div>"
                    f"<div class='hspot-row'>"
                    f"<span class='hspot-label'>Contribution</span>"
                    f"<span class='hspot-val'>{_fmt(h['percent'])}%</span></div>"
                    f"</div>")
            html.append("</div>")

        # Advisor
        if advisories:
            html.append("<div class='section-title'>Advisory</div>"
                        "<div class='advice-list'>")
            for adv in advisories:
                html.append(
                    f"<div class='advice'>"
                    f"<div class='obs'>{adv['observation']}</div>"
                    f"<div class='rec'>{adv['recommendation']}</div>"
                    f"<div class='ben'>{adv['benefit']}</div></div>")
            html.append("</div>")

        html.append("</div></div>")  # card-body, card

    # --- Unified heatmap: one per source file, merging line energy across all functions ---
    by_source = {}
    for func in functions:
        sf = func.get("source_file", "")
        if not sf:
            continue
        if sf not in by_source:
            by_source[sf] = {}
        for sl in func.get("source_lines", []):
            line = sl.get("line", 0)
            if line <= 0:
                continue
            by_source[sf][line] = by_source[sf].get(line, 0) + sl.get("energy", 0)

    for source_file, line_energy in by_source.items():
        src_path = os.path.normpath(source_file)
        max_line_en = max(line_energy.values()) if line_energy else 1

        html.append("<div class='card'>"
                    "<div class='card-title'>Source Heatmap</div>"
                    "<div class='card-body'>")
        html.append(
            f"<div style='font-size:0.8rem;color:#888;margin-bottom:4px;'>"
            f"{source_file}</div>")
        html.append("<div class='heatmap'>")

        try:
            with open(src_path, "r", encoding="utf-8") as fh:
                src_lines = fh.readlines()
            for i, src_line in enumerate(src_lines, 1):
                en = line_energy.get(i, 0)
                r = (math.log(1 + en) / math.log(1 + max_line_en)) if max_line_en > 0 else 0
                bg = _heat_bg(r)
                fg = _heat_fg(r)
                ln = f"{i:4d}"
                code = src_line.rstrip()
                title = f"L{i}: {_fmt(en)}" if en > 0 else ""
                html.append(
                    f"<div class='heatmap-line' style='background:{bg};'"
                    f" title='{title}'>"
                    f"<span class='heatmap-ln'>{ln}</span>"
                    f"<span class='heatmap-src' style='color:{fg};'>"
                    f"{code}</span></div>")
        except FileNotFoundError:
            html.append(
                f"<div style='padding:12px;color:#888;font-size:0.85rem;'>"
                f"Source file not found: {source_file}</div>")

        html.append("</div>")  # heatmap
        html.append(
            "<div class='legend'>"
            "Scale: "
            "<span><span class='legend-swatch' style='background:#1e1e1e;'>"
            "</span> none</span> "
            "<span><span class='legend-swatch' style='background:#1a472a;'>"
            "</span> low</span> "
            "<span><span class='legend-swatch' style='background:#7d6608;'>"
            "</span> medium</span> "
            "<span><span class='legend-swatch' style='background:#7b241c;'>"
            "</span> high</span> "
            "<span><span class='legend-swatch' style='background:#c0392b;'>"
            "</span> very high</span>"
            "</div>")
        html.append("</div></div>")  # card-body, card

    html.append(
        "<div class='footer'>Generated by LLVM Static Energy Estimator</div>")
    html.append("</div></body></html>")

    out = "\n".join(html)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"  [OK] HTML report -> {output_path}")


def main():
    report_path = sys.argv[1] if len(sys.argv) > 1 else "reports/energy_report.json"
    print("[*] Loading report:", report_path)
    functions = load_report(report_path)
    print(f"[*] Found {len(functions)} function(s)\n")
    for f in functions:
        print(f"    {f['name']:15s}  blocks: {len(f['blocks']):3d}  "
              f"total energy: {f['total_energy']:8.2f}")
    print("\n[*] Generating HTML report ...")
    generate_html(functions)
    print("\n[Done] reports/energy_report.html")


if __name__ == "__main__":
    main()
