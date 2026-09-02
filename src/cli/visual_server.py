"""
visual_server.py — Zero-dependency embedded web server for M5 Visual Graph Browser.
Opens http://127.0.0.1:5555 to visualize AST symbols, callers, callees, blast radius,
and call flows directly in your browser.
"""

import os
import sys
import json
import webbrowser
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Any

from src.storage.local_db import LocalCodeGraphDB

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>M5 — Code Knowledge Graph Browser</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0b0f19;
            --bg-surface: #111827;
            --bg-card: #1e293b;
            --border-color: #334155;
            --accent-primary: #3b82f6;
            --accent-glow: rgba(59, 130, 246, 0.25);
            --accent-green: #10b981;
            --accent-purple: #8b5cf6;
            --accent-orange: #f59e0b;
            --accent-red: #ef4444;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --font-main: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-primary);
            color: var(--text-main);
            font-family: var(--font-main);
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }

        header {
            background-color: var(--bg-surface);
            border-bottom: 1px solid var(--border-color);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 10;
        }

        .logo-group {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-badge {
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            color: #fff;
            font-weight: 800;
            font-size: 16px;
            padding: 4px 10px;
            border-radius: 6px;
            letter-spacing: 0.5px;
            box-shadow: 0 0 15px var(--accent-glow);
        }

        .brand-title {
            font-size: 16px;
            font-weight: 700;
            color: var(--text-main);
        }

        .stats-bar {
            display: flex;
            align-items: center;
            gap: 16px;
            font-size: 13px;
        }

        .stat-item {
            display: flex;
            align-items: center;
            gap: 6px;
            background: rgba(255,255,255,0.05);
            padding: 4px 12px;
            border-radius: 20px;
            border: 1px solid var(--border-color);
        }

        .stat-value {
            font-weight: 700;
            color: var(--accent-primary);
            font-family: var(--font-mono);
        }

        .main-container {
            display: grid;
            grid-template-columns: 320px 1fr 340px;
            flex: 1;
            overflow: hidden;
        }

        .sidebar-left, .content-center, .sidebar-right {
            display: flex;
            flex-direction: column;
            overflow: hidden;
            border-right: 1px solid var(--border-color);
        }

        .sidebar-right {
            border-right: none;
            border-left: 1px solid var(--border-color);
            background-color: var(--bg-surface);
        }

        .panel-header {
            padding: 14px 16px;
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border-color);
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .search-box {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
        }

        .search-input {
            width: 100%;
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            padding: 8px 12px;
            border-radius: 6px;
            font-family: var(--font-mono);
            font-size: 13px;
            outline: none;
            transition: border-color 0.2s;
        }

        .search-input:focus {
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 2px var(--accent-glow);
        }

        .scrollable-list {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
        }

        .list-item {
            padding: 10px 12px;
            border-radius: 6px;
            cursor: pointer;
            margin-bottom: 4px;
            transition: all 0.15s ease;
            display: flex;
            flex-direction: column;
            gap: 4px;
            border: 1px solid transparent;
        }

        .list-item:hover {
            background-color: var(--bg-card);
            border-color: var(--border-color);
        }

        .list-item.active {
            background-color: rgba(59, 130, 246, 0.15);
            border-color: var(--accent-primary);
        }

        .item-title {
            font-size: 13px;
            font-weight: 600;
            font-family: var(--font-mono);
            color: var(--text-main);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .item-badge {
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            text-transform: uppercase;
            font-weight: 700;
        }

        .badge-function { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
        .badge-class { background: rgba(139, 92, 246, 0.2); color: #a78bfa; }
        .badge-method { background: rgba(16, 185, 129, 0.2); color: #34d399; }

        .item-subtitle {
            font-size: 11px;
            color: var(--text-muted);
            font-family: var(--font-mono);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .content-center {
            background-color: var(--bg-primary);
            display: flex;
            flex-direction: column;
        }

        .code-viewer {
            flex: 1;
            overflow: auto;
            padding: 20px;
            font-family: var(--font-mono);
            font-size: 13px;
            line-height: 1.6;
            background-color: #0d1117;
            color: #c9d1d9;
            white-space: pre;
            border-bottom: 1px solid var(--border-color);
        }

        .empty-placeholder {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-muted);
            text-align: center;
            gap: 12px;
            padding: 40px;
        }

        .empty-placeholder svg {
            width: 48px;
            height: 48px;
            stroke: var(--text-muted);
            opacity: 0.5;
        }

        .section-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 12px;
        }

        .section-title {
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .tag-pill {
            display: inline-block;
            background: rgba(255,255,255,0.08);
            border: 1px solid var(--border-color);
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-family: var(--font-mono);
            margin: 2px 4px 2px 0;
            cursor: pointer;
            transition: all 0.15s;
        }

        .tag-pill:hover {
            border-color: var(--accent-primary);
            color: #60a5fa;
        }

        .blast-banner {
            background: rgba(245, 158, 11, 0.1);
            border: 1px solid rgba(245, 158, 11, 0.3);
            border-radius: 6px;
            padding: 10px;
            margin-bottom: 12px;
            font-size: 12px;
            color: #fbbf24;
        }
    </style>
</head>
<body>

    <header>
        <div class="logo-group">
            <div class="brand-badge">M5</div>
            <div class="brand-title">Code Knowledge Graph</div>
        </div>
        <div class="stats-bar" id="statsBar">
            <div class="stat-item">Files: <span class="stat-value" id="statFiles">0</span></div>
            <div class="stat-item">AST Symbols: <span class="stat-value" id="statSymbols">0</span></div>
            <div class="stat-item">Call Edges: <span class="stat-value" id="statEdges">0</span></div>
            <div class="stat-item">DB Size: <span class="stat-value" id="statSize">0 KB</span></div>
        </div>
    </header>

    <div class="main-container">
        <!-- Left Panel: Symbols & Search -->
        <div class="sidebar-left">
            <div class="panel-header">
                <span>AST Symbols</span>
                <span id="symbolCountBadge" style="font-family: var(--font-mono); font-size: 11px;">0</span>
            </div>
            <div class="search-box">
                <input type="text" id="searchInput" class="search-input" placeholder="Search functions, classes (/)..." autocomplete="off">
            </div>
            <div class="scrollable-list" id="symbolsList">
                <div class="empty-placeholder" style="padding: 20px;">
                    <div>Loading symbol graph...</div>
                </div>
            </div>
        </div>

        <!-- Center Panel: Code & Detail Viewer -->
        <div class="content-center">
            <div class="panel-header" id="activeSymbolHeader">
                <span>Select a symbol to view source & AST metadata</span>
            </div>
            <div class="code-viewer" id="codeViewer">
                <div class="empty-placeholder">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                        <polyline points="10 9 9 9 8 9"></polyline>
                    </svg>
                    <div>Pick any function or class on the left to inspect its live source & callers</div>
                </div>
            </div>
        </div>

        <!-- Right Panel: Dependencies & Blast Radius -->
        <div class="sidebar-right">
            <div class="panel-header">
                <span>Graph Intelligence</span>
            </div>
            <div class="scrollable-list" id="graphIntelPanel">
                <div class="empty-placeholder" style="padding: 20px;">
                    <div>Callers, callees, and blast radius will appear here.</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let allSymbols = [];
        let activeSymbol = null;

        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                document.getElementById('statFiles').innerText = data.total_files || 0;
                document.getElementById('statSymbols').innerText = data.total_symbols || 0;
                document.getElementById('statEdges').innerText = data.total_edges || 0;
                document.getElementById('statSize').innerText = (data.db_size_kb || 0) + ' KB';
            } catch (err) {
                console.error(err);
            }
        }

        async function fetchSymbols(query = '') {
            try {
                const res = await fetch('/api/search?q=' + encodeURIComponent(query));
                const data = await res.json();
                allSymbols = data.results || [];
                renderSymbolsList(allSymbols);
                document.getElementById('symbolCountBadge').innerText = allSymbols.length;
            } catch (err) {
                console.error(err);
            }
        }

        function renderSymbolsList(list) {
            const container = document.getElementById('symbolsList');
            if (!list || list.length === 0) {
                container.innerHTML = '<div class="empty-placeholder"><div style="font-size:12px;">No matching AST symbols found</div></div>';
                return;
            }

            container.innerHTML = list.map(item => `
                <div class="list-item ${activeSymbol && activeSymbol.name === item.name ? 'active' : ''}" onclick="selectSymbol('${encodeURIComponent(item.name)}')">
                    <div class="item-title">
                        <span>${escapeHtml(item.name)}</span>
                        <span class="item-badge badge-${item.kind || 'function'}">${item.kind || 'function'}</span>
                    </div>
                    <div class="item-subtitle">${escapeHtml(item.file_path)} : L${item.start_line}</div>
                </div>
            `).join('');
        }

        async function selectSymbol(encodedName) {
            const name = decodeURIComponent(encodedName);
            try {
                const res = await fetch('/api/symbol?name=' + encodeURIComponent(name));
                const data = await res.json();
                activeSymbol = data.symbol;
                renderActiveSymbol(data);
                renderSymbolsList(allSymbols);
            } catch (err) {
                console.error(err);
            }
        }

        function renderActiveSymbol(data) {
            const sym = data.symbol;
            if (!sym) return;

            document.getElementById('activeSymbolHeader').innerHTML = `
                <span>${escapeHtml(sym.file_path)} <span style="color:var(--text-muted); font-family:var(--font-mono);">[Lines ${sym.start_line}-${sym.end_line}]</span></span>
                <span class="item-badge badge-${sym.kind || 'function'}">${sym.kind || 'function'}</span>
            `;

            document.getElementById('codeViewer').innerText = sym.content || '// No source content available';

            // Render Right Panel (Callers, Callees, Blast Radius)
            const callers = data.callers || [];
            const callees = data.callees || [];
            const blast = data.blast_radius || {};

            let html = '';

            if (blast.total_affected_files > 0) {
                html += `
                    <div class="blast-banner">
                        <strong>Blast Radius:</strong> Modifying <code>${escapeHtml(sym.name)}</code> impacts <strong>${blast.total_affected_symbols}</strong> symbols across <strong>${blast.total_affected_files}</strong> files.
                    </div>
                `;
            }

            html += `
                <div class="section-card">
                    <div class="section-title">
                        <span>Callers (${callers.length})</span>
                    </div>
                    ${callers.length > 0 ? callers.map(c => `
                        <div class="tag-pill" onclick="selectSymbol('${encodeURIComponent(c.source_symbol)}')">
                            ${escapeHtml(c.source_symbol)} <span style="opacity:0.6; font-size:10px;">(${escapeHtml(c.source_file.split('/').pop().split('\\\\').pop())})</span>
                        </div>
                    `).join('') : '<div style="font-size:12px; color:var(--text-muted);">No direct callers found in graph</div>'}
                </div>
            `;

            html += `
                <div class="section-card">
                    <div class="section-title">
                        <span>Callees / Calls (${callees.length})</span>
                    </div>
                    ${callees.length > 0 ? callees.map(c => `
                        <div class="tag-pill" onclick="selectSymbol('${encodeURIComponent(c.target_symbol)}')">
                            ${escapeHtml(c.target_symbol)}
                        </div>
                    `).join('') : '<div style="font-size:12px; color:var(--text-muted);">No outgoing function calls</div>'}
                </div>
            `;

            if (blast.affected_files && blast.affected_files.length > 0) {
                html += `
                    <div class="section-card">
                        <div class="section-title">
                            <span>Affected Files (${blast.affected_files.length})</span>
                        </div>
                        ${blast.affected_files.map(f => `
                            <div style="font-size:11px; font-family:var(--font-mono); color:var(--text-muted); margin-bottom:4px; overflow:hidden; text-overflow:ellipsis;">
                                📄 ${escapeHtml(f)}
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            document.getElementById('graphIntelPanel').innerHTML = html;
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }

        // Live search filter
        document.getElementById('searchInput').addEventListener('input', (e) => {
            fetchSymbols(e.target.value.trim());
        });

        // Key shortcut '/'
        document.addEventListener('keydown', (e) => {
            if (e.key === '/' && document.activeElement !== document.getElementById('searchInput')) {
                e.preventDefault();
                document.getElementById('searchInput').focus();
            }
        });

        fetchStats();
        fetchSymbols();
    </script>
</body>
</html>
"""

class M5VisualHTTPHandler(BaseHTTPRequestHandler):
    db = LocalCodeGraphDB()

    def log_message(self, format, *args):
        # Quiet standard output
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if path == "/api/stats":
            stats = self.db.get_stats()
            self._send_json(stats)
            return

        if path == "/api/search":
            q = query.get("q", [""])[0]
            if q:
                results = self.db.search_fts(q, limit=50)
            else:
                with self.db._get_conn() as conn:
                    rows = conn.execute("SELECT name, kind, file_path, start_line, end_line FROM symbols ORDER BY name LIMIT 100").fetchall()
                    results = [dict(r) for r in rows]
            self._send_json({"results": results})
            return

        if path == "/api/symbol":
            name = query.get("name", [""])[0]
            syms = self.db.find_symbol(name, exact=True, limit=1)
            sym = syms[0] if syms else None
            callers = self.db.find_callers(name, limit=30)
            callees = []
            if sym:
                callees = self.db.find_callees(sym["file_path"], sym["name"])
            blast = self.db.get_impact_radius(name, depth=2)
            self._send_json({
                "symbol": sym,
                "callers": callers,
                "callees": callees,
                "blast_radius": blast
            })
            return

        if path == "/api/flow":
            from_sym = query.get("from", [""])[0]
            to_sym = query.get("to", [""])[0]
            paths = self.db.get_call_path(from_sym, to_sym, max_depth=4)
            self._send_json({"paths": paths})
            return

        self.send_response(404)
        self.end_headers()

    def _send_json(self, data: Any):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

def start_visual_server(port: int = 5555, open_browser: bool = True):
    server = HTTPServer(("127.0.0.1", port), M5VisualHTTPHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"\n=======================================================")
    print(f"  [M5] Visual Graph Browser running at {url}")
    print(f"  Press Ctrl+C to stop the server.")
    print(f"=======================================================\n")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] M5 Visual Server stopped.")
        server.server_close()

if __name__ == "__main__":
    start_visual_server()
