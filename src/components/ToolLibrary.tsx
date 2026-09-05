import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import { ToolCatalogModal } from "./ToolCatalogModal";
import type { CatalogToolEntry } from "../types";

export function ToolLibrary() {
  const tools = useStore((s) => s.tools);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [catalogByKind, setCatalogByKind] = useState<Record<string, CatalogToolEntry>>({});

  useEffect(() => {
    api.catalog.list().then((entries) => {
      setCatalogByKind(Object.fromEntries(entries.map((e) => [e.kind, e])));
    });
  }, []);

  return (
    <div className="border-t border-white/5 p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          Tool Library
        </h3>
        <button
          onClick={() => setCatalogOpen(true)}
          className="text-xs text-accent-400 hover:text-accent-300 transition-colors duration-150"
        >
          + Browse
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {tools.map((t) => {
          const shelf = catalogByKind[t.kind]?.shelf;
          return (
            <span
              key={t.id}
              title={shelf ? `Shelf: ${shelf}` : t.kind}
              className="text-xs px-2 py-1 rounded-full bg-surface-800 text-neutral-400"
            >
              🔧 {t.name}
            </span>
          );
        })}
        {tools.length === 0 && (
          <p className="text-xs text-neutral-600">No tools yet — browse the catalog to add some.</p>
        )}
      </div>

      {catalogOpen && <ToolCatalogModal onClose={() => setCatalogOpen(false)} />}
    </div>
  );
}
