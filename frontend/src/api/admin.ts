/**
 * api/admin.ts
 *
 * Typed wrappers for all admin API endpoints:
 *   - Auth (login/logout)
 *   - Schema registry (list + detail)
 *   - Dynamic CRUD (list, get, create, update, delete)
 */
import { api, tokenStorage, ApiError } from "./client";

// ─── TypeScript interfaces ────────────────────────────────────────────────

export interface SchemaFieldChoice {
  value: string | number;
  label: string;
}

export interface SchemaField {
  name: string;
  type:
    | "string"
    | "text"
    | "number"
    | "boolean"
    | "datetime"
    | "date"
    | "time"
    | "email"
    | "url"
    | "file"
    | "select"
    | "relation";
  label: string;
  read_only: boolean;
  required: boolean;
  nullable: boolean;
  help_text?: string;
  max_length?: number;
  min_value?: number;
  max_value?: number;
  choices?: SchemaFieldChoice[];
  related_model?: string;
  related_endpoint?: string;
  show_in_list: boolean;
  sortable: boolean;
  searchable: boolean;
}

export interface ModelSchema {
  name: string;
  endpoint: string;
  list_display: string[];
  search_fields: string[];
  ordering: string[];
  fields: SchemaField[];
}

export interface SchemaListing {
  name: string;
  endpoint: string;
  label: string;
  url: string;
}

export interface PaginatedResponse<T> {
  count: number;
  total_pages: number;
  current_page: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: {
    id: number;
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    is_staff: boolean;
    is_superuser: boolean;
  };
}

export interface ListParams {
  page?: number;
  page_size?: number;
  search?: string;
  ordering?: string;
  [key: string]: string | number | boolean | undefined;
}

// ─── Auth API ─────────────────────────────────────────────────────────────

export const authApi = {
  async login(username: string, password: string): Promise<LoginResponse> {
    const data = await api.post<LoginResponse>("/api/auth/login/", {
      username,
      password,
    });
    tokenStorage.set(data.access, data.refresh);
    return data;
  },

  async logout(): Promise<void> {
    const refresh = tokenStorage.getRefresh();
    if (refresh) {
      try {
        await api.post("/api/auth/logout/", { refresh });
      } catch {
        // Swallow — blacklist best-effort
      }
    }
    tokenStorage.clear();
  },

  async verify(): Promise<boolean> {
    const access = tokenStorage.getAccess();
    if (!access) return false;
    try {
      await api.post("/api/auth/verify/", { token: access });
      return true;
    } catch {
      return false;
    }
  },
};

// ─── Schema API ───────────────────────────────────────────────────────────

const schemaCache = new Map<string, ModelSchema>();
const listingCache = { data: null as SchemaListing[] | null, ts: 0 };
const CACHE_TTL_MS = 60_000; // 1 minute

export const schemaApi = {
  async listing(): Promise<SchemaListing[]> {
    const now = Date.now();
    if (listingCache.data && now - listingCache.ts < CACHE_TTL_MS) {
      return listingCache.data;
    }
    const res = await api.get<{ schemas: SchemaListing[] }>("/api/schema/");
    listingCache.data = res.schemas;
    listingCache.ts = now;
    return res.schemas;
  },

  async getSchema(modelName: string): Promise<ModelSchema> {
    const cached = schemaCache.get(modelName.toLowerCase());
    if (cached) return cached;

    const schema = await api.get<ModelSchema>(
      `/api/schema/${modelName}/`
    );
    schemaCache.set(modelName.toLowerCase(), schema);
    return schema;
  },

  invalidate(modelName?: string) {
    if (modelName) {
      schemaCache.delete(modelName.toLowerCase());
    } else {
      schemaCache.clear();
      listingCache.data = null;
    }
  },
};

// ─── Dynamic CRUD API ─────────────────────────────────────────────────────

export const crudApi = {
  list<T = Record<string, unknown>>(
    endpoint: string,
    params: ListParams = {}
  ): Promise<PaginatedResponse<T>> {
    return api.get<PaginatedResponse<T>>(endpoint, params as Record<string, string | number | boolean>);
  },

  get<T = Record<string, unknown>>(endpoint: string, id: number | string): Promise<T> {
    const url = endpoint.endsWith("/") ? `${endpoint}${id}/` : `${endpoint}/${id}/`;
    return api.get<T>(url);
  },

  create<T = Record<string, unknown>>(endpoint: string, data: unknown): Promise<T> {
    return api.post<T>(endpoint, data);
  },

  update<T = Record<string, unknown>>(
    endpoint: string,
    id: number | string,
    data: unknown
  ): Promise<T> {
    const url = endpoint.endsWith("/") ? `${endpoint}${id}/` : `${endpoint}/${id}/`;
    return api.patch<T>(url, data);
  },

  delete(endpoint: string, id: number | string): Promise<null> {
    const url = endpoint.endsWith("/") ? `${endpoint}${id}/` : `${endpoint}/${id}/`;
    return api.delete<null>(url);
  },

  /**
   * Fetch options for a relation field (FK dropdown population).
   * Assumes the related endpoint supports ?page_size=200.
   */
  async fetchRelationOptions(
    relatedEndpoint: string
  ): Promise<Array<{ value: number | string; label: string }>> {
    try {
      const res = await api.get<PaginatedResponse<Record<string, unknown>>>(
        relatedEndpoint,
        { page_size: 200 }
      );
      return res.results.map((item) => ({
        value: item.id as number,
        label: (item.name ?? item.title ?? item.username ?? String(item.id)) as string,
      }));
    } catch {
      return [];
    }
  },
};