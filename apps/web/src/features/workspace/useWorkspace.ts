"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, poll, post } from "@/lib/api";
import type {
  Atlas,
  Connectome,
  Counterfactual,
  Job,
  Patient,
  Prediction,
  Resection,
  Scenario,
  Sensitivity,
  Simulation,
} from "@/lib/types";
export function useWorkspace() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [atlases, setAtlases] = useState<Atlas[]>([]);
  const [patientId, setPatientId] = useState("");
  const [atlasId, setAtlasId] = useState("demo-64");
  const [connectome, setConnectome] = useState<Connectome | null>(null);
  const [regions, setRegions] = useState<Resection[]>([]);
  const [method, setMethodState] = useState<"weighted" | "binary">("weighted");
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [sensitivity, setSensitivity] = useState<Sensitivity | null>(null);
  const [counterfactual, setCounterfactual] = useState<Counterfactual | null>(
    null,
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [job, setJob] = useState<Job<unknown> | null>(null);
  const [reload, setReload] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const clearResults = useCallback(() => {
    setScenario(null);
    setSimulation(null);
    setPrediction(null);
    setSensitivity(null);
    setCounterfactual(null);
  }, []);
  const cancel = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    generation.current++;
    setBusy("");
    setJob(null);
  }, []);
  useEffect(() => {
    const ac = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      api<Patient[]>("/patients", { signal: ac.signal }),
      api<Atlas[]>("/atlases", { signal: ac.signal }),
    ])
      .then(([p, a]) => {
        setPatients(p);
        setAtlases(a);
        setPatientId((current) => current || p[0]?.id || "");
        if (!p.length) {
          setLoading(false);
          setError(
            "No patients are available. Import a de-identified connectome to begin.",
          );
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => ac.abort();
  }, [reload]);
  useEffect(() => {
    if (!patientId) return;
    const ac = new AbortController();
    cancel();
    clearResults();
    setConnectome(null);
    setRegions([]);
    setScenarios([]);
    setLoading(true);
    setError("");
    Promise.all([
      api<Connectome>(`/patients/${patientId}/connectome?atlas_id=${atlasId}`, {
        signal: ac.signal,
      }),
      api<Scenario[]>(`/scenarios?patient_id=${patientId}`, {
        signal: ac.signal,
      }),
    ])
      .then(([c, s]) => {
        setConnectome(c);
        setRegions(c.actual_resection);
        setScenarios(s);
        setLoading(false);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => ac.abort();
  }, [patientId, atlasId, reload, cancel, clearResults]);
  useEffect(() => () => controller.current?.abort(), []);
  function editRegions(next: Resection[]) {
    cancel();
    clearResults();
    setRegions(next.filter((r) => r.fraction_removed > 0));
    setError("");
  }
  function setMethod(value: "weighted" | "binary") {
    cancel();
    clearResults();
    setMethodState(value);
  }
  function changePatient(id: string) {
    cancel();
    clearResults();
    setConnectome(null);
    setPatientId(id);
    const available = patients.find((p) => p.id === id)?.available_atlases;
    if (available?.length && !available.includes(atlasId))
      setAtlasId(available[0]);
  }
  function changeAtlas(id: string) {
    cancel();
    clearResults();
    setConnectome(null);
    setAtlasId(id);
  }
  async function run<T>(
    label: string,
    action: (signal: AbortSignal) => Promise<T>,
    save: (result: T) => void,
  ) {
    cancel();
    const ac = new AbortController();
    controller.current = ac;
    const current = generation.current;
    setBusy(label);
    setError("");
    try {
      const result = await action(ac.signal);
      if (generation.current === current) save(result);
    } catch (e) {
      if (
        generation.current === current &&
        e instanceof Error &&
        e.name !== "AbortError"
      )
        setError(e.message);
    } finally {
      if (generation.current === current) {
        setBusy("");
        setJob(null);
        controller.current = null;
      }
    }
  }
  async function ensureScenario(signal: AbortSignal) {
    if (scenario) return scenario;
    const created = await post<Scenario>(
      "/scenarios",
      {
        patient_id: patientId,
        atlas_id: atlasId,
        label: `Virtual resection · ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`,
        method,
        regions,
      },
      signal,
    );
    if (!signal.aborted) {
      setScenario(created);
      setScenarios((s) => [created, ...s]);
    }
    return created;
  }
  function simulate() {
    return run(
      "Simulating resection",
      async (signal) => {
        const s = await ensureScenario(signal);
        return poll(
          await post<Job<Simulation>>(
            `/scenarios/${s.id}/simulate`,
            undefined,
            signal,
          ),
          setJob,
          signal,
        );
      },
      setSimulation,
    );
  }
  function predict() {
    return run(
      "Estimating synthetic outcome",
      async (signal) => {
        const s = await ensureScenario(signal);
        return poll(
          await post<Job<Prediction>>(
            `/scenarios/${s.id}/predict`,
            undefined,
            signal,
          ),
          setJob,
          signal,
        );
      },
      setPrediction,
    );
  }
  function analyzeSensitivity() {
    return run(
      "Testing resection boundaries",
      async (signal) => {
        const s = await ensureScenario(signal);
        return poll(
          await post<Job<Sensitivity>>(
            `/scenarios/${s.id}/sensitivity`,
            undefined,
            signal,
          ),
          setJob,
          signal,
        );
      },
      setSensitivity,
    );
  }
  function analyzeCounterfactuals(
    coverage: number,
    protected_regions: number[],
  ) {
    return run(
      "Searching constrained alternatives",
      async (signal) => {
        const s = await ensureScenario(signal);
        return poll(
          await post<Job<Counterfactual>>(
            `/scenarios/${s.id}/counterfactuals`,
            {
              minimum_target_coverage: coverage,
              protected_regions,
              max_candidates: 5,
            },
            signal,
          ),
          setJob,
          signal,
        );
      },
      setCounterfactual,
    );
  }
  async function loadScenario(s: Scenario) {
    if (s.atlas_id !== atlasId) return;
    cancel();
    clearResults();
    setScenario(s);
    setRegions(s.regions);
    setMethodState(s.method);
    setError("");
    const ac = new AbortController();
    controller.current = ac;
    try {
      setSimulation(
        await api<Simulation>(`/scenarios/${s.id}/simulation`, {
          signal: ac.signal,
        }),
      );
    } catch (e) {
      if (
        e instanceof Error &&
        e.name !== "AbortError" &&
        !("status" in e && e.status === 404)
      )
        setError(e.message);
    }
  }
  return {
    patients,
    atlases,
    patientId,
    atlasId,
    patient: patients.find((p) => p.id === patientId),
    connectome,
    regions,
    method,
    scenario,
    scenarios: scenarios.filter((s) => s.atlas_id === atlasId),
    simulation,
    prediction,
    sensitivity,
    counterfactual,
    error,
    loading,
    busy,
    job,
    setError,
    changePatient,
    changeAtlas,
    editRegions,
    setMethod,
    simulate,
    predict,
    analyzeSensitivity,
    analyzeCounterfactuals,
    loadScenario,
    retry: () => setReload((r) => r + 1),
  };
}
export type WorkspaceState = ReturnType<typeof useWorkspace>;
