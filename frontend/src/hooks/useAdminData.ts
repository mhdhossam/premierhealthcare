/**
 * hooks/useAdminData.ts
 *
 * Hooks for schema loading, list fetching, and single-record fetching.
 * All hooks return { data, isLoading, error, refetch }.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { schemaApi, crudApi, type ModelSchema, type PaginatedResponse, type ListParams } from "../api/admin";
import { ApiError } from "../api/client";

interface AsyncState<T> {
  data: T | null;
  isLoading: boolean;
  error: string | null;
}

// ─── useSchema ────────────────────────────────────────────────────────────

export function useSchema(modelName: string | undefined) {
  const [state, setState] = useState<AsyncState<ModelSchema>>({
    data: null,
    isLoading: true,
    error: null,
  });

  const load = useCallback(async () => {
    if (!modelName) return;
    setState({ data: null, isLoading: true, error: null });
    try {
      const schema = await schemaApi.getSchema(modelName);
      setState({ data: schema, isLoading: false, error: null });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Failed to load schema";
      setState({ data: null, isLoading: false, error: msg });
    }
  }, [modelName]);

  useEffect(() => { load(); }, [load]);

  return { ...state, refetch: load };
}

// ─── useSchemaListing ─────────────────────────────────────────────────────

export function useSchemaListing() {
  const [state, setState] = useState<AsyncState<Array<{
    name: string; endpoint: string; label: string; url: string;
  }>>>({ data: null, isLoading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    schemaApi.listing()
      .then((schemas) => {
        if (!cancelled) setState({ data: schemas, isLoading: false, error: null });
      })
      .catch((e) => {
        if (!cancelled) {
          const msg = e instanceof ApiError ? e.message : "Failed to load navigation";
          setState({ data: null, isLoading: false, error: msg });
        }
      });
    return () => { cancelled = true; };
  }, []);

  return state;
}

// ─── useList ──────────────────────────────────────────────────────────────

interface UseListOptions extends ListParams {
  enabled?: boolean;
}

export function useList<T = Record<string, unknown>>(
  endpoint: string | undefined,
  params: UseListOptions = {}
) {
  const { enabled = true, ...listParams } = params;
  const [state, setState] = useState<AsyncState<PaginatedResponse<T>>>({
    data: null,
    isLoading: true,
    error: null,
  });

  // Stable serialization of params for dependency array
  const paramsRef = useRef(listParams);
  paramsRef.current = listParams;

  const load = useCallback(async () => {
    if (!endpoint || !enabled) return;
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const data = await crudApi.list<T>(endpoint, paramsRef.current);
      setState({ data, isLoading: false, error: null });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Failed to load data";
      setState({ data: null, isLoading: false, error: msg });
    }
  }, [endpoint, enabled, JSON.stringify(listParams)]); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  return { ...state, refetch: load };
}

// ─── useRecord ────────────────────────────────────────────────────────────

export function useRecord<T = Record<string, unknown>>(
  endpoint: string | undefined,
  id: number | string | undefined
) {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    isLoading: true,
    error: null,
  });

  const load = useCallback(async () => {
    if (!endpoint || !id) return;
    setState({ data: null, isLoading: true, error: null });
    try {
      const data = await crudApi.get<T>(endpoint, id);
      setState({ data, isLoading: false, error: null });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Failed to load record";
      setState({ data: null, isLoading: false, error: msg });
    }
  }, [endpoint, id]);

  useEffect(() => { load(); }, [load]);

  return { ...state, refetch: load };
}