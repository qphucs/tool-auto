// Bộ chạy hoạt ảnh theo đồng hồ của tool.
// Mọi chuyển động được tính từ thời điểm t (giây) truyền vào seek(t), không dùng CSS animation,
// nên dựng bao nhiêu lần cũng ra giống hệt nhau và không phụ thuộc máy nhanh hay chậm.
(() => {
  const EASE = {
    linear: (p) => p,
    out: (p) => 1 - Math.pow(1 - p, 3),
    in: (p) => p * p * p,
    inOut: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
    back: (p) => {
      const c1 = 1.70158;
      const c3 = c1 + 1;
      return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2);
    },
  };

  const tracks = [];
  const drawers = [];
  const lerp = (a, b, p) => a + (b - a) * p;
  const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

  // Đơn vị theo chiều rộng khung hình: vw(10) = 10% chiều rộng, giống CSS vw.
  const vw = (n) => (n * window.innerWidth) / 100;

  // props: { opacity: [từ, tới], x: [...], y: [...], scale: [...], rotate: [...], blur: [...] } (x, y, blur tính bằng vw)
  function tween(el, props, start, dur, ease = "out") {
    tracks.push({ el, props, start, dur, ease: EASE[ease] || EASE.out });
  }

  function onFrame(fn) {
    drawers.push(fn);
  }

  function apply(el, s) {
    const tf = [];
    if ("x" in s || "y" in s) tf.push(`translate(${vw(s.x || 0)}px, ${vw(s.y || 0)}px)`);
    if ("scale" in s) tf.push(`scale(${s.scale})`);
    if ("rotate" in s) tf.push(`rotate(${s.rotate}deg)`);
    if (tf.length) el.style.transform = tf.join(" ");
    if ("opacity" in s) el.style.opacity = s.opacity;
    if ("blur" in s) el.style.filter = s.blur > 0.005 ? `blur(${vw(s.blur)}px)` : "none";
  }

  function seek(t) {
    const states = new Map();
    for (const tr of tracks) {
      let s = states.get(tr.el);
      if (!s) {
        s = {};
        states.set(tr.el, s);
      }
      const p = tr.dur > 0 ? clamp01((t - tr.start) / tr.dur) : t >= tr.start ? 1 : 0;
      for (const [k, [a, b]] of Object.entries(tr.props)) {
        if (t < tr.start) {
          if (!(k in s)) s[k] = a; // chưa tới lúc chạy: giữ giá trị đầu
        } else {
          s[k] = lerp(a, b, tr.ease(p));
        }
      }
    }
    for (const [el, s] of states) apply(el, s);
    for (const fn of drawers) fn(t);
  }

  // Số ngẫu nhiên có hạt giống: cùng hạt giống thì cùng dãy số
  function rng(seed) {
    let x = seed % 2147483647 || 1;
    return () => {
      x = (x * 16807) % 2147483647;
      return (x - 1) / 2147483646;
    };
  }

  // Nền hạt sáng chuyển động chậm và hai quầng sáng mờ
  // offset: dời thời gian của nền để mỗi cảnh có vị trí hạt khác nhau mà không phụ thuộc độ dài cảnh trước
  function particles(canvas, { count = 70, seed = 7, offset = 0 } = {}) {
    const ctx = canvas.getContext("2d");
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const W = canvas.width;
    const H = canvas.height;
    const rand = rng(seed);
    const dots = Array.from({ length: count }, () => ({
      x: rand() * W,
      y: rand() * H,
      r: vw(0.12 + rand() * 0.35),
      vy: -vw(0.15 + rand() * 0.6),
      vx: vw((rand() - 0.5) * 0.3),
      tw: 0.6 + rand() * 1.8,
      ph: rand() * Math.PI * 2,
    }));
    const glow = getComputedStyle(document.documentElement).getPropertyValue("--glow").trim() || "79,140,255";

    onFrame((local) => {
      const t = local + offset;
      ctx.clearRect(0, 0, W, H);
      for (const [cx, cy, rad, speed, alpha] of [
        [0.15, 0.2, 0.75, 0.05, 0.16],
        [0.9, 0.75, 0.65, 0.07, 0.12],
      ]) {
        const x = W * (cx + 0.05 * Math.sin(t * speed * 6));
        const y = H * (cy + 0.03 * Math.cos(t * speed * 5));
        const g = ctx.createRadialGradient(x, y, 0, x, y, W * rad);
        g.addColorStop(0, `rgba(${glow},${alpha})`);
        g.addColorStop(1, `rgba(${glow},0)`);
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, H);
      }
      for (const d of dots) {
        const x = (((d.x + d.vx * t) % W) + W) % W;
        const y = (((d.y + d.vy * t) % H) + H) % H;
        const a = 0.25 + 0.35 * (0.5 + 0.5 * Math.sin(t * d.tw + d.ph));
        ctx.beginPath();
        ctx.arc(x, y, d.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
        ctx.fill();
      }
    });
  }

  // Tách chữ thành từng từ (span) để làm hiệu ứng từng từ
  function splitWords(el) {
    const words = el.textContent.split(/\s+/).filter(Boolean);
    el.textContent = "";
    return words.map((w, i) => {
      const s = document.createElement("span");
      s.className = "w";
      s.textContent = w;
      el.appendChild(s);
      if (i < words.length - 1) el.appendChild(document.createTextNode(" "));
      return s;
    });
  }

  // Phụ đề tô sáng: words = [{ w, start, end }], hiện từng cụm tối đa maxWords từ.
  // Chia cụm đều nhau để không có cụm cuối chỉ còn một chữ.
  function captions(container, words, maxWords = 5) {
    const groups = [];
    const count = Math.ceil(words.length / maxWords);
    const size = Math.ceil(words.length / Math.max(count, 1));
    for (let i = 0; i < words.length; i += size) groups.push(words.slice(i, i + size));
    const rows = groups.map((g) => {
      const row = document.createElement("div");
      row.className = "cap";
      const spans = g.map((item, i) => {
        const s = document.createElement("span");
        s.className = "cw";
        s.textContent = item.w;
        row.appendChild(s);
        if (i < g.length - 1) row.appendChild(document.createTextNode(" "));
        return s;
      });
      container.appendChild(row);
      return { row, spans, items: g };
    });
    onFrame((t) => {
      let current = -1;
      rows.forEach((r, i) => {
        if (t >= r.items[0].start) current = i;
      });
      const last = rows[rows.length - 1];
      if (last && t > last.items[last.items.length - 1].end + 0.4) current = -1;
      rows.forEach((r, i) => {
        r.row.classList.toggle("show", i === current);
        r.spans.forEach((s, j) => s.classList.toggle("on", i === current && t >= r.items[j].start && t < r.items[j].end));
      });
    });
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text; // luôn dùng textContent: chữ từ AI không bao giờ thành HTML
    return e;
  }

  function finalize() {
    tracks.sort((a, b) => a.start - b.start);
  }

  window.Motion = { tween, onFrame, seek, particles, splitWords, captions, el, rng, vw, finalize, EASE };
  window.__seek = (t) => seek(t);
})();
