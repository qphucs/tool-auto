// Dựng một cảnh từ window.__SCENE rồi báo sẵn sàng cho bộ dựng (window.__ready).
// __SCENE = { type, duration, data, captions: [{ w, start, end }], brand, seed, bgOffset }
(() => {
  const scene = window.__SCENE;
  const M = window.Motion;
  const brand = scene.brand || {};
  const root = document.documentElement.style;
  for (const [k, v] of Object.entries(brand.vars || {})) root.setProperty(`--${k}`, v);

  M.particles(document.getElementById("bg"), { seed: scene.seed || 7, offset: scene.bgOffset || 0 });

  if (brand.show_logo && (brand.logo || brand.channel)) {
    const box = document.getElementById("brand");
    if (brand.logo) {
      const img = document.createElement("img");
      img.src = brand.logo;
      box.append(img);
    }
    if (brand.channel) box.append(M.el("span", "", brand.channel));
  }

  const build = window.Scenes[scene.type];
  if (!build) throw new Error(`Không có loại cảnh: ${scene.type}`);
  const stage = document.getElementById("stage");
  build(stage, scene.data || {}, M, scene.duration);
  // Nội dung mờ dần ở cuối cảnh, nền vẫn giữ để chuyển cảnh nhẹ nhàng
  M.tween(stage, { opacity: [1, 0], blur: [0, 0.6] }, scene.duration - 0.35, 0.35, "in");

  if (scene.captions && scene.captions.length) {
    M.captions(document.getElementById("captions"), scene.captions);
  }
  M.finalize();

  const images = [...document.images].map((img) => (img.complete ? null : new Promise((r) => (img.onload = img.onerror = r))));
  Promise.all([document.fonts.ready, ...images.filter(Boolean)]).then(() => {
    M.seek(0);
    window.__ready = true;
  });
})();
