import { useEffect, useId, useState } from "react";
import { keychain } from "../api/keychain";
import { PROVIDERS, getProvider, isKnownModel, normalizeProviderId } from "../config/providers";
import { useDraft } from "../hooks/useDraft";

const CUSTOM = "__custom__";

const selectClass =
  "w-full bg-studio-800 text-studio-100 border border-line-strong rounded-md px-2.5 py-1.5 text-xs focus:outline-none focus:border-accent-500 transition-colors";
const labelClass = "block text-2xs font-mono uppercase tracking-wider text-studio-400";

interface ModelPickerProps {
  provider: string | null | undefined;
  model: string | null | undefined;
  onChange: (patch: { provider?: string; model?: string }) => void;
}

function CustomModelInput({
  value,
  placeholder,
  onCommit,
  id,
}: {
  value: string;
  placeholder: string;
  onCommit: (next: string) => void;
  id: string;
}) {
  const draft = useDraft(value, onCommit);
  return (
    <input
      id={id}
      type="text"
      spellCheck={false}
      autoComplete="off"
      value={draft.value}
      onChange={(e) => draft.onChange(e.target.value.trim())}
      onBlur={draft.flush}
      placeholder={placeholder}
      className={`${selectClass} font-mono placeholder:text-studio-500`}
    />
  );
}

/** Whether a key is stored for this provider's slot (null while loading). */
function useHasKey(keyId: string | undefined, needsKey: boolean): boolean | null {
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  useEffect(() => {
    if (!keyId || !needsKey) {
      setHasKey(true);
      return;
    }
    let cancelled = false;
    setHasKey(null);
    keychain
      .status(keyId)
      .then((value) => !cancelled && setHasKey(value.saved))
      .catch(() => !cancelled && setHasKey(null));
    return () => {
      cancelled = true;
    };
  }, [keyId, needsKey]);
  return hasKey;
}

export function ModelPicker({ provider, model, onChange }: ModelPickerProps) {
  const uid = useId();
  const info = getProvider(provider);
  const providerId = normalizeProviderId(provider);
  const currentModel = model ?? "";
  const [forceCustom, setForceCustom] = useState(false);

  useEffect(() => setForceCustom(false), [providerId]);

  const isCustom = forceCustom || !info || (!!currentModel && !isKnownModel(providerId, currentModel));
  const hasKey = useHasKey(info?.keyId, info?.needsKey ?? false);

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <label htmlFor={`${uid}-provider`} className={labelClass}>
          LLM Provider
        </label>
        <select
          id={`${uid}-provider`}
          value={providerId}
          onChange={(e) => {
            const next = getProvider(e.target.value);
            onChange({ provider: e.target.value, model: next?.defaultModel ?? "" });
          }}
          className={selectClass}
        >
          {!info && <option value={providerId}>{providerId} (custom)</option>}
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <label htmlFor={`${uid}-model`} className={labelClass}>
          Chat Model
        </label>
        <select
          id={`${uid}-model`}
          value={isCustom ? CUSTOM : currentModel}
          onChange={(e) => {
            if (e.target.value === CUSTOM) {
              setForceCustom(true);
            } else {
              setForceCustom(false);
              onChange({ model: e.target.value });
            }
          }}
          className={`${selectClass} font-mono`}
        >
          {(info?.models ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
          <option value={CUSTOM}>Custom model ID…</option>
        </select>

        {isCustom && (
          <>
            <CustomModelInput
              key={`${providerId}-custom`}
              id={`${uid}-custom`}
              value={currentModel}
              placeholder={info?.customPlaceholder ?? "model id"}
              onCommit={(next) => onChange({ model: next })}
            />
            <p className="text-2xs leading-relaxed text-studio-500">
              Any model your provider offers works here. It is sent as{" "}
              <span className="font-mono text-studio-400">
                {providerId}/{currentModel || "…"}
              </span>
              .
            </p>
          </>
        )}

        {info?.needsKey && hasKey === false && (
          <p role="note" className="rounded border border-amber-900/50 bg-amber-950/30 px-2 py-1.5 text-2xs leading-relaxed text-amber-300">
            No {info.label} API key saved yet. Add one in Provider settings or runs with this agent will fail.
          </p>
        )}
      </div>
    </div>
  );
}
