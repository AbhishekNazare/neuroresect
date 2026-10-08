"use client";
import {
  Component,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Canvas, ThreeEvent, useFrame } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { Box, RotateCcw } from "lucide-react";
import type { Connectome, Region, Resection } from "@/lib/types";

export const NETWORK_COLORS: Record<string, string> = {
  visual: "#a9b9f3",
  somatomotor: "#65c6b9",
  "dorsal-attention": "#ccbe89",
  "ventral-attention": "#da9caf",
  limbic: "#e3aa6e",
  frontoparietal: "#88b4d3",
  "default-mode": "#b3a4d1",
};
type Props = {
  connectome: Connectome;
  regions: Resection[];
  mode: "anatomy" | "network" | "resection" | "sensitivity";
  threshold: number;
  transition: number;
  sensitivityScores?: { region_id: number; score: number }[];
  hemisphere: "both" | "left" | "right";
  onSelect: (id: number) => void;
  hovered: number | null;
  onHover: (id: number | null) => void;
  autoRotate: boolean;
};
const position = (n: Region): [number, number, number] => [
  n.x * 1.13,
  n.z * 1.03,
  -n.y * 1.02,
];
function cortexGeometry(side: number) {
  const geometry = new THREE.SphereGeometry(1, 100, 100);
  const p = geometry.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i),
      y = p.getY(i),
      z = p.getZ(i);
    const theta = Math.atan2(z, x),
      phi = Math.acos(Math.min(1, Math.max(-1, y)));
    const folds =
      Math.sin(theta * 18 + Math.sin(phi * 9) * 2.4) *
      Math.sin(phi * 16 + Math.sin(theta * 8) * 1.2);
    const secondary =
      Math.sin(theta * 31 + phi * 7) * Math.sin(phi * 23) * 0.013;
    const radius = 1 + folds * 0.038 + secondary;
    const taper = 1 - Math.max(0, -y) * 0.13;
    p.setXYZ(
      i,
      side * 0.43 + x * 0.67 * radius * taper,
      y * 0.88 * radius + 0.05,
      z * 1.35 * radius * (1 - Math.abs(y) * 0.1),
    );
  }
  geometry.computeVertexNormals();
  return geometry;
}
function Cortex({ mode, hemisphere }: Pick<Props, "mode" | "hemisphere">) {
  const left = useMemo(() => cortexGeometry(-1), []),
    right = useMemo(() => cortexGeometry(1), []);
  useEffect(
    () => () => {
      left.dispose();
      right.dispose();
    },
    [left, right],
  );
  return (
    <group>
      {[-1, 1].map(
        (side) =>
          (hemisphere === "both" ||
            hemisphere === (side === -1 ? "left" : "right")) && (
            <mesh
              key={side}
              geometry={side === -1 ? left : right}
              renderOrder={2}
            >
              <meshPhysicalMaterial
                color={mode === "anatomy" ? "#8faeaa" : "#72948f"}
                transparent
                opacity={mode === "anatomy" ? 0.68 : 0.12}
                roughness={0.52}
                metalness={0.08}
                side={THREE.DoubleSide}
                depthWrite={mode === "anatomy"}
                clearcoat={0.2}
              />
            </mesh>
          ),
      )}
    </group>
  );
}
function Graph({
  connectome,
  regions,
  mode,
  threshold,
  transition,
  sensitivityScores,
  hemisphere,
  onSelect,
  hovered,
  onHover,
}: Props) {
  const selected = useMemo(
    () => new Map(regions.map((r) => [r.region_id, r.fraction_removed])),
    [regions],
  );
  const visible = (n: Region) =>
    hemisphere === "both" ||
    n.hemisphere.toLowerCase().startsWith(hemisphere[0]);
  const nodes = useMemo(
    () => new Map(connectome.nodes.map((n) => [n.id, n])),
    [connectome.nodes],
  );
  const edgeGeometry = useMemo(() => {
    const positions: number[] = [],
      colors: number[] = [];
    const maxWeight = Math.max(...connectome.edges.map((e) => e.weight), 0.001);
    connectome.edges.forEach((edge) => {
      const a = nodes.get(edge.source),
        b = nodes.get(edge.target);
      if (
        !a ||
        !b ||
        !visible(a) ||
        !visible(b) ||
        edge.weight / maxWeight < threshold
      )
        return;
      const loss =
        1 - (1 - (selected.get(a.id) || 0)) * (1 - (selected.get(b.id) || 0));
      const remaining = 1 - loss * transition;
      if (remaining < 0.025) return;
      const color = new THREE.Color(loss > 0 ? "#e3aa6e" : "#68cabb");
      color.multiplyScalar(
        (0.24 + (edge.weight / maxWeight) * 0.7) * remaining,
      );
      positions.push(...position(a), ...position(b));
      colors.push(color.r, color.g, color.b, color.r, color.g, color.b);
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    return g;
    // Visibility is completely described by hemisphere; keep this expensive calculation stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectome, nodes, selected, threshold, transition, hemisphere]);
  useEffect(() => () => edgeGeometry.dispose(), [edgeGeometry]);
  return (
    <group>
      {mode !== "anatomy" && (
        <lineSegments geometry={edgeGeometry}>
          <lineBasicMaterial
            vertexColors
            transparent
            opacity={0.66}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </lineSegments>
      )}
      {connectome.nodes.filter(visible).map((node) => {
        const fraction = selected.get(node.id) || 0,
          active = hovered === node.id;
        const score =
          sensitivityScores?.find((s) => s.region_id === node.id)?.score || 0;
        const maximum = Math.max(
          ...(sensitivityScores || []).map((s) => s.score),
          0.000001,
        );
        const color =
          mode === "sensitivity"
            ? new THREE.Color("#467c80")
                .lerp(new THREE.Color("#f0b276"), score / maximum)
                .getStyle()
            : fraction
              ? "#f0b276"
              : NETWORK_COLORS[node.network] || "#79cbbc";
        return (
          <group key={node.id} position={position(node)}>
            <mesh
              onClick={(e: ThreeEvent<MouseEvent>) => {
                e.stopPropagation();
                onSelect(node.id);
              }}
              onPointerOver={(e) => {
                e.stopPropagation();
                onHover(node.id);
              }}
              onPointerOut={() => onHover(null)}
              scale={active ? 1.5 : 1}
            >
              <sphereGeometry args={[fraction ? 0.054 : 0.036, 12, 12]} />
              <meshStandardMaterial
                color={color}
                emissive={color}
                emissiveIntensity={active ? 1.2 : 0.4}
                transparent
                opacity={Math.max(0.18, 1 - fraction * transition)}
              />
            </mesh>
            {fraction > 0 && (
              <mesh>
                <sphereGeometry args={[0.087, 12, 12]} />
                <meshBasicMaterial
                  color={color}
                  transparent
                  opacity={0.12 * (1 - transition * 0.6)}
                  depthWrite={false}
                />
              </mesh>
            )}
            {active && (
              <Html
                distanceFactor={5}
                position={[0, 0.17, 0]}
                center
                style={{ pointerEvents: "none" }}
              >
                <div className="node-tooltip">
                  <strong>{node.name}</strong>
                  <span>
                    {node.network.replaceAll("-", " ")} ·{" "}
                    {fraction
                      ? `${Math.round(fraction * 100)}% selected`
                      : "Click to select"}
                  </span>
                </div>
              </Html>
            )}
          </group>
        );
      })}
    </group>
  );
}
function Scene(props: Props) {
  const group = useRef<THREE.Group>(null);
  useFrame((state) => {
    if (group.current && props.autoRotate)
      group.current.position.y =
        Math.sin(state.clock.elapsedTime * 0.45) * 0.025;
  });
  return (
    <>
      <ambientLight intensity={1.0} />
      <directionalLight position={[-3, 5, 4]} intensity={3.0} color="#d5fff3" />
      <directionalLight
        position={[4, -1, -3]}
        intensity={1.5}
        color="#7b9fbb"
      />
      <group ref={group} rotation={[0.1, -0.2, -0.08]}>
        <Cortex mode={props.mode} hemisphere={props.hemisphere} />
        <Graph {...props} />
      </group>
      <OrbitControls
        makeDefault
        enablePan={false}
        minDistance={3.2}
        maxDistance={8}
        autoRotate={props.autoRotate}
        autoRotateSpeed={0.35}
        enableDamping
        dampingFactor={0.06}
      />
      <gridHelper
        args={[12, 24, "#294642", "#162825"]}
        position={[0, -1.23, 0]}
      />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.22, 0]}>
        <ringGeometry args={[1.78, 1.786, 96]} />
        <meshBasicMaterial
          color="#56746b"
          transparent
          opacity={0.5}
          side={THREE.DoubleSide}
        />
      </mesh>
    </>
  );
}
class SceneBoundary extends Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <Fallback /> : this.props.children;
  }
}
function Fallback() {
  return (
    <div className="scene-fallback">
      <Box size={40} />
      <h3>3D rendering unavailable</h3>
      <p>
        Your browser could not create a WebGL scene. All regions and analysis
        controls remain available in the region editor.
      </p>
    </div>
  );
}
export default function BrainScene(props: Props) {
  const [cameraKey, setCameraKey] = useState(0),
    [supported, setSupported] = useState<boolean | null>(null);
  useEffect(() => {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2");
    setSupported(!!context);
    context?.getExtension("WEBGL_lose_context")?.loseContext();
  }, []);
  return (
    <div
      className="brain-canvas"
      role="img"
      aria-label="Interactive synthetic brain network. Drag to rotate, scroll to zoom. Use the region editor for keyboard selection."
    >
      {supported === false ? (
        <Fallback />
      ) : (
        supported && (
          <SceneBoundary>
            <Canvas
              key={cameraKey}
              camera={{ position: [2.9, 1.5, 4.1], fov: 39 }}
              dpr={[1, 1.7]}
              gl={{ antialias: true, alpha: true }}
            >
              <Suspense fallback={null}>
                <Scene {...props} />
              </Suspense>
            </Canvas>
          </SceneBoundary>
        )
      )}
      <button
        className="icon-button reset-camera"
        onClick={() => setCameraKey((k) => k + 1)}
        aria-label="Reset 3D camera"
        title="Reset camera"
      >
        <RotateCcw size={15} />
      </button>
    </div>
  );
}
