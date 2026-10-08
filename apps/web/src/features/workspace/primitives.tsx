import { ArrowUpRight, Info, LoaderCircle } from "lucide-react";
import type { Provenance } from "@/lib/types";
export function Logo({ small = false }: { small?: boolean }) {
  return (
    <div className={`brand ${small ? "small" : ""}`}>
      <svg viewBox="0 0 36 36" fill="none" aria-hidden="true">
        <path
          d="M16 5C10 2 5 8 7 13C1 17 4 24 9 25C9 31 14 33 17 29V8M20 5C26 2 31 8 29 13C35 17 32 24 27 25C27 31 22 33 19 29V8"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <path
          d="M8 13L15 17L8 24M28 13L21 17L28 24M11 8L15 10M25 8L21 10M13 27L16 23M23 27L20 23"
          stroke="currentColor"
          strokeWidth="1.3"
        />
        <circle cx="15" cy="17" r="2.3" fill="currentColor" />
        <circle cx="21" cy="17" r="2.3" fill="currentColor" />
      </svg>
      {!small && (
        <span>
          neuro<span>resect</span>
          <sup>LAB</sup>
        </span>
      )}
    </div>
  );
}
export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="loading-inline" role="status">
      <LoaderCircle size={15} className="spin" />
      {label}
    </span>
  );
}
export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <div className="eyebrow">{children}</div>;
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-symbol">
        <Info size={20} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function ProvenanceDetails({
  provenance,
  label = "View reproducibility record",
}: {
  provenance: Provenance;
  label?: string;
}) {
  return (
    <details className="provenance">
      <summary>
        {label}
        <ArrowUpRight size={13} />
      </summary>
      <pre>{JSON.stringify(provenance, null, 2)}</pre>
    </details>
  );
}
