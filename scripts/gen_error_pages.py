#!/usr/bin/env python3
"""Generate the static, self-contained error pages nginx serves when Odoo is
unreachable or nginx itself rejects the request (static/errors/*.html), plus
the preview index.  Run from the repo root:  python3 scripts/gen_error_pages.py
Pages must stay dependency-free (inline CSS/JS, no external requests)."""
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'errors'
FA = '۰۱۲۳۴۵۶۷۸۹'

CSS = """:root{--ink:#062E33;--body:#3B5256;--teal:#005C65;--mist:#F6FAFB;--gold:#B08A2E}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{display:flex;align-items:center;justify-content:center;padding:24px 16px;
 font-family:Vazirmatn,"Vazir",Tahoma,"Segoe UI",sans-serif;color:var(--body);text-align:center;
 background-color:var(--mist);
 background-image:radial-gradient(ellipse at 50% 35%,rgba(246,250,251,.97) 0,rgba(246,250,251,.75) 45%,rgba(246,250,251,.2) 100%),
 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='88' height='88'%3E%3Cg fill='none' stroke='%23B08A2E' stroke-opacity='.16' stroke-width='1'%3E%3Crect x='24' y='24' width='40' height='40'/%3E%3Crect x='24' y='24' width='40' height='40' transform='rotate(45 44 44)'/%3E%3Cpath d='M0 44H16M72 44H88M44 0V16M44 72V88'/%3E%3Ccircle cx='44' cy='44' r='6'/%3E%3C/g%3E%3C/svg%3E");
 background-size:auto,88px 88px}
main{max-width:34rem;display:flex;flex-direction:column;align-items:center;gap:1.25rem}
.brand{font-size:.95rem;color:var(--teal);font-weight:700}
.code{font-size:3.2rem;line-height:1;color:var(--gold);font-weight:700;letter-spacing:.02em}
h1{margin:0;color:var(--ink);font-size:clamp(1.6rem,5vw,2.2rem);line-height:1.5}
p{margin:0;line-height:2;font-size:1.05rem}
.orn{display:flex;align-items:center;gap:.75rem;width:min(16rem,70%)}
.orn::before,.orn::after{content:"";flex:1;height:1px}
.orn::before{background:linear-gradient(90deg,var(--gold),transparent)}
.orn::after{background:linear-gradient(270deg,var(--gold),transparent)}
.orn svg{flex:0 0 20px;width:20px;height:20px;display:block}
.spin{width:38px;height:38px;border-radius:50%;border:3px solid rgba(0,92,101,.15);border-top-color:var(--teal);animation:s 1s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation:none}}
a.btn{display:inline-block;padding:.7rem 1.4rem;border-radius:999px;background:var(--teal);color:#fff;text-decoration:none;font-weight:600}
a.btn:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
.small{font-size:.9rem;color:#4A5F62}"""

STAR = ('<svg viewBox="0 0 24 24" focusable="false"><g fill="#C9A24A" stroke="#8C6A1E" stroke-width=".6">'
        '<rect x="6" y="6" width="12" height="12"/><rect x="6" y="6" width="12" height="12" transform="rotate(45 12 12)"/></g>'
        '<circle cx="12" cy="12" r="2.2" fill="#FFF6DA"/></svg>')

RELOAD = ('<script>(function(){var n=%d,fa="%s",el=document.getElementById("n");'
          'function f(x){return String(x).replace(/\\d/g,function(d){return fa[d];});}'
          'setInterval(function(){n--;if(n<=0){location.reload();return;}el.textContent=f(n);},1000);})();</script>')

# code: (tab title, heading, text, auto-reload seconds or 0, show "home" button)
PAGES = {
    '502': ('در حال به‌روزرسانی', 'سایت چند لحظه در حال به‌روزرسانی است',
            'در حال انجام تغییرات هستیم و سایت معمولاً ظرف یک تا دو دقیقه دوباره در دسترس قرار می‌گیرد. این صفحه خودکار دوباره بارگذاری می‌شود.', 20, False),
    '503': ('سایت موقتاً در دسترس نیست', 'سایت موقتاً در دسترس نیست',
            'سرویس در حال نگهداری یا بسیار پرمشغله است. چند دقیقهٔ دیگر دوباره سر بزنید؛ این صفحه خودکار دوباره بارگذاری می‌شود.', 30, False),
    '504': ('پاسخ دیر رسید', 'پاسخ سایت بیش از حد طول کشید',
            'درخواست شما به‌موقع پاسخ داده نشد. معمولاً با یک بار تلاش دوباره درست می‌شود؛ اگر ادامه داشت، کمی بعد دوباره امتحان کنید.', 15, False),
    '429': ('درخواست‌های زیاد', 'درخواست‌های شما بیش از حد مجاز است',
            'در مدت کوتاه درخواست‌های زیادی فرستاده شده است. یکی دو دقیقه صبر کنید و دوباره تلاش کنید.', 60, False),
    '413': ('حجم فایل زیاد است', 'حجم فایل یا اطلاعات ارسالی زیاد است',
            'اطلاعاتی که فرستادید از حد مجاز بزرگ‌تر است. فایل را کوچک‌تر کنید و دوباره بفرستید.', 0, True),
}


def fa(n):
    return str(n).translate(str.maketrans('0123456789', FA))


def page(code):
    title, h1, text, secs, home = PAGES[code]
    extra = ''
    if secs:
        extra = ('  <div class="spin" role="status" aria-label="در حال بررسی"></div>\n'
                 '  <a class="btn" href="javascript:location.reload()">تلاش دوباره</a>\n'
                 '  <p class="small">تلاش خودکار تا <span id="n">%s</span> ثانیه دیگر</p>\n' % fa(secs))
    if home:
        extra += '  <a class="btn" href="/">بازگشت به صفحهٔ اصلی</a>\n'
    script = (RELOAD % (secs, FA)) if secs else ''
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title} | هیجان اندیشه</title>
<!-- GENERATED by scripts/gen_error_pages.py. Served by nginx (error_page {code});
     self-contained: no external requests. -->
<style>
{CSS}
</style>
</head>
<body>
<main>
  <span class="brand">مؤسسه تعاملی هیجان اندیشه</span>
  <span class="code" aria-hidden="true">{fa(code)}</span>
  <span class="orn" aria-hidden="true">{STAR}</span>
  <h1>{h1}</h1>
  <p>{text}</p>
{extra}</main>
{script}
</body>
</html>
"""


INDEX_ROWS = [
    ('۴۰۰', 'درخواست نامعتبر', 'سایت (اودو)', '/error-preview/400'),
    ('۴۰۳', 'دسترسی ممنوع', 'سایت (اودو)', '/error-preview/403'),
    ('۴۰۴', 'صفحه پیدا نشد', 'سایت (اودو)', '/error-preview/404'),
    ('۴۰۵ و مشابه', 'سایر خطاهای ۴xx (مثلاً روش نامجاز)', 'سایت (اودو)', '/error-preview/405'),
    ('۵۰۰', 'خطای داخلی سرور', 'سایت (اودو)', '/error-preview/500'),
    ('۴۱۳', 'حجم زیاد ارسال', 'nginx', '/theme_eot_custom/static/errors/413.html'),
    ('۴۲۹', 'درخواست زیاد', 'nginx', '/theme_eot_custom/static/errors/429.html'),
    ('۵۰۲', 'اودو در حال راه‌اندازی', 'nginx', '/theme_eot_custom/static/errors/502.html'),
    ('۵۰۳', 'سرویس موقتاً در دسترس نیست', 'nginx', '/theme_eot_custom/static/errors/503.html'),
    ('۵۰۴', 'پاسخ دیر رسید', 'nginx', '/theme_eot_custom/static/errors/504.html'),
]


def index():
    rows = '\n'.join(f'<tr><td>{c}</td><td><a href="{u}">{d}</a></td><td>{w}</td></tr>' for c, d, w, u in INDEX_ROWS)
    return f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>پیش‌نمایش صفحه‌های خطا | هیجان اندیشه</title>
<style>{CSS}
body{{display:block}}main{{margin:0 auto;max-width:42rem;align-items:stretch;text-align:right}}
table{{border-collapse:collapse;width:100%;background:#fff}}td{{padding:.7rem .9rem;border:1px solid #d8e6e2}}a{{color:var(--teal)}}</style></head>
<body><main><h1>صفحه‌های خطا</h1>
<p>برای دیدن هر صفحه روی عنوانش بزنید. صفحه‌های «اودو» از خود سایت و با قالب آن نمایش داده می‌شوند؛ صفحه‌های «nginx» وقتی اودو در دسترس نباشد یا درخواست به آن نرسد.</p>
<table>{rows}</table></main></body></html>
"""


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    for c in PAGES:
        (OUT / f'{c}.html').write_text(page(c), encoding='utf-8')
    (OUT / 'index.html').write_text(index(), encoding='utf-8')
    print('wrote', ', '.join(sorted(PAGES)), '+ index')
