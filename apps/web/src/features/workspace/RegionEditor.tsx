"use client";
import { useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Circle,
  Search,
  X,
} from "lucide-react";
import { NETWORK_COLORS } from "@/features/brain/BrainScene";
import { Spinner } from "./primitives";
import type { WorkspaceState } from "./useWorkspace";
export function RegionEditor({
  state,
  onHover,
}: {
  state: WorkspaceState;
  onHover: (id: number | null) => void;
}) {
  const [query, setQuery] = useState(""),
    [listOpen, setListOpen] = useState(false);
  const { connectome, regions, busy, loading, editRegions } = state;
  const selected = useMemo(
    () => new Map(regions.map((r) => [r.region_id, r.fraction_removed])),
    [regions],
  );
  const filtered =
    connectome?.nodes.filter((n) =>
      `${n.name} ${n.network}`.toLowerCase().includes(query.toLowerCase()),
    ) || [];
  const change = (id: number, fraction: number) =>
    editRegions([
      ...regions.filter((r) => r.region_id !== id),
      { region_id: id, fraction_removed: fraction },
    ]);
  return (
    <section className="resection-panel panel" aria-label="Resection editor">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">SCENARIO BUILDER</span>
          <h2>Virtual resection</h2>
        </div>
        <span className="count-badge">
          {regions.length.toString().padStart(2, "0")}
        </span>
      </div>
      <p className="panel-description">
        Define a resection. Observe what changes across the network.
      </p>
      <div
        className="method-selector"
        role="group"
        aria-label="Resection method"
      >
        <button
          className={state.method === "weighted" ? "active" : ""}
          onClick={() => state.setMethod("weighted")}
        >
          Weighted
        </button>
        <button
          className={state.method === "binary" ? "active" : ""}
          onClick={() => state.setMethod("binary")}
        >
          Binary
        </button>
      </div>
      <div className="small-note">
        {state.method === "weighted"
          ? "Connection weights scale with the fraction removed."
          : "Fractions of 50% or more remove all incident connections."}
      </div>
      <div className="selected-heading">
        <span>SELECTED REGIONS</span>
        <button
          className="text-button"
          disabled={!regions.length}
          onClick={() => editRegions([])}
        >
          Clear
        </button>
      </div>
      <div className="selected-regions">
        {!regions.length && (
          <div className="selection-empty">
            Click a brain node or browse the atlas below to add a region.
          </div>
        )}
        {regions.map((r) => {
          const node = connectome?.nodes.find((n) => n.id === r.region_id);
          if (!node) return null;
          return (
            <div
              className="region-row"
              key={r.region_id}
              onMouseEnter={() => onHover(r.region_id)}
              onMouseLeave={() => onHover(null)}
            >
              <div className="region-name">
                <span
                  className="region-dot"
                  style={{
                    background: NETWORK_COLORS[node.network] || "#69c5b0",
                  }}
                />
                <label htmlFor={`fraction-${r.region_id}`}>{node.name}</label>
                <button
                  className="icon-button"
                  aria-label={`Remove ${node.name}`}
                  onClick={() =>
                    editRegions(
                      regions.filter(
                        (region) => region.region_id !== r.region_id,
                      ),
                    )
                  }
                >
                  <X size={12} />
                </button>
              </div>
              <div className="fraction-row">
                <input
                  id={`fraction-${r.region_id}`}
                  aria-label={`${node.name} fraction removed`}
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={Math.round(r.fraction_removed * 100)}
                  onChange={(e) =>
                    change(r.region_id, Number(e.target.value) / 100)
                  }
                />
                <output>
                  {Math.round(r.fraction_removed * 100)}
                  <span>%</span>
                </output>
              </div>
            </div>
          );
        })}
      </div>
      <button
        className="browse-button"
        aria-expanded={listOpen}
        onClick={() => setListOpen(!listOpen)}
      >
        <Circle size={13} />
        Browse all {connectome?.nodes.length || "atlas"} regions
        <ChevronDown size={14} className={listOpen ? "rotated" : ""} />
      </button>
      {listOpen && (
        <div className="region-browser">
          <label className="search-box">
            <Search size={14} />
            <input
              aria-label="Search atlas regions"
              placeholder="Search region or network…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="region-options">
            {filtered.map((n) => (
              <button
                key={n.id}
                className={selected.has(n.id) ? "selected" : ""}
                aria-pressed={selected.has(n.id)}
                onClick={() =>
                  selected.has(n.id)
                    ? editRegions(regions.filter((r) => r.region_id !== n.id))
                    : change(n.id, 0.5)
                }
              >
                <span>
                  {n.name}
                  <small>{n.network.replaceAll("-", " ")}</small>
                </span>
                {selected.has(n.id) ? (
                  <Check size={13} />
                ) : (
                  <span className="plus">+</span>
                )}
              </button>
            ))}
            {!filtered.length && (
              <p className="small-note">No matching regions.</p>
            )}
          </div>
        </div>
      )}
      <div className="editor-footer">
        <button
          className="primary-button"
          disabled={!connectome || loading || !!busy}
          onClick={state.simulate}
        >
          {busy ? (
            <Spinner label={busy} />
          ) : (
            <>
              Simulate resection
              <ArrowRight size={16} />
            </>
          )}
        </button>
        <div className="small-note centered">
          {regions.length
            ? `${regions.length} regions · ${state.method} disconnection`
            : "No regions selected · baseline simulation"}
        </div>
      </div>
    </section>
  );
}
