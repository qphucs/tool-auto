// Thư viện các loại cảnh. Mỗi cảnh: (root, data, M, duration) dựng DOM và đặt hoạt ảnh theo thời gian của cảnh.
// Chữ luôn được gán bằng textContent (qua M.el) nên nội dung từ AI không bao giờ thành HTML.
window.Scenes = {};

(() => {
  const S = window.Scenes;

  // ----- thành phần dùng chung -----

  function tag(M, root, text, t, cls = "") {
    if (!text) return t;
    const e = M.el("div", `tag ${cls}`, text);
    root.append(e);
    M.tween(e, { opacity: [0, 1], y: [3, 0] }, t, 0.5);
    return t + 0.2;
  }

  // Tiêu đề 2 dòng, dòng 2 nhấn màu, hiện từng từ. Trả về thời điểm chữ cuối bắt đầu hiện.
  function title(M, root, d, t, size = "") {
    const h = M.el("h1", `headline ${size}`);
    const l1 = d.line1 ? M.el("span", "line", d.line1) : null;
    const l2 = d.line2 ? M.el("span", `line ${d.accent || "accent"}`, d.line2) : null;
    if (l1) h.append(l1);
    if (l2) h.append(l2);
    root.append(h);
    for (const w of l1 ? M.splitWords(l1) : []) {
      M.tween(w, { opacity: [0, 1], y: [5, 0], blur: [1, 0] }, t, 0.55);
      t += 0.07;
    }
    t += 0.08;
    for (const w of l2 ? M.splitWords(l2) : []) {
      M.tween(w, { opacity: [0, 1], y: [5, 0], scale: [0.85, 1], blur: [1, 0] }, t, 0.6, "back");
      t += 0.09;
    }
    return t;
  }

  function popIn(M, el, t, dur = 0.5) {
    M.tween(el, { opacity: [0, 1], y: [4, 0], scale: [0.92, 1] }, t, dur, "back");
  }

  function row(M, cls, icon, text) {
    const r = M.el("div", cls);
    if (icon) r.append(M.el("span", "ico", icon));
    r.append(M.el("span", "txt", text));
    return r;
  }

  function list(M, root, items, t, step, build) {
    const box = M.el("div", "list");
    root.append(box);
    (items || []).forEach((it, i) => {
      const r = build(it, i);
      box.append(r);
      popIn(M, r, t + i * step);
    });
    return t + (items || []).length * step;
  }

  // ----- các loại cảnh -----

  S.hook = (root, d, M) => {
    let t = tag(M, root, d.tag, 0.15);
    t = title(M, root, d, t + 0.05) + 0.25;
    const chips = M.el("div", "chips");
    root.append(chips);
    (d.chips || []).forEach((c, i) => {
      const chip = row(M, "chip", c.icon, c.text);
      chips.append(chip);
      popIn(M, chip, t + i * 0.12);
    });
  };

  S.question = (root, d, M) => {
    if (d.icon) {
      const ico = M.el("div", "big-ico", d.icon);
      root.append(ico);
      M.tween(ico, { opacity: [0, 1], scale: [0.5, 1] }, 0.1, 0.6, "back");
      M.onFrame((t) => {
        ico.style.translate = `0 ${M.vw(1.2 * Math.sin(t * 2.2))}px`;
      });
    }
    const t = title(M, root, d, 0.35);
    if (d.sub) {
      const sub = M.el("p", "sub", d.sub);
      root.append(sub);
      M.tween(sub, { opacity: [0, 1], y: [3, 0] }, t + 0.3, 0.5);
    }
  };

  S.stat = (root, d, M) => {
    let t = tag(M, root, d.tag, 0.15);
    const box = M.el("div", "stat");
    const num = M.el("div", `stat-num ${d.accent || "accent"}`, "0");
    box.append(num);
    if (d.label) box.append(M.el("div", "stat-label", d.label));
    root.append(box);
    M.tween(box, { opacity: [0, 1], scale: [0.8, 1] }, t, 0.5, "back");
    const value = Number(d.value) || 0;
    const decimals = Number.isInteger(d.decimals) ? d.decimals : Number.isInteger(value) ? 0 : 1;
    const fmt = new Intl.NumberFormat("vi-VN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    const start = t + 0.1;
    M.onFrame((now) => {
      const p = Math.min(1, Math.max(0, (now - start) / 1.3));
      num.textContent = `${d.prefix || ""}${fmt.format(value * M.EASE.out(p))}${d.suffix || ""}`;
    });
    if (d.note) {
      const note = M.el("p", "sub", d.note);
      root.append(note);
      M.tween(note, { opacity: [0, 1], y: [3, 0] }, start + 1.0, 0.5);
    }
  };

  S.screenshot = (root, d, M, duration) => {
    const t = title(M, root, d, 0.15, "md") + 0.15;
    const frame = M.el("div", "browser");
    const bar = M.el("div", "browser-bar");
    bar.append(M.el("i", "dot r"), M.el("i", "dot y"), M.el("i", "dot g"), M.el("span", "url", d.url || ""));
    const view = M.el("div", "browser-view");
    frame.append(bar, view);
    if (d.image) {
      const img = document.createElement("img");
      img.src = d.image;
      view.append(img);
      const f = d.focus || {};
      const scale = Number(f.scale) || 1;
      if (scale > 1.01) {
        // Phóng vào điểm (x, y) tính theo tỉ lệ 0-1 của ảnh
        img.style.transformOrigin = `${(Number(f.x) || 0.5) * 100}% ${(Number(f.y) || 0.3) * 100}%`;
        M.tween(img, { scale: [1, scale] }, t + 0.9, Math.min(1.8, Math.max(0.8, duration - t - 1.5)), "inOut");
      }
    } else {
      view.append(M.el("div", "browser-empty", d.placeholder || "Ảnh minh họa"));
    }
    root.append(frame);
    M.tween(frame, { opacity: [0, 1], y: [6, 0], scale: [0.95, 1] }, t, 0.6, "back");
    if (d.caption) {
      const pill = row(M, "pill", d.caption_icon || "", d.caption);
      root.append(pill);
      popIn(M, pill, t + 0.6);
    }
  };

  S.steps = (root, d, M) => {
    let t = tag(M, root, d.tag, 0.15);
    t = title(M, root, d, t + 0.05, "md") + 0.25;
    list(M, root, d.items, t, 0.35, (it, i) => {
      const r = M.el("div", "step");
      r.append(M.el("span", "num", String(i + 1).padStart(2, "0")));
      if (it.icon) r.append(M.el("span", "ico", it.icon));
      r.append(M.el("span", "txt", it.text || ""));
      return r;
    });
  };

  S.diagram = (root, d, M) => {
    const t = title(M, root, d, 0.15, "md") + 0.25;
    const flow = M.el("div", "flow");
    root.append(flow);
    (d.nodes || []).forEach((n, i) => {
      if (i > 0) {
        const link = M.el("div", "link");
        flow.append(link);
        M.tween(link, { opacity: [0, 1], scale: [0.2, 1] }, t + i * 0.45 - 0.2, 0.35);
      }
      const node = row(M, `node${i === (d.nodes || []).length - 1 ? " last" : ""}`, n.icon, n.text);
      flow.append(node);
      popIn(M, node, t + i * 0.45);
    });
  };

  const LEVELS = {
    tip: { icon: "💡", cls: "accent-4" },
    warning: { icon: "⚠️", cls: "accent-2" },
    danger: { icon: "⛔", cls: "accent-3" },
  };

  S.warning = (root, d, M) => {
    const lv = LEVELS[d.level] || LEVELS.warning;
    const head = M.el("div", `warn-head ${lv.cls}`);
    head.append(M.el("span", "ico", d.icon || lv.icon), M.el("span", "", d.title || ""));
    root.append(head);
    M.tween(head, { opacity: [0, 1], x: [-4, 0] }, 0.15, 0.5);
    const card = M.el("div", `card warn ${lv.cls}`);
    if (d.text) card.append(M.el("p", "card-text", d.text));
    root.append(card);
    popIn(M, card, 0.5, 0.6);
    list(M, card, d.bullets, 0.9, 0.3, (b) => row(M, "bullet", "•", b));
  };

  S.summary = (root, d, M) => {
    const t = title(M, root, d, 0.15, "md") + 0.25;
    list(M, root, d.items, t, 0.3, (it) => row(M, "check", "✓", typeof it === "string" ? it : it.text || ""));
  };

  S.cta = (root, d, M) => {
    const bubble = M.el("div", "bubble");
    bubble.append(M.el("p", "", d.question || ""));
    root.append(bubble);
    M.tween(bubble, { opacity: [0, 1], scale: [0.85, 1], y: [4, 0] }, 0.15, 0.6, "back");
    let t = 0.8;
    if (d.hint) {
      const hint = row(M, "hint", "💬", d.hint);
      root.append(hint);
      M.tween(hint, { opacity: [0, 1], y: [2, 0] }, t, 0.5);
      t += 0.3;
    }
    if (d.button) {
      const btn = row(M, "cta-btn", d.button_icon || "🔔", d.button);
      root.append(btn);
      popIn(M, btn, t, 0.6);
      const begin = t + 0.6;
      M.onFrame((now) => {
        if (now > begin) btn.style.scale = String(1 + 0.04 * Math.sin((now - begin) * 5));
      });
    }
  };
})();
