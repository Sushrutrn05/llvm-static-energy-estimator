#!/usr/bin/env python3
"""
LLVM Energy Report Dashboard

Reads reports/energy_report.json and produces a self-contained HTML
dashboard with KPI cards, hotspot analysis, optimization advisories,
and source code heatmap.

Usage:
  python scripts/visualize.py                          # default path
  python scripts/visualize.py path/to/report.json      # custom path
"""

import json
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
    """Format energy values: int if round, else 2 decimals."""
    if abs(val - round(val)) < 0.005:
        return f"{val:.0f}"
    return f"{val:.2f}"


def _rank_color(r):
    """Return CSS color for hotspot rank badge."""
    return ["#e53e3e", "#dd6b20", "#d69e2e"][r - 1] if 1 <= r <= 3 else "#718096"


def _heat_bg(ratio):
    """Return background color for heatmap line based on energy ratio."""
    if ratio <= 0:
        return "#1e1e1e"
    elif ratio <= 0.25:
        return "#1a3a2a"
    elif ratio <= 0.50:
        return "#3a3a1a"
    elif ratio <= 0.75:
        return "#4a2a1a"
    else:
        return "#5a1a1a"


def _heat_fg(ratio):
    """Return text color for heatmap line."""
    return "#a0aec0" if ratio <= 0 else "#e2e8f0"


def generate_html(functions, output_path="reports/energy_report.html"):
    grand_total = sum(f["total_energy"] for f in functions)
    total_blocks = sum(len(f["blocks"]) for f in functions)
    top_hotspot = None
    for f in functions:
        hs = f.get("hotspots", [])
        if hs:
            p = hs[0].get("percent", 0)
            if top_hotspot is None or p > top_hotspot[1]:
                top_hotspot = (f["name"], p)

    css_vars = """
:root {
  --primary: #1a202c;
  --primary-light: #2d3748;
  --accent: #2b6cb0;
  --green: #38a169;
  --amber: #d69e2e;
  --red: #e53e3e;
  --bg: #edf2f7;
  --surface: #ffffff;
  --text: #2d3748;
  --text-muted: #718096;
  --border: #e2e8f0;
  --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
  --shadow-lg: 0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.06);
  --radius: 8px;
  --radius-sm: 6px;
}"""

    css = css_vars + """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Inter", "Segoe UI", Roboto, -apple-system, sans-serif;
  background: var(--bg); color: var(--text); padding: 24px 16px;
  line-height: 1.5;
}
.container { max-width: 1120px; margin: 0 auto; }

/* Header */
.header { margin-bottom: 28px; }
.header h1 {
  font-size: 1.6rem; font-weight: 700; color: var(--primary);
  letter-spacing: -0.02em;
}
.header p { color: var(--text-muted); font-size: 0.9rem; margin-top: 2px; }

/* KPI grid */
.kpi-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px; margin-bottom: 28px;
}
.kpi {
  background: var(--surface); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 18px 20px; border: 1px solid var(--border);
}
.kpi .label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
              color: var(--text-muted); font-weight: 600; }
.kpi .value { font-size: 1.65rem; font-weight: 700; color: var(--primary);
              margin-top: 4px; letter-spacing: -0.02em; }
.kpi .sub { font-size: 0.8rem; color: var(--text-muted); margin-top: 2px; }

/* Card */
.card {
  background: var(--surface); border-radius: var(--radius);
  box-shadow: var(--shadow); border: 1px solid var(--border);
  margin-bottom: 20px; overflow: hidden;
}
.card-header {
  padding: 14px 20px; border-bottom: 1px solid var(--border);
  font-size: 0.85rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; color: var(--primary);
  background: #fafbfc;
}
.card-body { padding: 16px 20px; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
th { text-align: left; padding: 8px 10px; font-weight: 600;
     color: var(--text-muted); font-size: 0.78rem; text-transform: uppercase;
     letter-spacing: 0.04em; border-bottom: 2px solid var(--border); }
td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
tr:last-child td { border-bottom: none; }
tr.highlight { background: #fff5f5; }

/* Hotspot cards */
.hotspot-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px; margin-top: 4px;
}
.hotspot-card {
  border-radius: var(--radius-sm); padding: 16px 18px;
  border: 1px solid var(--border); position: relative;
}
.hotspot-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 50%;
  color: #fff; font-weight: 700; font-size: 0.85rem;
  margin-bottom: 8px;
}
.hotspot-card .block-name {
  font-weight: 700; font-size: 0.95rem; color: var(--primary);
  margin-bottom: 6px;
}
.hotstat { display: flex; justify-content: space-between; font-size: 0.85rem;
           margin-top: 4px; }
.hotstat .stat-label { color: var(--text-muted); }
.hotstat .stat-value { font-weight: 600; }

/* Advisor cards */
.advisor-list { display: flex; flex-direction: column; gap: 12px; }
.advisor-card {
  border-radius: var(--radius-sm); padding: 14px 16px;
  border-left: 4px solid var(--accent); background: #f7fafc;
}
.advisor-card .obs { font-size: 0.85rem; color: var(--text-muted); }
.advisor-card .rec {
  font-size: 0.92rem; font-weight: 600; color: var(--primary);
  margin-top: 4px;
}
.advisor-card .ben {
  font-size: 0.82rem; color: var(--green); font-weight: 500;
  margin-top: 3px;
}

/* Heatmap */
.heatmap-wrap { margin-top: 4px; }
.heatmap-code {
  background: #1e1e1e; border-radius: var(--radius-sm);
  padding: 10px 0; overflow-x: auto; font-family: "JetBrains Mono",
  "Fira Code", "Cascadia Code", "Consolas", monospace;
  font-size: 0.82rem; line-height: 1.65; tab-size: 4;
}
.heatmap-line {
  display: flex; padding: 0 14px; white-space: pre;
  transition: filter 0.1s;
}
.heatmap-line:hover { filter: brightness(1.3); }
.heatmap-lineno {
  color: #4a5568; min-width: 3.6em; text-align: right;
  padding-right: 14px; user-select: none; flex-shrink: 0;
}
.heatmap-code-text { flex: 1; }
.heatmap-legend {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-top: 10px; padding: 8px 14px; background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  font-size: 0.78rem; color: var(--text-muted);
}
.legend-item { display: flex; align-items: center; gap: 5px; }
.legend-swatch {
  width: 14px; height: 14px; border-radius: 3px;
  border: 1px solid rgba(0,0,0,0.1); flex-shrink: 0;
}

/* Footer */
.footer {
  text-align: center; color: var(--text-muted); font-size: 0.8rem;
  margin: 32px 0 12px; padding-top: 20px;
  border-top: 1px solid var(--border);
}

/* Responsive */
@media (max-width: 640px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .hotspot-grid { grid-template-columns: 1fr; }
}
"""

    html = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>LLVM Energy Report</title>",
        "<link rel='preconnect' href='https://fonts.googleapis.com'>",
        "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap' rel='stylesheet'>",
        f"<style>{css}</style></head><body>",
        "<div class='container'>",
        "<div class='header'>",
        "<h1>Energy Analysis Report</h1>",
        f"<p>{len(functions)} function(s) &middot; {_fmt(grand_total)} total energy</p>",
        "</div>",
    ]

    # -- KPI cards --
    top_pct = top_hotspot[1] if top_hotspot else 0
    top_name = top_hotspot[0] if top_hotspot else ""
    html.append("<div class='kpi-grid'>")
    html.append(f"<div class='kpi'><div class='label'>Total Energy</div>"
                f"<div class='value'>{_fmt(grand_total)}</div>"
                f"<div class='sub'>across all functions</div></div>")
    html.append(f"<div class='kpi'><div class='label'>Functions</div>"
                f"<div class='value'>{len(functions)}</div>"
                f"<div class='sub'>analyzed</div></div>")
    html.append(f"<div class='kpi'><div class='label'>Basic Blocks</div>"
                f"<div class='value'>{total_blocks}</div>"
                f"<div class='sub'>across all functions</div></div>")
    html.append(f"<div class='kpi'><div class='label'>Top Hotspot</div>"
                f"<div class='value'>{_fmt(top_pct)}%</div>"
                f"<div class='sub'>{top_name}</div></div>")
    html.append("</div>")

    # -- Function Summary --
    html.append("<div class='card'>")
    html.append("<div class='card-header'>Function Summary</div>")
    html.append("<div class='card-body'>")
    html.append("<table><tr><th>Function</th><th>Blocks</th>"
                "<th>Total Energy</th><th>Avg / Block</th><th>Top Hotspot</th></tr>")
    for f in functions:
        nb = len(f["blocks"])
        avg = f["total_energy"] / nb if nb else 0
        hs = f.get("hotspots", [])
        top_hs_name = hs[0]["name"] if hs else ""
        top_hs_pct = hs[0].get("percent", 0) if hs else 0
        top_hs_str = f"{top_hs_name} ({_fmt(top_hs_pct)}%)" if hs else ""
        html.append(
            f"<tr><td><strong>{f['name']}</strong></td>"
            f"<td>{nb}</td>"
            f"<td><strong>{_fmt(f['total_energy'])}</strong></td>"
            f"<td>{_fmt(avg)}</td>"
            f"<td style='color:var(--red);'>{top_hs_str}</td></tr>")
    html.append("</table>")
    html.append("</div></div>")

    # -- Per-function sections --
    for func in functions:
        name = func["name"]
        total = func["total_energy"]
        blocks = func["blocks"]
        max_en = max((b["energy"] for b in blocks), default=0)
        hotspots = func.get("hotspots", [])
        advisories = func.get("advisories", [])

        html.append(f"<div class='card'>")
        html.append(f"<div class='card-header'>{name} "
                    f"&mdash; {_fmt(total)} total energy</div>")
        html.append(f"<div class='card-body'>")

        # Block table
        html.append("<table><tr><th>Block</th><th>Frequency</th><th>Energy</th></tr>")
        for b in blocks:
            hl = " class='highlight'" if b["energy"] == max_en else ""
            html.append(f"<tr{hl}><td>{b['name']}</td>"
                        f"<td>{_fmt(b['frequency'])}</td>"
                        f"<td>{_fmt(b['energy'])}</td></tr>")
        html.append("</table>")

        # Hotspots
        if hotspots:
            html.append("<div style='margin-top:16px;'>"
                        "<h4 style='font-size:0.82rem;font-weight:700;"
                        "text-transform:uppercase;letter-spacing:0.04em;"
                        "color:var(--text-muted);margin-bottom:8px;'>"
                        "Top Hotspots</h4>")
            html.append("<div class='hotspot-grid'>")
            for rank, h in enumerate(hotspots, 1):
                c = _rank_color(rank)
                html.append(
                    f"<div class='hotspot-card' "
                    f"style='background:{c}08;border-left:4px solid {c};'>"
                    f"<div class='hotspot-badge' style='background:{c};'>"
                    f"#{rank}</div>"
                    f"<div class='block-name'>{h['name']}</div>"
                    f"<div class='hotstat'>"
                    f"<span class='stat-label'>Energy</span>"
                    f"<span class='stat-value'>{_fmt(h['energy'])}</span>"
                    f"</div>"
                    f"<div class='hotstat'>"
                    f"<span class='stat-label'>Contribution</span>"
                    f"<span class='stat-value' style='color:{c};'>"
                    f"{_fmt(h['percent'])}%</span></div></div>")
            html.append("</div></div>")

        # Advisor
        if advisories:
            html.append("<div style='margin-top:16px;'>"
                        "<h4 style='font-size:0.82rem;font-weight:700;"
                        "text-transform:uppercase;letter-spacing:0.04em;"
                        "color:var(--text-muted);margin-bottom:8px;'>"
                        "Optimization Advisory</h4>")
            html.append("<div class='advisor-list'>")
            for adv in advisories:
                html.append(
                    f"<div class='advisor-card'>"
                    f"<div class='obs'>{adv['observation']}</div>"
                    f"<div class='rec'>{adv['recommendation']}</div>"
                    f"<div class='ben'>{adv['benefit']}</div></div>")
            html.append("</div></div>")

        # Heatmap
        source_file = func.get("source_file", "")
        source_lines = func.get("source_lines", [])
        if source_file and source_lines:
            src_path = os.path.normpath(source_file)
            line_energy = {sl["line"]: sl["energy"]
                           for sl in source_lines if sl["line"] > 0}
            max_line_en = max(line_energy.values()) if line_energy else 1

            html.append("<div style='margin-top:16px;'>"
                        "<h4 style='font-size:0.82rem;font-weight:700;"
                        "text-transform:uppercase;letter-spacing:0.04em;"
                        "color:var(--text-muted);margin-bottom:8px;'>"
                        "Source Code Heatmap</h4>")
            html.append("<div class='heatmap-wrap'>")
            html.append(f"<div class='heatmap-code'>"
                        f"<div style='padding:0 14px 6px;color:#4a5568;"
                        f"font-size:0.75rem;border-bottom:1px solid #333;"
                        f"margin-bottom:4px;'>{source_file}</div>")

            try:
                with open(src_path, "r", encoding="utf-8") as fh:
                    src_lines = fh.readlines()
                for i, src_line in enumerate(src_lines, 1):
                    en = line_energy.get(i, 0)
                    r = en / max_line_en if max_line_en > 0 else 0
                    bg = _heat_bg(r)
                    fg = _heat_fg(r)
                    ln = f"{i:4d}"
                    code = src_line.rstrip()
                    title = f"Line {i}: {_fmt(en)} energy" if en > 0 else ""
                    html.append(
                        f"<div class='heatmap-line' style='background:{bg};' "
                        f"title='{title}'>"
                        f"<span class='heatmap-lineno'>{ln}</span>"
                        f"<span class='heatmap-code-text' "
                        f"style='color:{fg};'>{code}</span></div>")
            except FileNotFoundError:
                html.append(
                    f"<div style='padding:14px;color:var(--text-muted);"
                    f"font-size:0.85rem;'>Source file not found: "
                    f"{source_file}</div>")

            html.append("</div>")  # heatmap-code
            # Legend
            html.append(
                "<div class='heatmap-legend'>"
                "<span>Energy scale:</span>"
                "<span class='legend-item'>"
                "<span class='legend-swatch' style='background:#1e1e1e;'>"
                "</span> none</span>"
                "<span class='legend-item'>"
                "<span class='legend-swatch' style='background:#1a3a2a;'>"
                "</span> low</span>"
                "<span class='legend-item'>"
                "<span class='legend-swatch' style='background:#3a3a1a;'>"
                "</span> medium</span>"
                "<span class='legend-item'>"
                "<span class='legend-swatch' style='background:#4a2a1a;'>"
                "</span> high</span>"
                "<span class='legend-item'>"
                "<span class='legend-swatch' style='background:#5a1a1a;'>"
                "</span> very high</span>"
                "</div>")
            html.append("</div></div>")  # heatmap-wrap + margin div

        html.append("</div></div>")  # card-body, card

    # -- Footer --
    html.append(
        "<div class='footer'>"
        "Generated by LLVM Static Energy Estimation Framework</div>")
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
    print("\n[*] Generating HTML dashboard ...")
    generate_html(functions)
    print("\n[Done] reports/energy_report.html")


if __name__ == "__main__":
    main()
