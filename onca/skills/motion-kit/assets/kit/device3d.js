/* Onca motion kit: the 3D device shell (a phone or laptop built from primitives, drawn with Three.js from
 * lib/). motion.js owns the pose math; this file only turns a pose into pixels: draw(state) is a pure function of
 * the state it is given, called from OncaMotion.seek on every hf-seek. No clock, no random, no requestAnimationFrame.
 * It builds every <canvas data-device="phone|laptop"> on the page and registers window.__hf.buildReady["device3d"].
 * Screen: data-shot (an image) or data-frames (a folder of 0001.jpg ... from `kit.py frames`, with data-fps).
 * A failed setup draws nothing and sets window.__hf.deviceError; kit.py check reports it. */
import * as THREE from "./lib/three.module.min.js";
import { RoundedBoxGeometry } from "./lib/RoundedBoxGeometry.js";
import { RoomEnvironment } from "./lib/RoomEnvironment.js";

const rad = THREE.MathUtils.degToRad;
const deviceSpec = () => window.OncaMotion.deviceSpec;
const ELEVATION = rad(6);  // the camera looks down a little, so the contact shadow shows
const LID_OPEN = rad(106);
const instances = new Map();  // canvas -> built device
const pending = new Map();  // canvas -> the last state drawn before its build finished

function fail(text) {
  window.__hf = window.__hf || {};
  window.__hf.deviceError = window.__hf.deviceError ? window.__hf.deviceError + "; " + text : text;
  console.error("[device3d] " + text);
}

// ------------------------------------------------------------ shapes

function roundedShape(w, h, r) {
  const x = -w / 2, y = -h / 2;
  r = Math.min(r, w / 2, h / 2);
  const s = new THREE.Shape();
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.absarc(x + w - r, y + r, r, -Math.PI / 2, 0, false);
  s.lineTo(x + w, y + h - r);
  s.absarc(x + w - r, y + h - r, r, 0, Math.PI / 2, false);
  s.lineTo(x + r, y + h);
  s.absarc(x + r, y + h - r, r, Math.PI / 2, Math.PI, false);
  s.lineTo(x, y + r);
  s.absarc(x + r, y + r, r, Math.PI, Math.PI * 1.5, false);
  return s;
}

/* A flat rounded rectangle facing +z, its uv spanning 0 to 1 (a screen, a glare, a bezel). */
function flat(w, h, r) {
  const g = new THREE.ShapeGeometry(roundedShape(w, h, r), 20);
  const p = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / w + 0.5, p.getY(i) / h + 0.5);
  return g;
}

/* A slab with large face corners and small rounded edges, centred, its front face toward +z. */
function slab(w, h, d, r, bevel) {
  const g = new THREE.ExtrudeGeometry(roundedShape(w - 2 * bevel, h - 2 * bevel, r - bevel), {
    depth: d - 2 * bevel, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 4, curveSegments: 24,
  });
  g.translate(0, 0, -(d - 2 * bevel) / 2);
  return g;
}

// ------------------------------------------------------------ generated textures (deterministic)

function canvasTexture(w, h, paint) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  paint(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/* The glass glare: a soft diagonal band; its offset follows the yaw so it sweeps the screen as the device turns. */
function glareTexture() {
  const t = canvasTexture(256, 256, (g, w, h) => {
    g.clearRect(0, 0, w, h);
    const band = g.createLinearGradient(0, 0, w, h * 0.35);
    band.addColorStop(0.3, "rgba(255,255,255,0)");
    band.addColorStop(0.5, "rgba(255,255,255,0.9)");
    band.addColorStop(0.7, "rgba(255,255,255,0)");
    g.fillStyle = band;
    g.fillRect(0, 0, w, h);
  });
  t.repeat.set(0.5, 1);
  return t;
}

function shadowTexture() {
  return canvasTexture(256, 256, (g, w, h) => {
    const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    r.addColorStop(0, "rgba(0,0,0,0.85)");
    r.addColorStop(0.55, "rgba(0,0,0,0.3)");
    r.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = r;
    g.fillRect(0, 0, w, h);
  });
}

function keyboardTexture() {
  return canvasTexture(1280, 420, (g, w, h) => {
    g.fillStyle = "#17181c";
    g.fillRect(0, 0, w, h);
    const rows = [14, 14, 14, 13, 12], gap = 9, top = 14;
    const kh = (h * 0.74 - top - gap * 4) / 5;
    rows.forEach((n, row) => {
      const kw = (w - gap * (n + 1)) / n;
      for (let i = 0; i < n; i++) {
        g.fillStyle = "#2a2c33";
        g.beginPath();
        g.roundRect(gap + i * (kw + gap), top + row * (kh + gap), kw, kh, 8);
        g.fill();
      }
    });
    g.fillStyle = "#202228";
    g.beginPath();
    g.roundRect(w * 0.32, h * 0.76, w * 0.36, h * 0.22, 14);
    g.fill();
  });
}

// ------------------------------------------------------------ the two devices

const mat = (color, metal, rough) => new THREE.MeshStandardMaterial({ color, metalness: metal, roughness: rough });
const BLACK_GLASS = () => new THREE.MeshStandardMaterial({ color: 0x050506, metalness: 0.1, roughness: 0.12 });

/* The face stack (black glass, the screen, a glare) on a group whose +z is the front. */
function addFace(group, spec, z, screenTex, glareTex) {
  const glass = new THREE.Mesh(flat(spec.glassW, spec.glassH, spec.glassR), BLACK_GLASS());
  glass.position.z = z + 0.0005;
  const screen = new THREE.Mesh(flat(spec.w, spec.h, spec.r), new THREE.MeshBasicMaterial({ map: screenTex, toneMapped: false }));
  screen.position.z = z + 0.0011;
  const glare = new THREE.Mesh(flat(spec.w, spec.h, spec.r), new THREE.MeshBasicMaterial({
    map: glareTex, transparent: true, opacity: 0.16, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
  glare.position.z = z + 0.0017;
  group.add(glass, screen, glare);
}

function buildPhone(screenTex, glareTex) {
  const { w: W, h: H } = deviceSpec().sizes.phone, D = 0.08, R = W * 0.12;
  const rig = new THREE.Group();
  const body = new THREE.Mesh(slab(W, H, D, R, 0.014), mat(0x9a9ca4, 1, 0.3));
  rig.add(body);
  const inset = 0.022;
  const screen = { w: W - 2 * inset, h: H - 2 * inset, r: R - inset, glassW: W - 0.012, glassH: H - 0.012, glassR: R - 0.006 };
  addFace(rig, screen, D / 2, screenTex, glareTex);
  const island = new THREE.Mesh(flat(W * 0.14, W * 0.04, W * 0.02), new THREE.MeshBasicMaterial({ color: 0x000000 }));
  island.position.set(0, H / 2 - inset - 0.05, D / 2 + 0.0024);
  rig.add(island);
  const bump = new THREE.Mesh(new RoundedBoxGeometry(0.3, 0.3, 0.016, 4, 0.06), mat(0x30313a, 1, 0.3));
  bump.position.set(-W / 2 + 0.2, H / 2 - 0.2, -D / 2 - 0.008);
  rig.add(bump);
  [[-0.07, 0.07], [-0.07, -0.07], [0.07, 0]].forEach(([dx, dy]) => {
    const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.052, 0.052, 0.012, 32), mat(0x0a0a0c, 0.4, 0.15));
    lens.rotation.x = Math.PI / 2;
    lens.position.set(bump.position.x + dx, bump.position.y + dy, -D / 2 - 0.018);
    rig.add(lens);
  });
  const button = (x, y, h) => {
    const b = new THREE.Mesh(new RoundedBoxGeometry(0.012, h, 0.028, 3, 0.005), mat(0x8a8c94, 1, 0.35));
    b.position.set(x, y, 0);
    rig.add(b);
  };
  button(W / 2 + 0.002, 0.25, 0.16);
  button(-W / 2 - 0.002, 0.3, 0.07);
  button(-W / 2 - 0.002, 0.18, 0.12);
  return { rig, shadow: { y: -H / 2 - 0.03, w: 1.1, d: 0.5 }, screenAspect: screen.w / screen.h };
}

function buildLaptop(screenTex, glareTex) {
  const W = 2.2, BD = 1.5, BH = 0.07, LH = 1.45, LT = 0.034;
  const model = new THREE.Group();
  const base = new THREE.Mesh(new RoundedBoxGeometry(W, BH, BD, 4, 0.03), mat(0xb7b9c1, 1, 0.34));
  base.position.y = BH / 2;
  model.add(base);
  const deck = new THREE.Mesh(new THREE.PlaneGeometry(1.95, 1.95 * 420 / 1280), new THREE.MeshStandardMaterial({ map: keyboardTexture(), roughness: 0.6, metalness: 0.1 }));
  deck.rotation.x = -Math.PI / 2;
  deck.position.set(0, BH + 0.0006, -0.2);
  model.add(deck);
  const pivot = new THREE.Group();  // the hinge, at the back edge of the base
  pivot.position.set(0, BH + 0.003, -BD / 2 + 0.03);
  model.add(pivot);
  const hinge = new THREE.Mesh(new THREE.CylinderGeometry(0.026, 0.026, 1.8, 24), mat(0x2b2c32, 0.9, 0.4));
  hinge.rotation.z = Math.PI / 2;
  hinge.position.set(0, BH + 0.01, -BD / 2 + 0.03);
  model.add(hinge);
  const frame = new THREE.Group();  // a +z-front plate lying flat: its z becomes -y, its y runs toward the lid's top
  frame.rotation.x = Math.PI / 2;
  frame.position.set(0, LT / 2, LH / 2);
  pivot.add(frame);
  frame.add(new THREE.Mesh(slab(W, LH, LT, 0.055, 0.008), mat(0xb7b9c1, 1, 0.34)));
  const screen = { w: 2.1, h: 2.1 / 1.6, r: 0.03, glassW: W - 0.016, glassH: LH - 0.016, glassR: 0.05 };
  addFace(frame, screen, LT / 2, screenTex, glareTex);
  const cam = new THREE.Mesh(new THREE.CircleGeometry(0.012, 16), new THREE.MeshBasicMaterial({ color: 0x15161a }));
  cam.position.set(0, LH / 2 - 0.034, LT / 2 + 0.0016);
  frame.add(cam);
  model.position.y = -0.73;  // the open laptop's middle sits on the origin
  const rig = new THREE.Group();
  rig.add(model);
  return { rig, pivot, shadow: { y: -0.75, w: 2.8, d: 1.7 }, screenAspect: screen.w / screen.h };
}

// ------------------------------------------------------------ screen source

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("not found: " + url));
    img.src = url;
  });
}

const frameName = (i) => String(i + 1).padStart(4, "0") + ".jpg";

/* [{img}] for a still or a folder of numbered frames (all loaded before the first draw). */
async function loadScreen(canvas) {
  const shot = canvas.getAttribute("data-shot");
  const folder = canvas.getAttribute("data-frames");
  if (shot) return { images: [await loadImage(new URL(shot, document.baseURI).href).catch(() => { throw new Error("shot '" + shot + "' not found"); })], fps: 1, kind: "image" };
  if (!folder) throw new Error("the canvas needs data-shot or data-frames");
  const base = new URL(folder.replace(/\/?$/, "/"), document.baseURI).href;
  const images = [];
  for (let i = 0; ; i++) {
    try {
      images.push(await loadImage(base + frameName(i)));
    } catch (e) {
      if (i === 0) throw new Error("frames '" + folder + "' has no " + frameName(0));
      break;
    }
  }
  const fps = Number(canvas.getAttribute("data-fps")) || 12;
  return { images, fps, kind: "frames " + images.length };
}

/* Crop the picture to the screen's shape (cover: no bars), keeping its top and its middle. */
function fitTexture(tex, imageAspect, screenAspect) {
  tex.repeat.set(1, 1);
  tex.offset.set(0, 0);
  if (imageAspect > screenAspect) {
    tex.repeat.x = screenAspect / imageAspect;
    tex.offset.x = (1 - tex.repeat.x) / 2;
  } else {
    tex.repeat.y = imageAspect / screenAspect;
    tex.offset.y = 1 - tex.repeat.y;
  }
}

// ------------------------------------------------------------ build and draw

async function build(canvas, opts) {
  const started = Date.now();
  const device = (opts && opts.device) || canvas.getAttribute("data-device") || "phone";
  const root = canvas.closest("[data-width][data-height]");
  const W = Number(canvas.getAttribute("width")) || (root && Number(root.getAttribute("data-width"))) || 1080;
  const H = Number(canvas.getAttribute("height")) || (root && Number(root.getAttribute("data-height"))) || 1920;
  canvas.width = W;
  canvas.height = H;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
  } catch (e) {
    fail("no WebGL for " + canvas.id + ": " + (e && e.message));
    return;
  }
  let screen;
  try {
    screen = await loadScreen(canvas);
  } catch (e) {
    fail(canvas.id + ": " + e.message);
    renderer.dispose();
    return;
  }
  renderer.setPixelRatio(1);
  renderer.setSize(W, H, false);
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.9;
  pm.dispose();
  const key = new THREE.DirectionalLight(0xffe8cc, 2.2);
  key.position.set(-2, 3, 4);
  const rim = new THREE.DirectionalLight(0x9db8ff, 1.8);  // the cool rim separates the edge from a dark background
  rim.position.set(3, 1, -3);
  scene.add(key, rim);

  const tex = new THREE.Texture(screen.images[0]);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  tex.generateMipmaps = true;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.needsUpdate = true;
  const glare = glareTexture();
  const model = device === "laptop" ? buildLaptop(tex, glare) : buildPhone(tex, glare);
  fitTexture(tex, screen.images[0].naturalWidth / screen.images[0].naturalHeight, model.screenAspect);
  scene.add(model.rig);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(model.shadow.w, model.shadow.d),
    new THREE.MeshBasicMaterial({ map: shadowTexture(), transparent: true, opacity: 0.6, depthWrite: false, toneMapped: false }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = model.shadow.y;
  scene.add(floor);
  const camera = new THREE.PerspectiveCamera(deviceSpec().fov, W / H, 0.1, 40);
  const safeAttr = (canvas.getAttribute("data-safe") || "").split(",").map(Number);  // "0.83,0.52": the box the device keeps to
  const safe = safeAttr.length === 2 && safeAttr.every((n) => n > 0 && n <= 1) ? safeAttr : null;
  const liftAttr = canvas.getAttribute("data-lift");  // px the picture moves up; default: the 9:16 safe box's own centre
  const lift = liftAttr != null && liftAttr !== "" ? Number(liftAttr) / H : W / H < 1 ? deviceSpec().lift.portrait : deviceSpec().lift.landscape;
  const fit = window.OncaMotion.deviceFit(W / H, device, safe);
  const inst = { canvas, renderer, scene, camera, model, tex, glare, screen, device, fit, W, H, lift, shown: 0, floor };
  instances.set(canvas, inst);
  console.info(`[device3d] ${canvas.id} ${device} ${screen.kind} ${W}x${H} built in ${Date.now() - started} ms`);
  if (pending.has(canvas)) draw(pending.get(canvas), canvas);
}

function draw(state, canvas) {
  const inst = instances.get(canvas);
  if (!inst) {
    pending.set(canvas, state);  // the build draws it once the canvas is ready
    return;
  }
  const { renderer, scene, camera, model, tex, glare, screen, device, fit, W, H, lift } = inst;
  const size = deviceSpec().sizes[device];
  const pose = model.rig;
  pose.rotation.set(-rad(state.pitch), rad(state.yaw), rad(state.roll), "YXZ");
  pose.position.set(state.x * size.h, state.y * size.h, 0);
  if (model.pivot) model.pivot.rotation.x = -LID_OPEN * state.open;
  const dist = deviceSpec().dist / Math.max(0.05, state.zoom * fit);
  camera.position.set(0, dist * Math.sin(ELEVATION), dist * Math.cos(ELEVATION));
  camera.lookAt(0, 0, 0);
  camera.setViewOffset(W, H, 0, Math.round(lift * H), W, H);
  glare.offset.x = 0.25 + state.yaw * 0.006;
  const index = Math.min(screen.images.length - 1, Math.max(0, Math.floor(state.t * screen.fps + 1e-6)));
  if (index !== inst.shown) {
    tex.image = screen.images[index];
    tex.needsUpdate = true;
    inst.shown = index;
  }
  renderer.render(scene, camera);
}

function dispose() {
  instances.forEach((inst) => {
    inst.renderer.dispose();
    inst.tex.dispose();
    inst.glare.dispose();
  });
  instances.clear();
  pending.clear();
}

window.OncaDevice3D = { build, draw, dispose };
window.__hf = window.__hf || {};
window.__hf.buildReady = window.__hf.buildReady || {};
window.__hf.buildReady["device3d"] = Promise.all(Array.from(document.querySelectorAll("canvas[data-device]")).map((c) => build(c)));
