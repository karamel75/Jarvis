// JARVIS — le globe holographique (Three.js + bloom).
// Couches : nuage de particules vivant (bruit + voix), maillage de latitudes, cœur à effet fresnel,
// icosaèdre filaire, arcs HUD, anneau de graduations, anneau de fréquences, satellites, poussière.
// États : idle (veille), listen (écoute), think (réflexion), speak (parole).
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const BANDS = 24;
const TAU = Math.PI * 2;

const STATES = {
  idle:   { a: '#1e9bff', b: '#8fe6ff', agit: 0.15, spin: 0.06, glow: 0.75, bloom: 0.75 },
  listen: { a: '#2bc4ff', b: '#e6fbff', agit: 0.45, spin: 0.10, glow: 1.05, bloom: 0.95 },
  think:  { a: '#ff9a2a', b: '#ffe0a0', agit: 0.85, spin: 0.55, glow: 1.00, bloom: 0.90 },
  speak:  { a: '#22b6ff', b: '#c9f5ff', agit: 0.35, spin: 0.12, glow: 1.15, bloom: 1.05 },
};

// Bruit simplex 3D (Ashima Arts / Stefan Gustavson, licence MIT)
const NOISE = /* glsl */`
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

const PARTICLE_VS = /* glsl */`
uniform float uTime, uLevel, uMic, uAgit, uForm, uPixel, uSwirl, uRadius;
uniform float uBands[${BANDS}];
attribute vec3 aScatter;
attribute vec4 aRand;   // taille, phase, retard d'implosion, bande de fréquence
varying float vGlow; varying float vMix; varying float vAlpha;
${NOISE}
void main(){
  vec3 dir = normalize(position);
  float t = uTime;
  float n  = snoise(dir * 1.7 + vec3(0.0, t * 0.17, t * 0.11));
  float n2 = snoise(dir * 4.2 - vec3(t * 0.32));
  float band = uBands[int(aRand.w * float(${BANDS - 1}) + 0.5)];
  float disp = n * (0.045 + uAgit * 0.11) + n2 * 0.022
             + band * 0.30 * (0.55 + 0.45 * n) + uLevel * 0.10 + uMic * 0.09 * (0.5 + n2);
  // tourbillon de réflexion : les latitudes glissent les unes sur les autres
  float sw = uSwirl * (0.6 + 0.4 * sin(dir.y * 6.0 + t)) * dir.y;
  float cs = cos(sw), sn = sin(sw);
  dir = vec3(dir.x * cs - dir.z * sn, dir.y, dir.x * sn + dir.z * cs);
  vec3 sphere = dir * uRadius * (1.0 + disp);

  // implosion / dispersion, avec un retard propre à chaque particule
  float f = clamp(uForm * 1.7 - aRand.z * 0.7, 0.0, 1.0);
  f = f * f * (3.0 - 2.0 * f);
  vec3 p = mix(aScatter, sphere, f);

  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float facing = normalize(normalMatrix * dir).z;   // > 0 : face caméra
  float size = (0.55 + aRand.x * 1.5) * (1.0 + band * 1.6 + uLevel * 0.8);
  gl_PointSize = size * uPixel * (24.0 / -mv.z);
  vGlow = clamp(0.35 + disp * 2.4 + band * 1.2, 0.0, 1.7);
  vMix = clamp(0.45 + n * 0.55 + band, 0.0, 1.0);
  float twinkle = 0.55 + 0.45 * sin(t * (1.5 + aRand.x * 2.0) + aRand.y * 6.2831);
  vAlpha = twinkle * (0.28 + 0.72 * smoothstep(-0.7, 0.5, facing)) * mix(0.15, 1.0, f);
}`;

const PARTICLE_FS = /* glsl */`
uniform vec3 uColorA, uColorB; uniform float uFade;
varying float vGlow; varying float vMix; varying float vAlpha;
void main(){
  float d = length(gl_PointCoord - 0.5);
  float a = pow(smoothstep(0.5, 0.0, d), 1.7);
  vec3 col = mix(uColorA, uColorB, vMix) * (0.55 + vGlow);
  gl_FragColor = vec4(col, a * vAlpha * uFade);
}`;

const CORE_VS = /* glsl */`
varying vec3 vN; varying vec3 vV;
void main(){
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}`;
const CORE_FS = /* glsl */`
uniform vec3 uColor; uniform float uPower, uFade;
varying vec3 vN; varying vec3 vV;
void main(){
  float fres = pow(1.0 - max(dot(vN, vV), 0.0), 2.4);
  float inner = pow(max(dot(vN, vV), 0.0), 6.0) * 0.55;
  gl_FragColor = vec4(uColor * (fres * 1.4 + inner) * uPower, (fres + inner) * uFade);
}`;

const DUST_VS = /* glsl */`
uniform float uTime, uPixel; attribute float aSeed; varying float vA;
void main(){
  vec3 p = position;
  p.y += sin(uTime * 0.07 + aSeed * 40.0) * 0.35;
  p.x += cos(uTime * 0.05 + aSeed * 23.0) * 0.25;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = (0.6 + aSeed * 1.4) * uPixel * (14.0 / -mv.z);
  vA = 0.25 + 0.5 * sin(uTime * 0.9 + aSeed * 90.0) * 0.5 + 0.25;
}`;
const DUST_FS = /* glsl */`
uniform vec3 uColor; uniform float uFade; varying float vA;
void main(){
  float d = length(gl_PointCoord - 0.5);
  gl_FragColor = vec4(uColor, smoothstep(0.5, 0.0, d) * vA * 0.55 * uFade);
}`;

const lerp = (a, b, k) => a + (b - a) * k;
const ease = (k) => 1 - Math.pow(1 - k, 3);

export class Globe {
  constructor(canvas) {
    this.canvas = canvas;
    this.state = 'idle';
    this.level = 0; this.levelTarget = 0;
    this.mic = 0; this.micTarget = 0;
    this.bands = new Float32Array(BANDS); this.bandsTarget = new Float32Array(BANDS);
    this.form = 0; this.formTarget = 0; this.formSpeed = 1.2;
    this.mouse = new THREE.Vector2(); this.mouseSmooth = new THREE.Vector2();
    this.colorA = new THREE.Color(STATES.idle.a); this.colorB = new THREE.Color(STATES.idle.b);
    this.params = { ...STATES.idle };
    this._tA = new THREE.Color(); this._tB = new THREE.Color(); this._mid = new THREE.Color();
    this.fadeMats = [];
    this.clock = new THREE.Clock();
    this.shock = [];

    const pixel = Math.min(window.devicePixelRatio || 1, 1.5);
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(pixel);
    this.renderer.setClearColor(0x01040a, 1);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    this.camera.position.set(0, 0, 7.2);
    this.root = new THREE.Group(); this.scene.add(this.root);
    this.spin = new THREE.Group(); this.root.add(this.spin);
    this.pixel = pixel;

    this._particles();
    this._grid();
    this._core();
    this._wire();
    this._arcs();
    this._ticks();
    this._freq();
    this._satellites();
    this._dust();

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.8, 0.38, 0.08);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());

    addEventListener('resize', () => this.resize());
    addEventListener('pointermove', (e) => {
      this.mouse.set(e.clientX / innerWidth * 2 - 1, e.clientY / innerHeight * 2 - 1);
    });
    this.resize();
    this.renderer.setAnimationLoop(() => this.frame());
  }

  // ── construction ────────────────────────────────────────────────────

  _particles() {
    const N = 11000, R = 1.55;
    const pos = new Float32Array(N * 3), scatter = new Float32Array(N * 3), rand = new Float32Array(N * 4);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < N; i++) {
      // sphère de Fibonacci légèrement bruitée : régulière sans être mécanique
      const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), th = golden * i;
      const j = 0.012;
      pos.set([(Math.cos(th) * r + (Math.random() - .5) * j) * R, (y + (Math.random() - .5) * j) * R,
               (Math.sin(th) * r + (Math.random() - .5) * j) * R], i * 3);
      const s = 5 + Math.random() * 9, u = Math.random() * TAU, v = Math.acos(2 * Math.random() - 1);
      scatter.set([s * Math.sin(v) * Math.cos(u), s * Math.cos(v) * 0.7, s * Math.sin(v) * Math.sin(u)], i * 3);
      const lon = (Math.atan2(Math.sin(th) * r, Math.cos(th) * r) / TAU + 0.5);
      rand.set([Math.random() ** 2, Math.random(), Math.random(), (lon * 2) % 1], i * 4);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aScatter', new THREE.BufferAttribute(scatter, 3));
    g.setAttribute('aRand', new THREE.BufferAttribute(rand, 4));
    this.pu = {
      uTime: { value: 0 }, uLevel: { value: 0 }, uMic: { value: 0 }, uAgit: { value: .15 }, uForm: { value: 0 },
      uPixel: { value: this.pixel }, uSwirl: { value: 0 }, uFade: { value: 1 }, uRadius: { value: R },
      uBands: { value: this.bands }, uColorA: { value: this.colorA }, uColorB: { value: this.colorB },
    };
    const m = new THREE.ShaderMaterial({ uniforms: this.pu, vertexShader: PARTICLE_VS, fragmentShader: PARTICLE_FS,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    this.points = new THREE.Points(g, m);
    this.points.frustumCulled = false;
    this.spin.add(this.points);
  }

  _line(points, color, opacity, closed = true) {
    const g = new THREE.BufferGeometry().setFromPoints(points);
    const m = new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false,
      blending: THREE.AdditiveBlending });
    this.fadeMats.push([m, opacity]);
    return new (closed ? THREE.LineLoop : THREE.Line)(g, m);
  }

  _circle(r, n = 160, y = 0) {
    const pts = [];
    for (let i = 0; i < n; i++) { const a = i / n * TAU; pts.push(new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r)); }
    return pts;
  }

  _grid() {
    // latitudes et méridiens très fins : la lecture « globe » sans être une carte
    const R = 1.6, grid = new THREE.Group();
    for (let k = -3; k <= 3; k++) {
      const y = k / 4 * R, r = Math.sqrt(R * R - y * y);
      grid.add(this._line(this._circle(r, 140, y), 0x3cc8ff, k === 0 ? 0.22 : 0.08));
    }
    for (let k = 0; k < 12; k++) {
      const pts = [], a = k / 12 * Math.PI;
      for (let i = 0; i <= 80; i++) {
        const v = i / 80 * Math.PI;
        pts.push(new THREE.Vector3(Math.sin(v) * Math.cos(a) * R, Math.cos(v) * R, Math.sin(v) * Math.sin(a) * R));
      }
      grid.add(this._line(pts, 0x3cc8ff, 0.06, false));
    }
    this.spin.add(grid);
    // bande de balayage qui parcourt le globe de haut en bas
    this.scan = this._line(this._circle(1, 160), 0xbff1ff, 0.55);
    this.fadeMats.pop();  // opacité pilotée à part, dans frame()
    this.spin.add(this.scan);
  }

  _core() {
    this.coreU = { uColor: { value: this.colorB }, uPower: { value: 1 }, uFade: { value: 1 } };
    const m = new THREE.ShaderMaterial({ uniforms: this.coreU, vertexShader: CORE_VS, fragmentShader: CORE_FS,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    this.core = new THREE.Mesh(new THREE.SphereGeometry(0.5, 48, 48), m);
    this.root.add(this.core);
    // halo : cœur ponctuel très lumineux, le bloom fait le reste
    const s = document.createElement('canvas'); s.width = s.height = 128;
    const c = s.getContext('2d'), grd = c.createRadialGradient(64, 64, 0, 64, 64, 64);
    grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.2, 'rgba(170,235,255,.55)');
    grd.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = grd; c.fillRect(0, 0, 128, 128);
    this.glowTex = new THREE.CanvasTexture(s);
    const sm = new THREE.SpriteMaterial({ map: this.glowTex, color: 0x9fe6ff, transparent: true, opacity: .55,
      blending: THREE.AdditiveBlending, depthWrite: false });
    this.fadeMats.push([sm, .55]);
    this.halo = new THREE.Sprite(sm); this.halo.scale.setScalar(1.6);
    this.root.add(this.halo);
  }

  _wire() {
    const geo = new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(1.05, 1));
    const m = new THREE.LineBasicMaterial({ color: 0x58d2ff, transparent: true, opacity: .16,
      blending: THREE.AdditiveBlending, depthWrite: false });
    this.fadeMats.push([m, .16]);
    this.wire = new THREE.LineSegments(geo, m);
    this.root.add(this.wire);
  }

  _arcs() {
    // arcs HUD épais, en plusieurs anneaux inclinés qui tournent à des vitesses différentes
    this.arcs = [];
    const specs = [
      { r: 2.02, w: .018, segs: [[0, .9], [1.1, .35], [1.6, 1.4], [3.3, .25], [3.7, 1.9]], tilt: [1.35, 0, .12], speed: .12, op: .55 },
      { r: 2.16, w: .006, segs: [[0, TAU]], tilt: [1.35, 0, .12], speed: 0, op: .18 },
      { r: 2.32, w: .03, segs: [[.4, .5], [2.4, .8], [4.4, .3]], tilt: [1.1, .3, -.2], speed: -.2, op: .4 },
      { r: 1.86, w: .01, segs: [[0, 2.6], [3.1, 2.6]], tilt: [.4, .9, 0], speed: .32, op: .32 },
      { r: 2.55, w: .004, segs: [[0, TAU]], tilt: [1.57, 0, 0], speed: 0, op: .12 },
    ];
    for (const s of specs) {
      const grp = new THREE.Group();
      for (const [start, len] of s.segs) {
        const m = new THREE.MeshBasicMaterial({ color: 0x5ad4ff, transparent: true, opacity: s.op, side: THREE.DoubleSide,
          blending: THREE.AdditiveBlending, depthWrite: false });
        this.fadeMats.push([m, s.op]);
        grp.add(new THREE.Mesh(new THREE.RingGeometry(s.r - s.w, s.r + s.w, Math.max(8, Math.ceil(len * 40)), 1, start, len), m));
      }
      const holder = new THREE.Group(); holder.rotation.set(...s.tilt); holder.add(grp);
      this.root.add(holder);
      this.arcs.push({ grp, speed: s.speed, holder });
    }
  }

  _ticks() {
    // graduations façon instrument : une longue tous les dix degrés
    const pts = [], R = 2.42;
    for (let i = 0; i < 180; i++) {
      const a = i / 180 * TAU, l = i % 18 === 0 ? .1 : i % 3 === 0 ? .045 : .02;
      pts.push(new THREE.Vector3(Math.cos(a) * R, Math.sin(a) * R, 0), new THREE.Vector3(Math.cos(a) * (R + l), Math.sin(a) * (R + l), 0));
    }
    const m = new THREE.LineBasicMaterial({ color: 0x6fd8ff, transparent: true, opacity: .32,
      blending: THREE.AdditiveBlending, depthWrite: false });
    this.fadeMats.push([m, .32]);
    this.ticks = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), m);
    this.root.add(this.ticks);
  }

  _freq() {
    // anneau de fréquences : 144 barres radiales qui suivent la vraie voix de Jarvis
    this.freqN = 144; this.freqR = 1.92;
    this.freqPos = new Float32Array(this.freqN * 6);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.freqPos, 3));
    const m = new THREE.LineBasicMaterial({ color: 0xbff1ff, transparent: true, opacity: .85,
      blending: THREE.AdditiveBlending, depthWrite: false });
    this.freqMat = m;
    this.freq = new THREE.LineSegments(g, m);
    this.freq.frustumCulled = false;
    this.root.add(this.freq);
  }

  _satellites() {
    this.sats = [];
    const specs = [[2.02, [1.35, 0, .12], .5], [2.32, [1.1, .3, -.2], -.34], [1.86, [.4, .9, 0], .8]];
    for (const [r, tilt, speed] of specs) {
      const holder = new THREE.Group(); holder.rotation.set(...tilt);
      const sm = new THREE.SpriteMaterial({ map: this.glowTex, color: 0xd8f7ff, transparent: true, opacity: .9,
        blending: THREE.AdditiveBlending, depthWrite: false });
      this.fadeMats.push([sm, .9]);
      const sp = new THREE.Sprite(sm); sp.scale.setScalar(.16);
      holder.add(sp); this.root.add(holder);
      this.sats.push({ sp, r, speed, a: Math.random() * TAU });
    }
  }

  _dust() {
    const N = 1600, pos = new Float32Array(N * 3), seed = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      const r = 3 + Math.random() * 9, u = Math.random() * TAU, v = Math.acos(2 * Math.random() - 1);
      pos.set([r * Math.sin(v) * Math.cos(u), r * Math.cos(v) * .6, r * Math.sin(v) * Math.sin(u) - 3], i * 3);
      seed[i] = Math.random();
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
    this.du = { uTime: { value: 0 }, uPixel: { value: this.pixel }, uColor: { value: new THREE.Color(0x4fc8ff) }, uFade: { value: 1 } };
    this.dust = new THREE.Points(g, new THREE.ShaderMaterial({ uniforms: this.du, vertexShader: DUST_VS, fragmentShader: DUST_FS,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.scene.add(this.dust);
  }

  _shockwave() {
    const m = new THREE.MeshBasicMaterial({ color: 0x9fe6ff, transparent: true, opacity: .8, side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending, depthWrite: false });
    const mesh = new THREE.Mesh(new THREE.RingGeometry(.98, 1, 128), m);
    this.root.add(mesh);
    this.shock.push({ mesh, t: 0 });
  }

  // ── API ─────────────────────────────────────────────────────────────

  setState(s) {
    if (!STATES[s] || s === this.state) return;
    this.state = s;
    if (s === 'listen') this._shockwave();
  }
  setLevel(v, bands) {
    this.levelTarget = Math.max(0, Math.min(1, v || 0));
    if (bands && bands.length) {
      for (let i = 0; i < BANDS; i++) this.bandsTarget[i] = bands[Math.floor(i * bands.length / BANDS)] || 0;
    }
  }
  setMic(v) { this.micTarget = Math.max(0, Math.min(1, v || 0)); }
  appear() { this.formTarget = 1; this.formSpeed = 1.15; this._shockwave(); }
  vanish() { this.formTarget = 0; this.formSpeed = 1.6; }
  get visible() { return this.formTarget > 0; }

  resize() {
    const w = innerWidth, h = innerHeight;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.bloom.resolution.set(w / 2, h / 2);
    this.camera.aspect = w / h;
    // le globe garde la même taille apparente en portrait comme en paysage
    this.camera.position.z = w / h < 1 ? 7.2 / (w / h) * .9 : 7.2;
    this.camera.updateProjectionMatrix();
  }

  frame() {
    const dt = Math.min(this.clock.getDelta(), 0.05), t = this.clock.elapsedTime;
    const target = STATES[this.state];

    // lissage : attaque rapide, retombée douce
    const k = (cur, tgt, up, down) => lerp(cur, tgt, 1 - Math.exp(-(tgt > cur ? up : down) * dt));
    this.level = k(this.level, this.levelTarget, 28, 7);
    this.mic = k(this.mic, this.micTarget, 22, 6);
    for (let i = 0; i < BANDS; i++) this.bands[i] = k(this.bands[i], this.bandsTarget[i], 30, 8);
    for (const key of ['agit', 'spin', 'glow', 'bloom']) this.params[key] = lerp(this.params[key], target[key], 1 - Math.exp(-3 * dt));
    this.colorA.lerp(this._tA.set(target.a), 1 - Math.exp(-3.5 * dt));
    this.colorB.lerp(this._tB.set(target.b), 1 - Math.exp(-3.5 * dt));

    const dir = Math.sign(this.formTarget - this.form);
    this.form = Math.max(0, Math.min(1, this.form + dir * dt * this.formSpeed));
    const fade = ease(this.form);
    const p = this.params, voice = this.level, think = this.state === 'think' ? 1 : 0;

    // particules
    this.pu.uTime.value = t; this.pu.uLevel.value = voice; this.pu.uMic.value = this.mic;
    this.pu.uAgit.value = p.agit; this.pu.uForm.value = this.form; this.pu.uFade.value = .35 + .65 * fade;
    this.pu.uSwirl.value = lerp(this.pu.uSwirl.value, think * 1.4, 1 - Math.exp(-2 * dt));
    this.spin.rotation.y += dt * p.spin;
    this.spin.rotation.x = Math.sin(t * .11) * .08;
    const breathe = 1 + Math.sin(t * 1.3) * .012 + voice * .06 + this.mic * .04;
    this.spin.scale.setScalar(breathe * (.6 + .4 * fade));

    // balayage
    const sy = Math.sin(t * .55) * 1.5, sr = Math.sqrt(Math.max(0.0001, 1.6 * 1.6 - sy * sy));
    this.scan.position.y = sy; this.scan.scale.setScalar(sr);
    this.scan.material.opacity = (.22 + .3 * Math.abs(Math.cos(t * .55))) * fade;

    // cœur et halo
    this.coreU.uPower.value = p.glow * (1 + voice * 1.8 + this.mic * .8 + Math.sin(t * 2.2) * .05);
    this.coreU.uFade.value = fade;
    this.core.scale.setScalar(.85 + voice * .45 + this.mic * .2 + think * Math.sin(t * 6) * .04);
    this.halo.scale.setScalar(1.3 + voice * 1.6 + this.mic * .6);
    this.halo.material.color.copy(this.colorB);

    this.wire.rotation.x -= dt * .07 * (1 + think * 3); this.wire.rotation.y -= dt * .11 * (1 + think * 3);
    this.wire.scale.setScalar((.9 + voice * .2) * fade);
    for (const a of this.arcs) {
      a.grp.rotation.z += dt * a.speed * (1 + think * 2.5);
      a.holder.scale.setScalar(lerp(1.6, 1, fade));
    }
    this.ticks.rotation.z -= dt * .02 * (1 + think * 4);
    this.ticks.scale.setScalar(lerp(1.5, 1, fade));
    for (const s of this.sats) {
      s.a += dt * s.speed * (1 + think * 2);
      s.sp.position.set(Math.cos(s.a) * s.r, Math.sin(s.a) * s.r, 0);
      s.sp.scale.setScalar(.12 + voice * .12 + Math.sin(t * 3 + s.r) * .02);
    }

    // anneau de fréquences, symétrique, face à la caméra
    const N = this.freqN, R = this.freqR * (.92 + .08 * fade);
    for (let i = 0; i < N; i++) {
      const a = i / N * TAU + Math.PI / 2;
      const m = Math.abs(((i / N) * 2) % 2 - 1);              // 0 → 1 → 0 : miroir gauche/droite
      const b = this.bands[Math.min(BANDS - 1, Math.floor(m * BANDS))];
      const idle = (Math.sin(t * 2 + i * .7) * .5 + .5) * .006;
      const len = (idle + b * .55 + voice * .08 + this.mic * .12 * (Math.sin(i * 1.3 + t * 9) * .5 + .5)) * fade;
      const c = Math.cos(a), s = Math.sin(a);
      this.freqPos.set([c * R, s * R, 0, c * (R + len), s * (R + len), 0], i * 6);
    }
    this.freq.geometry.attributes.position.needsUpdate = true;
    this.freqMat.color.copy(this.colorB);
    this.freqMat.opacity = (.04 + .8 * Math.min(1, voice * 2.5 + this.mic * 2.5)) * fade;

    // matériaux simples : teinte suivant l'état, opacité suivant l'apparition
    this._mid.copy(this.colorA).lerp(this.colorB, .5);
    for (const [m, base] of this.fadeMats) {
      m.opacity = base * fade;
      if (m !== this.halo.material) m.color.lerp(this._mid, 1 - Math.exp(-3 * dt));
    }
    this.du.uTime.value = t; this.du.uFade.value = .25 + .75 * fade;
    this.du.uColor.value.copy(this.colorA);

    // ondes de choc
    for (const s of this.shock) {
      s.t += dt;
      const q = s.t / 1.4;
      s.mesh.scale.setScalar(1.2 + ease(Math.min(1, q)) * 3.2);
      s.mesh.material.opacity = Math.max(0, .7 * (1 - q));
    }
    this.shock = this.shock.filter((s) => {
      if (s.t < 1.4) return true;
      this.root.remove(s.mesh); s.mesh.geometry.dispose(); s.mesh.material.dispose(); return false;
    });

    // parallaxe douce à la souris
    this.mouseSmooth.lerp(this.mouse, 1 - Math.exp(-2 * dt));
    this.root.rotation.y = this.mouseSmooth.x * .18;
    this.root.rotation.x = this.mouseSmooth.y * .12;
    this.dust.rotation.y = t * .01 + this.mouseSmooth.x * .05;

    this.bloom.strength = p.bloom * (1 + voice * .5) * (.4 + .6 * fade);
    this.composer.render();
  }
}
