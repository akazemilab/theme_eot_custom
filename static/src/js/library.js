/** @odoo-module ignore */
// Library pages (views/library.xml): client-side filtering of the articles
// and glossary lists, the in-article contents highlight and the reading
// progress bar. Plain script, no dependencies; does nothing on pages
// without the data-eot-* hooks.
(function () {
    "use strict";

    function toFa(n) {
        return String(n).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
    }

    function norm(s) {
        return (s || "")
            .replace(/‌/g, " ")
            .replace(/[يى]/g, "ی")
            .replace(/ك/g, "ک")
            .replace(/\s+/g, " ")
            .toLowerCase()
            .trim();
    }

    function setupFilter(root) {
        var items = Array.prototype.slice.call(root.querySelectorAll("[data-eot-item]"));
        var groups = Array.prototype.slice.call(root.querySelectorAll("[data-eot-group]"));
        var search = root.querySelector("[data-eot-search]");
        var counter = root.querySelector("[data-eot-count]");
        var empty = root.querySelector("[data-eot-empty]");
        var hideWhenFiltered = root.querySelectorAll("[data-eot-hide-when-filtered]");
        var state = {};
        var texts = items.map(function (it) { return norm(it.textContent); });

        function apply() {
            var q = norm(search ? search.value : "");
            var active = q || Object.keys(state).some(function (k) { return state[k]; });
            var shown = 0;
            items.forEach(function (it, i) {
                var ok = true;
                Object.keys(state).forEach(function (dim) {
                    if (state[dim] && it.dataset[dim] !== state[dim]) { ok = false; }
                });
                if (ok && q) { ok = texts[i].indexOf(q) !== -1; }
                it.hidden = !ok;
                if (ok) { shown++; }
            });
            groups.forEach(function (g) {
                g.hidden = !g.querySelector("[data-eot-item]:not([hidden])");
            });
            if (counter) { counter.textContent = toFa(shown); }
            if (empty) { empty.hidden = shown !== 0; }
            Array.prototype.forEach.call(hideWhenFiltered, function (el) { el.hidden = !!active; });
        }

        Array.prototype.forEach.call(root.querySelectorAll("[data-eot-dim]"), function (btn) {
            btn.addEventListener("click", function () {
                var dim = btn.dataset.eotDim;
                state[dim] = btn.dataset.eotVal || "";
                Array.prototype.forEach.call(root.querySelectorAll('[data-eot-dim="' + dim + '"]'), function (b) {
                    b.setAttribute("aria-pressed", String(b === btn));
                });
                apply();
            });
        });
        if (search) { search.addEventListener("input", apply); }
    }

    function setupToc() {
        var toc = document.querySelector(".eot-page-toc");
        if (!toc || !("IntersectionObserver" in window)) { return; }
        var links = {};
        Array.prototype.forEach.call(toc.querySelectorAll("a[href^='#']"), function (a) {
            links[decodeURIComponent(a.getAttribute("href").slice(1))] = a;
        });
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (e) {
                if (e.isIntersecting && links[e.target.id]) {
                    Object.keys(links).forEach(function (k) { links[k].classList.remove("active"); });
                    links[e.target.id].classList.add("active");
                }
            });
        }, { rootMargin: "0px 0px -70% 0px" });
        Object.keys(links).forEach(function (id) {
            var h = document.getElementById(id);
            if (h) { observer.observe(h); }
        });
    }

    function setupProgress() {
        var bar = document.querySelector("[data-eot-read-progress]");
        var text = document.querySelector(".eot-article-text");
        if (!bar || !text) { return; }
        var ticking = false;
        function update() {
            ticking = false;
            var r = text.getBoundingClientRect();
            var total = r.height - window.innerHeight;
            var done = total > 0 ? Math.min(1, Math.max(0, -r.top / total)) : 1;
            bar.style.width = (done * 100).toFixed(1) + "%";
        }
        window.addEventListener("scroll", function () {
            if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
        }, { passive: true });
        update();
    }

    function init() {
        Array.prototype.forEach.call(document.querySelectorAll("[data-eot-filter]"), setupFilter);
        setupToc();
        setupProgress();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
