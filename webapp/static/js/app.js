/* EVE Helper — 共享前端工具
   统一：入场揭示、数字滚动、格式化、请求封装、标签页/分段控件、骨架屏、轻提示。 */
(function () {
    'use strict';

    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ---------- DOM ---------- */
    function qs(sel, root) { return (root || document).querySelector(sel); }
    function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function delegate(root, selector, type, handler) {
        root.addEventListener(type, function (e) {
            var el = e.target.closest(selector);
            if (el && root.contains(el)) handler(e, el);
        });
    }

    /* ---------- 请求封装 ---------- */
    function api(url, opts) {
        return fetch(url, opts).then(function (res) {
            if (!res.ok) throw new Error('HTTP ' + res.status + ' · ' + url);
            var ct = res.headers.get('content-type') || '';
            return ct.indexOf('json') !== -1 ? res.json() : res.text();
        });
    }

    function debounce(fn, wait) {
        var t;
        return function () {
            var args = arguments, self = this;
            clearTimeout(t);
            t = setTimeout(function () { fn.apply(self, args); }, wait == null ? 200 : wait);
        };
    }

    /* ---------- 格式化 ---------- */
    function fmt(n, dec, opts) {
        opts = opts || {};
        var v = Number(n) || 0;
        var s = dec > 0 ? v.toFixed(dec) : Math.round(v).toString();
        if (opts.group !== false) {
            var parts = s.split('.');
            parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
            s = parts.join('.');
        }
        return (opts.prefix || '') + s + (opts.suffix || '');
    }
    function int(n) { return fmt(n, 0); }
    function compact(n) {
        n = Number(n) || 0;
        var a = Math.abs(n);
        if (a >= 1e9) return (n / 1e9).toFixed(2) + 'B';
        if (a >= 1e6) return (n / 1e6).toFixed(2) + 'M';
        if (a >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return String(Math.round(n));
    }

    /* ---------- 入场揭示 ---------- */
    var io = null;
    function reveal(root) {
        var els = qsa('[data-reveal]:not(.in)', root);
        if (!els.length) return;
        if (!('IntersectionObserver' in window) || reduce) {
            els.forEach(function (el) { el.classList.add('in'); });
            return;
        }
        if (!io) {
            io = new IntersectionObserver(function (entries) {
                entries.forEach(function (e) {
                    if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
                });
            }, { rootMargin: '0px 0px -8% 0px', threshold: 0.01 });
        }
        els.forEach(function (el) { io.observe(el); });
    }

    /* ---------- 数字滚动 ---------- */
    function countUp(el, target, opts) {
        if (!el) return;
        opts = opts || {};
        var dur = opts.duration || 700;
        var dec = opts.decimals || 0;
        var to = Number(target) || 0;
        if (reduce || Number(el.textContent.replace(/[^\d.-]/g, '')) === to) {
            el.textContent = fmt(to, dec, opts); return;
        }
        var from = 0, start = performance.now();
        function frame(now) {
            var p = Math.min(1, (now - start) / dur);
            var eased = 1 - Math.pow(1 - p, 3);
            el.textContent = fmt(from + (to - from) * eased, dec, opts);
            if (p < 1) requestAnimationFrame(frame);
            else el.textContent = fmt(to, dec, opts);
        }
        requestAnimationFrame(frame);
    }

    /* ---------- 轻提示 ---------- */
    function ensureToastCss() {
        if (document.getElementById('eh-toast-css')) return;
        var s = document.createElement('style');
        s.id = 'eh-toast-css';
        s.textContent =
            '#eh-toast{position:fixed;right:22px;bottom:22px;z-index:200;display:flex;flex-direction:column;gap:10px;align-items:flex-end}' +
            '#eh-toast .t{display:flex;align-items:center;gap:10px;padding:11px 15px;border:1px solid var(--line-2);border-left:3px solid var(--accent);' +
            'border-radius:10px;background:#fff;color:var(--text);font-size:13px;box-shadow:0 10px 30px -12px rgba(16,24,40,.35);' +
            'animation:fadeUp .3s var(--ease) both;max-width:360px}' +
            '#eh-toast .t .d{width:7px;height:7px;border-radius:50%;background:var(--accent);flex:none}' +
            '#eh-toast .t.ok{border-left-color:var(--pos)}#eh-toast .t.ok .d{background:var(--pos)}' +
            '#eh-toast .t.err{border-left-color:var(--neg)}#eh-toast .t.err .d{background:var(--neg)}' +
            '#eh-toast .t.out{opacity:0;transform:translateY(6px);transition:opacity .3s ease,transform .3s ease}';
        document.head.appendChild(s);
    }
    function toast(msg, type) {
        ensureToastCss();
        var host = document.getElementById('eh-toast');
        if (!host) { host = document.createElement('div'); host.id = 'eh-toast'; document.body.appendChild(host); }
        var el = document.createElement('div');
        el.className = 't' + (type ? ' ' + type : '');
        el.innerHTML = '<span class="d"></span><span>' + esc(msg) + '</span>';
        host.appendChild(el);
        setTimeout(function () {
            el.classList.add('out');
            setTimeout(function () { el.remove(); }, 320);
        }, 2600);
    }

    /* ---------- 骨架屏 ---------- */
    function skeletonRows(rows, cols) {
        var out = '';
        for (var i = 0; i < rows; i++) {
            out += '<div class="sk-row">';
            for (var c = 0; c < cols; c++) out += '<span class="sk"' + (c === 0 ? ' style="max-width:180px"' : '') + '></span>';
            out += '</div>';
        }
        return out;
    }

    /* ---------- 标签页（滑动下划线 + 键盘） ---------- */
    function tabs(root, onChange) {
        var btns = qsa('button[data-tab]', root);
        if (!btns.length) return null;
        var ink = document.createElement('span');
        ink.className = 'ink';
        root.appendChild(ink);
        root.setAttribute('role', 'tablist');

        function move(btn) {
            ink.style.left = btn.offsetLeft + 'px';
            ink.style.width = btn.offsetWidth + 'px';
        }
        function activate(btn, fire) {
            btns.forEach(function (b) {
                var on = b === btn;
                b.classList.toggle('active', on);
                b.setAttribute('aria-selected', on ? 'true' : 'false');
                var pane = document.getElementById(b.dataset.tab);
                if (pane) pane.classList.toggle('active', on);
            });
            move(btn);
            if (fire && onChange) onChange(btn.dataset.tab, btn);
        }
        btns.forEach(function (b, i) {
            b.setAttribute('role', 'tab');
            b.setAttribute('tabindex', b.classList.contains('active') ? '0' : '-1');
            var pane = document.getElementById(b.dataset.tab);
            if (pane) { pane.setAttribute('role', 'tabpanel'); b.setAttribute('aria-controls', b.dataset.tab); }
            b.addEventListener('click', function () { activate(b, true); });
            b.addEventListener('keydown', function (e) {
                var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
                if (!d) return;
                e.preventDefault();
                var next = btns[(i + d + btns.length) % btns.length];
                btns.forEach(function (x) { x.setAttribute('tabindex', '-1'); });
                next.setAttribute('tabindex', '0');
                next.focus();
                activate(next, true);
            });
        });
        var initial = btns.filter(function (b) { return b.classList.contains('active'); })[0] || btns[0];
        requestAnimationFrame(function () { activate(initial, false); });
        window.addEventListener('resize', function () {
            var a = btns.filter(function (b) { return b.classList.contains('active'); })[0];
            if (a) move(a);
        });
        return { activate: activate };
    }

    /* ---------- 分段控件（滑动指示） ---------- */
    function segment(root, onChange) {
        var btns = qsa('button[data-value]', root);
        if (!btns.length) return null;
        var thumb = document.createElement('span');
        thumb.className = 'thumb';
        root.insertBefore(thumb, root.firstChild);
        root.setAttribute('role', 'tablist');

        function move(btn) {
            thumb.style.left = btn.offsetLeft + 'px';
            thumb.style.width = btn.offsetWidth + 'px';
        }
        function activate(btn, fire) {
            btns.forEach(function (b) {
                var on = b === btn;
                b.classList.toggle('active', on);
                b.setAttribute('aria-selected', on ? 'true' : 'false');
            });
            move(btn);
            if (fire && onChange) onChange(btn.dataset.value);
        }
        btns.forEach(function (b) {
            b.setAttribute('role', 'tab');
            b.addEventListener('click', function () { activate(b, true); });
        });
        var initial = btns.filter(function (b) { return b.classList.contains('active'); })[0] || btns[0];
        requestAnimationFrame(function () { activate(initial, false); });
        window.addEventListener('resize', function () {
            var a = btns.filter(function (b) { return b.classList.contains('active'); })[0];
            if (a) move(a);
        });
        return { activate: activate };
    }

    /* ---------- 搜索快捷键：/ 聚焦 ---------- */
    document.addEventListener('keydown', function (e) {
        if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
        var t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
        var el = qs('[data-shortcut-search]');
        if (el) { e.preventDefault(); el.focus(); el.select && el.select(); }
    });

    window.EH = {
        qs: qs, qsa: qsa, esc: esc, delegate: delegate,
        api: api, debounce: debounce,
        fmt: fmt, int: int, compact: compact,
        reveal: reveal, countUp: countUp,
        toast: toast, skeletonRows: skeletonRows,
        tabs: tabs, segment: segment,
        reduce: reduce
    };

    document.addEventListener('DOMContentLoaded', function () { reveal(); });
})();