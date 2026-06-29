import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import type { PhysicsAircraft, PhysicsSnapshot, PhysicsVehicle } from "../physics/types";

const VEHICLE_COLORS: Record<string, number> = {
  fuel: 0xf2a93b,
  baggage: 0x5cc8ff,
  catering: 0x94df65,
  bus: 0xe9d66b,
  pushback: 0xb8a7ff,
  maintenance: 0xff8f66,
  ambulance: 0xff4d5a,
  security: 0x39e6b1,
};

const AIRCRAFT_ASSETS: Record<string, { url: string; length: number }> = {
  dc8: { url: "/assets/nasa-aircraft/DC8_AFRC_AIR_0824.glb", length: 12.5 },
  g3: { url: "/assets/nasa-aircraft/G3_JSC_AIR_0824.glb", length: 8.5 },
};

const AIRCRAFT_MODEL_CACHE = new Map<string, Promise<THREE.Group>>();
const SHARED_GLTF_LOADER = new GLTFLoader();

function worldPoint(x: number, y: number, z = 0): THREE.Vector3 {
  return new THREE.Vector3(x, z, -y);
}

function lerpAngle(current: number, target: number, alpha: number): number {
  const delta = Math.atan2(Math.sin(target - current), Math.cos(target - current));
  return current + delta * alpha;
}

function makeLabelTexture(text: string, color: string, width = 320): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = 84;
  const ctx = canvas.getContext("2d")!;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "rgba(6, 8, 6, 0.86)";
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.roundRect(8, 8, width - 16, 68, 8);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#f5eed5";
  ctx.font = "800 24px Inter, sans-serif";
  ctx.fillText(text, 22, 38);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function makeRunwayNumberTexture(text: string): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#f4efe0";
  ctx.font = "900 118px Inter, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 128, 128);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function prepareModelObject(object: THREE.Object3D): void {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.castShadow = false;
    mesh.receiveShadow = false;
    mesh.frustumCulled = true;
  });
}

function normalizeModel(source: THREE.Group, targetLength: number): THREE.Group {
  const wrapper = new THREE.Group();
  const model = source.clone(true);
  prepareModelObject(model);
  const box = new THREE.Box3().setFromObject(model);
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  box.getSize(size);
  box.getCenter(center);
  const longest = Math.max(size.x, size.y, size.z, 0.001);
  const scale = targetLength / longest;
  model.position.set(-center.x, -center.y, -center.z);
  wrapper.add(model);
  wrapper.scale.setScalar(scale);
  return wrapper;
}

function loadSharedAircraftModel(key: string, asset: { url: string; length: number }): Promise<THREE.Group> {
  const existing = AIRCRAFT_MODEL_CACHE.get(key);
  if (existing) return existing;

  const promise = SHARED_GLTF_LOADER.loadAsync(asset.url).then((gltf) => normalizeModel(gltf.scene, asset.length));
  AIRCRAFT_MODEL_CACHE.set(key, promise);
  return promise;
}

function compactGpuLabel(renderer: string): string {
  const lower = renderer.toLowerCase();
  if (lower.includes("nvidia") || lower.includes("quadro") || lower.includes("geforce")) return "GPU NVIDIA";
  if (lower.includes("intel")) return "GPU Intel";
  if (lower.includes("swiftshader") || lower.includes("llvmpipe") || lower.includes("software")) return "GPU software";
  return "GPU high-perf";
}

class VehicleMesh {
  group: THREE.Group;
  beacon: THREE.Mesh;
  label: THREE.Sprite;
  trail: THREE.Line;
  trailPoints: THREE.Vector3[] = [];
  private targetPosition = new THREE.Vector3();
  private targetYaw = 0;
  private initialized = false;

  constructor(vehicle: PhysicsVehicle) {
    const color = VEHICLE_COLORS[vehicle.kind] ?? 0xffffff;
    const material = new THREE.MeshStandardMaterial({
      color,
      roughness: 0.42,
      metalness: 0.18,
      emissive: color,
      emissiveIntensity: vehicle.kind === "ambulance" ? 0.18 : 0.05,
    });
    const dimensions = this.dimensions(vehicle.kind);
    this.group = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(dimensions.length, dimensions.height, dimensions.width), material);
    body.castShadow = true;
    body.receiveShadow = true;
    body.position.y = dimensions.height / 2;
    this.group.add(body);

    const wheelMaterial = new THREE.MeshStandardMaterial({ color: 0x070b0b, roughness: 0.8 });
    const wheelGeometry = new THREE.CylinderGeometry(0.18, 0.18, 0.16, 18);
    for (const x of [-dimensions.length * 0.32, dimensions.length * 0.32]) {
      for (const z of [-dimensions.width * 0.58, dimensions.width * 0.58]) {
        const wheel = new THREE.Mesh(wheelGeometry, wheelMaterial);
        wheel.rotation.z = Math.PI / 2;
        wheel.position.set(x, 0.18, z);
        this.group.add(wheel);
      }
    }

    this.beacon = new THREE.Mesh(
      new THREE.SphereGeometry(dimensions.length * 0.58, 24, 12),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.08, depthWrite: false }),
    );
    this.beacon.position.y = 0.12;
    this.group.add(this.beacon);

    this.label = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: makeLabelTexture(vehicle.label, `#${color.toString(16).padStart(6, "0")}`, 236),
        transparent: true,
        depthWrite: false,
      }),
    );
    this.label.scale.set(2.5, 0.66, 1);
    this.label.position.set(0, 1.75, 0);
    this.group.add(this.label);

    this.trail = new THREE.Line(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.48 }),
    );
  }

  update(vehicle: PhysicsVehicle, priority: boolean): void {
    this.targetPosition.copy(worldPoint(vehicle.pose.x, vehicle.pose.y, vehicle.pose.z));
    this.targetYaw = -vehicle.pose.yaw;
    if (!this.initialized) {
      this.group.position.copy(this.targetPosition);
      this.group.rotation.y = this.targetYaw;
      this.initialized = true;
    }
    this.beacon.visible = priority || vehicle.status === "priority";
    this.beacon.scale.setScalar(priority ? 1.35 : 1.0);

    const trailPoint = worldPoint(vehicle.pose.x, vehicle.pose.y, 0.08);
    const previous = this.trailPoints.at(-1);
    if (!previous || previous.distanceTo(trailPoint) > 0.45) {
      this.trailPoints.push(trailPoint);
      if (this.trailPoints.length > 44) this.trailPoints.shift();
      this.trail.geometry.dispose();
      this.trail.geometry = new THREE.BufferGeometry().setFromPoints(this.trailPoints);
    }
  }

  animate(alpha: number): void {
    this.group.position.lerp(this.targetPosition, alpha);
    this.group.rotation.y = lerpAngle(this.group.rotation.y, this.targetYaw, alpha);
  }

  private dimensions(kind: string): { length: number; width: number; height: number } {
    if (kind === "bus") return { length: 3.3, width: 1.2, height: 1.0 };
    if (kind === "fuel") return { length: 2.5, width: 1.05, height: 0.72 };
    if (kind === "pushback") return { length: 1.75, width: 1.0, height: 0.58 };
    return { length: 2.1, width: 0.96, height: 0.68 };
  }
}

class AircraftMesh {
  group = new THREE.Group();
  label: THREE.Sprite;
  riskRing: THREE.Mesh;
  trail: THREE.Line;
  trailPoints: THREE.Vector3[] = [];
  private visual = new THREE.Group();
  private hasModel = false;
  private labelKey = "";
  private targetPosition = new THREE.Vector3();
  private targetYaw = 0;
  private targetScale = 1;
  private initialized = false;

  constructor(aircraft: PhysicsAircraft) {
    this.group.add(this.visual);
    this.visual.add(this.makeFallbackModel(aircraft.modelKey));

    this.label = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: makeLabelTexture(`${aircraft.callsign}  ${aircraft.altitudeFt}ft`, "#f4d05e", 360),
        transparent: true,
        depthWrite: false,
      }),
    );
    this.labelKey = `${aircraft.callsign}  ${aircraft.altitudeFt}ft`;
    this.label.scale.set(4.4, 1.05, 1);
    this.label.position.set(0, 2.2, 0);
    this.group.add(this.label);

    this.riskRing = new THREE.Mesh(
      new THREE.TorusGeometry(3.4, 0.055, 8, 72),
      new THREE.MeshBasicMaterial({ color: 0xff3151, transparent: true, opacity: 0.0, depthWrite: false }),
    );
    this.riskRing.rotation.x = Math.PI / 2;
    this.group.add(this.riskRing);

    this.trail = new THREE.Line(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ color: 0xf4d05e, transparent: true, opacity: 0.7 }),
    );
  }

  setModel(template: THREE.Group): void {
    if (this.hasModel) return;
    this.visual.clear();
    const clone = template.clone(true);
    prepareModelObject(clone);
    this.visual.add(clone);
    this.hasModel = true;
  }

  update(aircraft: PhysicsAircraft, modelTemplate: THREE.Group | undefined): void {
    if (!this.hasModel && modelTemplate) this.setModel(modelTemplate);
    this.targetPosition.copy(worldPoint(aircraft.pose.x, aircraft.pose.y, aircraft.pose.z));
    this.targetYaw = -aircraft.pose.yaw;
    this.targetScale = aircraft.phase === "approach" || aircraft.phase === "go_around" ? 1.0 : 0.78;
    if (!this.initialized) {
      this.group.position.copy(this.targetPosition);
      this.group.rotation.y = this.targetYaw;
      this.group.scale.setScalar(this.targetScale);
      this.initialized = true;
    }
    this.label.position.y = aircraft.pose.z > 2 ? 2.6 : 1.8;
    const altitude = Math.round(aircraft.altitudeFt / 100) * 100;
    const eta = aircraft.etaRunwayMs === null ? "" : `  ETA ${Math.max(0, Math.ceil(aircraft.etaRunwayMs / 1000))}s`;
    const color = aircraft.risk > 60 ? "#ff3151" : "#f4d05e";
    const nextLabel = `${aircraft.callsign}  ${altitude}ft${eta}`;
    const nextLabelKey = `${nextLabel}|${color}`;
    if (nextLabelKey !== this.labelKey) {
      const labelMaterial = this.label.material as THREE.SpriteMaterial;
      labelMaterial.map?.dispose();
      labelMaterial.map = makeLabelTexture(nextLabel, color, 420);
      labelMaterial.needsUpdate = true;
      this.labelKey = nextLabelKey;
    }

    const ringMaterial = this.riskRing.material as THREE.MeshBasicMaterial;
    ringMaterial.opacity = aircraft.risk > 30 ? Math.min(0.72, aircraft.risk / 130) : 0;
    ringMaterial.color.set(aircraft.risk > 70 ? 0xff3151 : 0xf4d05e);
    this.riskRing.scale.setScalar(1 + aircraft.risk / 140);

    const trailPoint = worldPoint(aircraft.pose.x, aircraft.pose.y, aircraft.pose.z);
    const previous = this.trailPoints.at(-1);
    if (!previous || previous.distanceTo(trailPoint) > 1.05) {
      this.trailPoints.push(trailPoint);
      if (this.trailPoints.length > 42) this.trailPoints.shift();
      this.trail.geometry.dispose();
      this.trail.geometry = new THREE.BufferGeometry().setFromPoints(this.trailPoints);
    }
  }

  animate(alpha: number): void {
    this.group.position.lerp(this.targetPosition, alpha);
    this.group.rotation.y = lerpAngle(this.group.rotation.y, this.targetYaw, alpha);
    const scale = THREE.MathUtils.lerp(this.group.scale.x, this.targetScale, alpha);
    this.group.scale.setScalar(scale);
  }

  private makeFallbackModel(modelKey: string): THREE.Group {
    const group = new THREE.Group();
    const color = modelKey === "dc8" ? 0xdfe8ea : 0xe8e0c8;
    const material = new THREE.MeshStandardMaterial({ color, roughness: 0.43, metalness: 0.34 });
    const darkMaterial = new THREE.MeshStandardMaterial({ color: 0x1a211f, roughness: 0.55, metalness: 0.22 });
    const length = modelKey === "dc8" ? 12.5 : 8.5;
    const span = modelKey === "dc8" ? 11.4 : 7.6;
    const chord = modelKey === "dc8" ? 2.2 : 1.55;
    const fuselage = new THREE.Mesh(new THREE.CapsuleGeometry(0.52, length, 16, 32), material);
    fuselage.rotation.z = Math.PI / 2;
    group.add(fuselage);

    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.54, 1.45, 24), material);
    nose.rotation.z = -Math.PI / 2;
    nose.position.x = length * 0.54;
    group.add(nose);

    const wings = new THREE.Mesh(new THREE.BoxGeometry(chord, 0.14, span), material);
    wings.position.x = length * 0.04;
    wings.position.y = -0.02;
    group.add(wings);

    const tailplane = new THREE.Mesh(new THREE.BoxGeometry(chord * 0.72, 0.14, span * 0.34), material);
    tailplane.position.x = -length * 0.42;
    tailplane.position.y = 0.26;
    group.add(tailplane);

    const fin = new THREE.Mesh(new THREE.BoxGeometry(chord * 0.42, 1.18, 0.16), material);
    fin.position.x = -length * 0.46;
    fin.position.y = 0.82;
    group.add(fin);

    const engineGeometry = new THREE.CylinderGeometry(0.18, 0.18, 0.72, 16);
    for (const z of [-span * 0.24, span * 0.24]) {
      const engine = new THREE.Mesh(engineGeometry, darkMaterial);
      engine.rotation.z = Math.PI / 2;
      engine.position.set(length * 0.04, -0.34, z);
      group.add(engine);
    }
    return group;
  }
}

export class AirportScene {
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(45, 1, 0.1, 180);
  private renderer: THREE.WebGLRenderer;
  private gpuRenderer = "GPU pending";
  private vehicles = new Map<string, VehicleMesh>();
  private aircraft = new Map<string, AircraftMesh>();
  private aircraftModels = new Map<string, THREE.Group>();
  private rules = new Map<string, THREE.Mesh>();
  private contacts = new THREE.Group();
  private animationPhase = 0;
  private lastRenderMs = 0;

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: false,
      antialias: false,
      powerPreference: "high-performance",
      preserveDrawingBuffer: true,
      failIfMajorPerformanceCaveat: false,
    });
    this.renderer.setClearColor(0x070806, 1);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.shadowMap.enabled = false;
    this.gpuRenderer = this.detectGpuRenderer();
    canvas.dataset.gpuRenderer = this.gpuRenderer;
    this.scene.fog = new THREE.Fog(0x070806, 72, 145);
    this.camera.position.set(13, 45, 48);
    this.camera.lookAt(0, 0, 22);

    const ambient = new THREE.HemisphereLight(0xd9f3ee, 0x050706, 1.22);
    this.scene.add(ambient);
    const key = new THREE.DirectionalLight(0xffffff, 2.35);
    key.position.set(-22, 38, 21);
    this.scene.add(key);
    this.scene.add(this.contacts);

    this.buildStaticWorld();
    this.loadAircraftModels();
  }

  resize(width: number, height: number, ratio: number): void {
    const cappedRatio = Math.min(Math.max(1, ratio), 1.25);
    const targetWidth = Math.max(1, Math.floor(width * cappedRatio));
    const targetHeight = Math.max(1, Math.floor(height * cappedRatio));
    if (this.renderer.domElement.width !== targetWidth || this.renderer.domElement.height !== targetHeight) {
      this.renderer.setPixelRatio(cappedRatio);
      this.renderer.setSize(width, height, false);
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
    }
  }

  update(snapshot: PhysicsSnapshot | null): void {
    if (!snapshot) return;
    for (const vehicle of snapshot.vehicles) {
      let mesh = this.vehicles.get(vehicle.id);
      if (!mesh) {
        mesh = new VehicleMesh(vehicle);
        this.vehicles.set(vehicle.id, mesh);
        this.scene.add(mesh.group);
        this.scene.add(mesh.trail);
      }
      mesh.update(vehicle, vehicle.id === snapshot.priorityVehicleId);
    }

    for (const plane of snapshot.aircraft) {
      let mesh = this.aircraft.get(plane.id);
      if (!mesh) {
        mesh = new AircraftMesh(plane);
        this.aircraft.set(plane.id, mesh);
        this.scene.add(mesh.group);
        this.scene.add(mesh.trail);
      }
      const useRealModel = plane.id === "nasa742" || plane.id === "gulf3";
      mesh.update(plane, useRealModel ? this.aircraftModels.get(plane.modelKey) : undefined);
    }

    for (const mesh of this.rules.values()) mesh.visible = false;
    for (const rule of snapshot.activeRules) {
      const zone = snapshot.zones[rule.zone];
      if (!zone) continue;
      let mesh = this.rules.get(rule.zone);
      if (!mesh) {
        const material = new THREE.MeshBasicMaterial({
          color: 0xf4bd54,
          transparent: true,
          opacity: 0.24,
          depthWrite: false,
        });
        mesh = new THREE.Mesh(new THREE.BoxGeometry(zone.width, 0.18, zone.height), material);
        mesh.position.copy(worldPoint(zone.x + zone.width / 2, zone.y + zone.height / 2, 0.16));
        this.rules.set(rule.zone, mesh);
        this.scene.add(mesh);
      }
      mesh.visible = true;
      const material = mesh.material as THREE.MeshBasicMaterial;
      const critical = ["emergency_only", "stale_conflict", "runway_closed", "crossing_lockout", "incursion"].includes(rule.rule);
      material.color.set(critical ? 0xff334c : 0xf4bd54);
      material.opacity = critical ? 0.34 : 0.24;
      mesh.scale.y = 1 + Math.sin(this.animationPhase) * 0.18;
    }

    this.contacts.clear();
    for (const contact of snapshot.contacts) {
      const a = snapshot.vehicles.find((vehicle) => vehicle.id === contact.a);
      const b = snapshot.vehicles.find((vehicle) => vehicle.id === contact.b);
      if (!a || !b) continue;
      const points = [worldPoint(a.pose.x, a.pose.y, 0.25), worldPoint(b.pose.x, b.pose.y, 0.25)];
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineBasicMaterial({ color: 0xff3750, transparent: true, opacity: 0.9 }),
      );
      this.contacts.add(line);
    }
  }

  render(timeMs: number): void {
    this.animationPhase = timeMs / 260;
    const deltaMs = this.lastRenderMs ? Math.min(50, timeMs - this.lastRenderMs) : 16.7;
    this.lastRenderMs = timeMs;
    const smoothing = 1 - Math.exp(-deltaMs / 70);
    for (const mesh of this.vehicles.values()) mesh.animate(smoothing);
    for (const mesh of this.aircraft.values()) mesh.animate(smoothing);
    for (const mesh of this.rules.values()) {
      if (mesh.visible) mesh.rotation.y = Math.sin(this.animationPhase) * 0.01;
    }
    for (const mesh of this.aircraft.values()) {
      mesh.riskRing.rotation.z += 0.012;
    }
    this.camera.position.x = 13 + Math.sin(timeMs / 13000) * 1.8;
    this.camera.position.z = 48 + Math.cos(timeMs / 15000) * 1.4;
    this.camera.lookAt(0, 0, 22);
    this.renderer.render(this.scene, this.camera);
  }

  capture(): string {
    const source = this.renderer.domElement;
    const maxWidth = 640;
    const scale = Math.min(1, maxWidth / source.width);
    if (scale >= 1) return source.toDataURL("image/jpeg", 0.72);

    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(source.width * scale));
    canvas.height = Math.max(1, Math.round(source.height * scale));
    const context = canvas.getContext("2d");
    if (!context) return source.toDataURL("image/jpeg", 0.72);
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.72);
  }

  dispose(): void {
    this.renderer.dispose();
  }

  gpuLabel(): string {
    return compactGpuLabel(this.gpuRenderer);
  }

  private detectGpuRenderer(): string {
    const gl = this.renderer.getContext();
    const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
    if (!debugInfo) return "unavailable";
    return String(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || "unknown");
  }

  private loadAircraftModels(): void {
    for (const [key, asset] of Object.entries(AIRCRAFT_ASSETS)) {
      void loadSharedAircraftModel(key, asset)
        .then((model) => this.aircraftModels.set(key, model))
        .catch(() => this.aircraftModels.delete(key));
    }
  }

  private buildStaticWorld(): void {
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(118, 82),
      new THREE.MeshStandardMaterial({ color: 0x111512, roughness: 0.9, metalness: 0.02 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    this.scene.add(floor);

    const grid = new THREE.GridHelper(116, 58, 0x22352f, 0x16221f);
    grid.position.y = 0.012;
    this.scene.add(grid);

    this.addRunway();
    this.addTaxiways();
    this.addApronAndBuildings();
    this.addApproachLights();
    this.addGroundSigns();
  }

  private addRunway(): void {
    this.addRect(0, -24, 96, 6.8, 0x171a18, 0.04, 0);
    this.addRect(0, -20.1, 96, 0.12, 0xf5efe0, 0.08, 0);
    this.addRect(0, -27.9, 96, 0.12, 0xf5efe0, 0.08, 0);

    for (let x = -39; x <= 39; x += 8) {
      this.addRect(x, -24, 3.6, 0.16, 0xf5efe0, 0.1, 0);
    }
    for (let x = -46; x <= -39; x += 1.15) this.addRect(x, -22.2, 0.36, 1.45, 0xf5efe0, 0.11, 0);
    for (let x = -46; x <= -39; x += 1.15) this.addRect(x, -25.8, 0.36, 1.45, 0xf5efe0, 0.11, 0);
    for (let x = 39; x <= 46; x += 1.15) this.addRect(x, -22.2, 0.36, 1.45, 0xf5efe0, 0.11, 0);
    for (let x = 39; x <= 46; x += 1.15) this.addRect(x, -25.8, 0.36, 1.45, 0xf5efe0, 0.11, 0);
    this.addRunwayNumber(-35.5, -24, "09", Math.PI / 2);
    this.addRunwayNumber(35.5, -24, "27", -Math.PI / 2);
  }

  private addTaxiways(): void {
    this.addRect(-2, -18.1, 5.4, 11.8, 0x263632, 0.055, 0);
    this.addRect(27, -17.4, 8.4, 13.5, 0x263632, 0.055, 0);
    this.addRect(-14, -13, 32, 3.2, 0x243430, 0.06, 0);
    this.addRect(11, -13, 24, 3.2, 0x243430, 0.06, 0);
    this.addRect(1, 9.4, 34, 2.9, 0x243430, 0.06, 0);
    this.addRect(-14.7, -5.4, 18.8, 2.4, 0x243430, 0.06, -0.78);
    this.addRect(10.1, -4.3, 21.0, 2.4, 0x243430, 0.06, 1.08);
    for (let x = -18; x <= 22; x += 4) this.addRect(x, -13, 1.6, 0.12, 0xf2c84f, 0.1, 0);
    this.addRect(-2, -18.1, 0.12, 11.0, 0xf2c84f, 0.1, 0);
    this.addRect(27, -17.4, 0.12, 12.4, 0xf2c84f, 0.1, 0);
  }

  private addApronAndBuildings(): void {
    this.addRect(20.5, -2.2, 18, 12, 0x374541, 0.07, 0);
    this.addRect(17, 8.8, 22, 10, 0x31403c, 0.07, 0);
    this.addRect(-19, 6, 18, 13, 0x222c29, 0.065, 0);

    const terminal = new THREE.Mesh(
      new THREE.BoxGeometry(25, 4.2, 6),
      new THREE.MeshStandardMaterial({ color: 0x252b29, roughness: 0.65, metalness: 0.18 }),
    );
    terminal.position.copy(worldPoint(1, 15.4, 3));
    terminal.castShadow = true;
    terminal.receiveShadow = true;
    this.scene.add(terminal);

    const tower = new THREE.Group();
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.65, 0.9, 9, 18), new THREE.MeshStandardMaterial({ color: 0x303b38 }));
    shaft.position.y = 4.5;
    const cab = new THREE.Mesh(new THREE.BoxGeometry(4.6, 2.0, 3.2), new THREE.MeshStandardMaterial({ color: 0x465a56, roughness: 0.38, metalness: 0.22 }));
    cab.position.y = 10.1;
    tower.add(shaft, cab);
    tower.position.copy(worldPoint(-28, 17, 0));
    this.scene.add(tower);

    this.addRect(2.5, -2.1, 6.0, 4.0, 0xd94a2f, 0.14, 0, 0.28);
  }

  private addApproachLights(): void {
    const material = new THREE.MeshBasicMaterial({ color: 0xf7f0d5 });
    const red = new THREE.MeshBasicMaterial({ color: 0xff3151 });
    for (let x = -62; x < -45; x += 3) {
      const light = new THREE.Mesh(new THREE.SphereGeometry(0.14, 12, 8), material);
      light.position.copy(worldPoint(x, -24, 0.18));
      this.scene.add(light);
    }
    for (const y of [-26.4, -25.2, -22.8, -21.6]) {
      const p = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 8), y < -24 ? red : material);
      p.position.copy(worldPoint(-49.2, y, 0.2));
      this.scene.add(p);
    }
  }

  private addGroundSigns(): void {
    const signs = [
      { x: -7.2, y: -18.4, text: "D HOLD" },
      { x: 29.8, y: -18.0, text: "RWY 27" },
      { x: 19.8, y: -9.6, text: "GATE A" },
      { x: -28, y: 14.6, text: "TOWER" },
    ];
    for (const sign of signs) {
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({ map: makeLabelTexture(sign.text, "#f4d05e", 220), transparent: true, depthWrite: false }),
      );
      sprite.position.copy(worldPoint(sign.x, sign.y, 0.8));
      sprite.scale.set(2.4, 0.78, 1);
      this.scene.add(sprite);
    }
  }

  private addRect(x: number, y: number, width: number, height: number, color: number, z: number, yaw: number, opacity = 1): void {
    const transparent = opacity < 1;
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(width, 0.05, height),
      new THREE.MeshStandardMaterial({ color, roughness: 0.74, metalness: 0.04, transparent, opacity }),
    );
    mesh.position.copy(worldPoint(x, y, z));
    mesh.rotation.y = yaw;
    mesh.receiveShadow = true;
    this.scene.add(mesh);
  }

  private addRunwayNumber(x: number, y: number, text: string, yaw: number): void {
    const material = new THREE.MeshBasicMaterial({
      map: makeRunwayNumberTexture(text),
      transparent: true,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(4.6, 4.6), material);
    mesh.rotation.x = -Math.PI / 2;
    mesh.rotation.z = yaw;
    mesh.position.copy(worldPoint(x, y, 0.13));
    this.scene.add(mesh);
  }
}
