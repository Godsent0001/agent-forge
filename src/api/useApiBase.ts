import { useEffect, useState } from "react";
import { getApiBase } from "./client";

export function useApiBase(): string | null {
  const [base, setBase] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    getApiBase().then((value) => {
      if (active) setBase(value);
    }).catch(() => {
      if (active) setBase(null);
    });
    return () => { active = false; };
  }, []);
  return base;
}
