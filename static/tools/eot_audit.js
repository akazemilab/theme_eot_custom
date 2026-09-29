/* eot_audit.js - design/quality audit of rendered pages (milestone 8).
 *
 * One source for two runners:
 *   - VPS: tools/vps/eotaudit.py (headless Chromium) injects this file and
 *     calls eotAudit.page(window) on each URL.
 *   - Browser pane: await import('/theme_eot_custom/static/tools/eot_audit.js')
 *     then eotAudit.start([...paths], 375) and poll eotAudit.report().
 *
 * Checks per page: horizontal overflow (scrollWidth vs viewport, elements
 * spilling out), WCAG contrast of every visible text node against its real
 * background, leftover English UI text, broken images, heading font/weight,
 * <title>. Returns only problems, so output stays small.
 *
 * Not loaded by any asset bundle: served only as a static file for audits.
 */
(function () {
    const IGNORE_TEXT = /@|\.ir\b|https?:|www\.|EOT|rehearsal\.invalid/;
    // Content (not UI) that is deliberately English on this site.
    const CONTENT_EN = /eLearning|Microlearning|CAT|TAT|factual/;
    const SKIP = 'script,style,noscript,template,option,[aria-hidden=true],.d-none,.visually-hidden,.modal,.offcanvas,#o_shared_blocks';
    const OVER_SKIP = '.eot-h-field,.offcanvas,[aria-hidden=true],.d-none,.eot-legal-tabs,.modal';

    const rgb = (s) => (s.match(/[\d.]+/g) || [0, 0, 0]).map(Number);
    const lum = ([r, g, b]) => {
        const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

    function page(w, opts) {
        opts = opts || {};
        const d = w.document, vw = w.innerWidth;
        const bgOf = (el) => {
            for (let e = el; e; e = e.parentElement) {
                const cs = w.getComputedStyle(e), c = rgb(cs.backgroundColor);
                if ((c.length > 3 ? c[3] : 1) > 0.5) return c.slice(0, 3);
                if (cs.backgroundImage && cs.backgroundImage.includes('url(')) return null; // photo: can't judge
            }
            return [255, 255, 255];
        };
        const out = { url: decodeURIComponent(w.location.pathname + w.location.search), vw, docW: d.documentElement.scrollWidth, title: d.title };
        const low = [], en = [], seen = new Set();
        const walker = d.createTreeWalker(d.body, 4);
        while (walker.nextNode()) {
            const t = walker.currentNode.textContent.trim();
            const el = walker.currentNode.parentElement;
            if (!t || !el || seen.has(el) || el.closest(SKIP)) continue;
            seen.add(el);
            const cs = w.getComputedStyle(el);
            if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue;
            const r = el.getBoundingClientRect();
            if (!r.width || !r.height) continue;
            const bg = bgOf(el);
            if (bg) {
                const cr = ratio(rgb(cs.color).slice(0, 3), bg);
                const fs = parseFloat(cs.fontSize), fw = parseInt(cs.fontWeight, 10);
                const need = (fs >= 24 || (fs >= 18.66 && fw >= 700)) ? 3 : 4.5;
                if (cr < need) low.push([t.slice(0, 30), +cr.toFixed(2), cs.color, 'rgb(' + bg + ')']);
            }
            if (/[A-Za-z]{3,}/.test(t) && !IGNORE_TEXT.test(t) && !(opts.allowContentEn !== false && CONTENT_EN.test(t))) en.push(t.slice(0, 40));
        }
        const over = [];
        d.querySelectorAll('#wrapwrap *').forEach((e) => {
            const r = e.getBoundingClientRect();
            if (!r.width || !r.height || (r.right <= vw + 2 && r.left >= -2)) return;
            const pos = w.getComputedStyle(e).position;
            if (pos === 'fixed' || pos === 'absolute' || e.closest(OVER_SKIP)) return;
            over.push((e.tagName + '.' + String(e.className || '').split(' ')[0]).slice(0, 34) + ':' + Math.round(r.left) + '..' + Math.round(r.right));
        });
        const h = d.querySelector('#wrap h1, main h1');
        const problems = {};
        if (out.docW > vw + 1) problems.pageWidth = out.docW;
        if (over.length) problems.overflow = [...new Set(over)].slice(0, 6);
        if (low.length) { problems.contrast = low.slice(0, 6); problems.contrastN = low.length; }
        const enU = [...new Set(en)];
        if (enU.length && opts.english !== false) problems.english = enU.slice(0, 10);
        const bad = [...d.images].filter((i) => i.complete && i.naturalWidth === 0 && i.getBoundingClientRect().width > 0).map((i) => i.src.slice(-50));
        if (bad.length) problems.brokenImages = bad;
        if (h) {
            const hs = w.getComputedStyle(h);
            if (!/Estedad/.test(hs.fontFamily)) problems.h1Font = hs.fontFamily.split(',')[0];
        }
        if (/[A-Za-z]{3,}/.test(d.title.replace(/\|.*$/, ''))) problems.englishTitle = d.title;
        out.problems = problems;
        out.ok = Object.keys(problems).length === 0;
        return out;
    }

    // Browser-pane runner: same-origin iframe per page at a chosen width.
    async function load(src, width, injectCss) {
        let f = document.getElementById('__eot_audit_frame');
        if (f) f.remove();
        f = document.createElement('iframe');
        f.id = '__eot_audit_frame';
        f.style.cssText = 'position:absolute;left:-6000px;top:0;border:0;width:' + width + 'px;height:900px';
        document.body.appendChild(f);
        await new Promise((res) => { f.onload = res; f.src = src; });
        if (injectCss) {
            for (const l of document.querySelectorAll('link[rel=stylesheet]')) {
                const n = f.contentDocument.createElement('link');
                n.rel = 'stylesheet'; n.href = l.href; f.contentDocument.head.appendChild(n);
            }
        }
        await new Promise((res) => setTimeout(res, 1500));
        try { return page(f.contentWindow); } catch (e) { return { url: src, error: String(e) }; }
    }

    const state = { results: [], done: true };
    function start(paths, width, injectCss) {
        state.results = []; state.done = false;
        (async () => {
            for (const p of paths) state.results.push(Object.assign({ width }, await load(p, width || 1280, injectCss)));
            state.done = true;
        })();
        return 'started ' + paths.length;
    }
    function report() {
        const bad = state.results.filter((r) => !r.ok).map((r) => ({ url: r.url, width: r.width, problems: r.problems, error: r.error }));
        return { done: state.done, checked: state.results.length, problems: bad };
    }

    const api = { page, load, start, report, ratio };
    if (typeof window !== 'undefined') window.eotAudit = api;
})();
