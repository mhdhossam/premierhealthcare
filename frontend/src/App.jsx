import { useState, useEffect, useCallback, useRef, createContext, useContext } from "react";

// ─── Config ──────────────────────────────────────────────────────────────
const BASE_URL = "http://localhost:8000";
const TOKEN_KEY = "admin_access";
const REFRESH_KEY = "admin_refresh";

// ─── Token Storage ────────────────────────────────────────────────────────
const tokenStorage = {
  getAccess:  () => localStorage.getItem(TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (a, r) => {
    localStorage.setItem(TOKEN_KEY, a);
    localStorage.setItem(REFRESH_KEY, r);
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem("admin_user");
  },
};

// ─── API Client ───────────────────────────────────────────────────────────
class ApiError extends Error {
  constructor(status, data) {
    super(data?.detail ?? data?.error ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

let refreshPromise = null;
async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const refresh = tokenStorage.getRefresh();
    if (!refresh) throw new ApiError(401, { detail: "No refresh token" });
    const res = await fetch(`${BASE_URL}/api/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) { tokenStorage.clear(); throw new ApiError(401, {}); }
    const data = await res.json();
    tokenStorage.set(data.access, data.refresh ?? refresh);
    return data.access;
  })().finally(() => { refreshPromise = null; });
  return refreshPromise;
}

async function apiFetch(path, options = {}, _retry = true) {
  const { params, ...init } = options;
  let url = `${BASE_URL}${path}`;
  if (params) {
    const qs = new URLSearchParams(
      Object.fromEntries(
        Object.entries(params)
          .filter(([, v]) => v != null)
          .map(([k, v]) => [k, String(v)])
      )
    );
    if (qs.toString()) url += `?${qs}`;
  }
  const access = tokenStorage.getAccess();
  const headers = new Headers(init.headers);
  // Don't force Content-Type for FormData — browser sets it with the boundary
  if (!headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (access) headers.set("Authorization", `Bearer ${access}`);

  const res = await fetch(url, { ...init, headers });

  if (res.status === 401 && _retry) {
    try {
      const t = await refreshAccessToken();
      headers.set("Authorization", `Bearer ${t}`);
      return apiFetch(path, options, false);
    } catch {
      throw new ApiError(401, { detail: "Session expired." });
    }
  }
  if (!res.ok) {
    let d = {};
    try { d = await res.json(); } catch { d = { detail: res.statusText }; }
    throw new ApiError(res.status, d);
  }
  if (res.status === 204) return null;
  return res.json();
}

const api = {
  get:    (path, params)  => apiFetch(path, { method: "GET", params }),
  post:   (path, body)    => apiFetch(path, { method: "POST",   body: JSON.stringify(body) }),
  patch:  (path, body)    => apiFetch(path, { method: "PATCH",  body: JSON.stringify(body) }),
  delete: (path)          => apiFetch(path, { method: "DELETE" }),
  // FormData upload — no JSON stringify, no Content-Type override
  upload: (path, formData) => apiFetch(path, { method: "POST", body: formData }),
};

// ─── Schema Cache ─────────────────────────────────────────────────────────
const schemaCache = new Map();
const schemaApi = {
  async listing() {
    const r = await api.get("/api/schema/");
    return r.schemas;
  },
  async getSchema(name) {
    if (schemaCache.has(name)) return schemaCache.get(name);
    const s = await api.get(`/api/schema/${name}/`);
    schemaCache.set(name, s);
    return s;
  },
};

const crudApi = {
  list:   (ep, p = {}) => api.get(ep, p),
  get:    (ep, id)     => api.get(`${ep}${id}/`),
  create: (ep, d)      => api.post(ep, d),
  update: (ep, id, d)  => api.patch(`${ep}${id}/`, d),
  delete: (ep, id)     => api.delete(`${ep}${id}/`),
};

// ─── Auth Context ─────────────────────────────────────────────────────────
const AuthContext = createContext(null);
function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const stored = localStorage.getItem("admin_user");
    if (stored && tokenStorage.getAccess()) {
      try { setUser(JSON.parse(stored)); } catch { tokenStorage.clear(); }
    }
    setLoading(false);
  }, []);
  const login = async (username, password) => {
    const data = await api.post("/api/auth/login/", { username, password });
    tokenStorage.set(data.access, data.refresh);
    setUser(data.user);
    localStorage.setItem("admin_user", JSON.stringify(data.user));
  };
  const logout = async () => {
    const refresh = tokenStorage.getRefresh();
    if (refresh) try { await api.post("/api/auth/logout/", { refresh }); } catch {}
    tokenStorage.clear();
    setUser(null);
  };
  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
const useAuth = () => useContext(AuthContext);

// ─── Router ───────────────────────────────────────────────────────────────
function useRoute() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const handle = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handle);
    return () => window.removeEventListener("popstate", handle);
  }, []);
  return path;
}
function navigate(to) {
  window.history.pushState({}, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

// ─── Icons ────────────────────────────────────────────────────────────────
const Icon = {
  chevronRight: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={14} height={14}><path d="M9 18l6-6-6-6"/></svg>,
  search:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={16} height={16}><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>,
  plus:    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={16} height={16}><path d="M12 5v14M5 12h14"/></svg>,
  edit:    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={14} height={14}><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>,
  trash:   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={14} height={14}><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>,
  logout:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={16} height={16}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>,
  db:      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={18} height={18}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>,
  check:   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} width={14} height={14}><polyline points="20 6 9 17 4 12"/></svg>,
  x:       <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={14} height={14}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>,
  spinner: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={20} height={20} style={{animation:"spin 0.8s linear infinite"}}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>,
  home:    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={16} height={16}><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
  upload:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={16} height={16}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>,
  download:<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={14} height={14}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>,
  file:    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={16} height={16}><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>,
};

// ─── Login Page ───────────────────────────────────────────────────────────
function LoginPage() {
  const { login } = useAuth();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError("");
    try { await login(form.username, form.password); navigate("/admin"); }
    catch (err) { setError(err.message || "Invalid credentials"); }
    finally { setLoading(false); }
  };
  return (
    <div style={S.loginWrap}>
      <div style={S.loginCard}>
        <div style={S.loginLogo}>
          <span style={S.logoIcon}>{Icon.db}</span>
          <span style={S.logoText}>NEXUS ADMIN</span>
        </div>
        <p style={S.loginSub}>Headless Django Admin Panel</p>
        <form onSubmit={submit} style={{ display:"flex", flexDirection:"column", gap:12 }}>
          <label style={S.label}>Username</label>
          <input style={S.input} type="text" autoFocus placeholder="admin" value={form.username}
            onChange={e => setForm(f => ({...f, username: e.target.value}))} required />
          <label style={S.label}>Password</label>
          <input style={S.input} type="password" placeholder="••••••••" value={form.password}
            onChange={e => setForm(f => ({...f, password: e.target.value}))} required />
          {error && <div style={S.errorBanner}>{error}</div>}
          <button style={{...S.btn, ...S.btnPrimary, marginTop:8}} type="submit" disabled={loading}>
            {loading
              ? <span style={{display:"flex",alignItems:"center",gap:8,justifyContent:"center"}}>{Icon.spinner} Authenticating…</span>
              : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── Sidebar ──────────────────────────────────────────────────────────────
function Sidebar({ schemas, currentModel }) {
  const { user, logout } = useAuth();
  const path = useRoute();
  return (
    <aside style={S.sidebar}>
      <div style={S.sidebarHeader}>
        <span style={S.sidebarLogoIcon}>{Icon.db}</span>
        <span style={S.sidebarLogoText}>NEXUS</span>
      </div>
      <div style={S.sidebarSection}>
        <div style={S.sidebarSectionLabel}>Navigation</div>
        <button style={{...S.navItem, ...(path==="/admin" ? S.navItemActive : {})}} onClick={() => navigate("/admin")}>
          {Icon.home}<span>Dashboard</span>
        </button>
        {/* Files link — always visible, not schema-driven */}
        <button
          style={{...S.navItem, ...(path==="/admin/files" ? S.navItemActive : {})}}
          onClick={() => navigate("/admin/files")}
        >
          {Icon.file}<span>Files</span>
          {path==="/admin/files" && <span style={{marginLeft:"auto",opacity:.5}}>{Icon.chevronRight}</span>}
        </button>
      </div>
      <div style={S.sidebarSection}>
        <div style={S.sidebarSectionLabel}>Models</div>
        {schemas?.map(s => {
          const active = currentModel?.toLowerCase() === s.label.toLowerCase();
          return (
            <button key={s.name} style={{...S.navItem, ...(active ? S.navItemActive : {})}}
              onClick={() => navigate(`/admin/${s.label.toLowerCase()}`)}>
              <span style={S.navDot} />
              <span>{s.label}</span>
              {active && <span style={{marginLeft:"auto",opacity:.5}}>{Icon.chevronRight}</span>}
            </button>
          );
        })}
      </div>
      <div style={S.sidebarFooter}>
        <div style={S.userBadge}>
          <div style={S.userAvatar}>{user?.username?.[0]?.toUpperCase()}</div>
          <div style={{flex:1,overflow:"hidden"}}>
            <div style={S.userName}>{user?.username}</div>
            <div style={S.userRole}>{user?.is_superuser ? "Superuser" : "Staff"}</div>
          </div>
        </div>
        <button style={S.logoutBtn} onClick={logout} title="Logout">{Icon.logout}</button>
      </div>
    </aside>
  );
}

// ─── Toast ────────────────────────────────────────────────────────────────
function useToast() {
  const [toast, setToast] = useState(null);
  const show = useCallback((msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  }, []);
  return { toast, show };
}
function Toast({ toast }) {
  if (!toast) return null;
  const colors = { success:"#22d3ee", error:"#f87171", info:"#a78bfa" };
  return (
    <div style={{...S.toast, borderLeftColor: colors[toast.type] ?? colors.info}}>
      {toast.msg}
    </div>
  );
}

// ─── Files Page ───────────────────────────────────────────────────────────
const FILE_EXT_COLORS = {
  pdf:  "#f87171", doc:"#60a5fa", docx:"#60a5fa",
  xls:  "#4ade80", xlsx:"#4ade80", csv:"#4ade80",
  png:  "#c084fc", jpg:"#c084fc", jpeg:"#c084fc", gif:"#c084fc", webp:"#c084fc", svg:"#c084fc",
  mp4:  "#fb923c", mp3:"#fb923c", mov:"#fb923c",
  zip:  "#fbbf24", rar:"#fbbf24", "7z":"#fbbf24",
  txt:  "#94a3b8", md:"#94a3b8",
};

function FileExtBadge({ ext }) {
  const color = FILE_EXT_COLORS[ext?.toLowerCase()] ?? "#64748b";
  return (
    <span style={{
      background: color + "18",
      color,
      padding:"2px 7px",
      borderRadius:4,
      fontSize:11,
      fontWeight:700,
      fontFamily:"'JetBrains Mono',monospace",
      letterSpacing:.5,
      textTransform:"uppercase",
    }}>
      {ext || "—"}
    </span>
  );
}

function DropZone({ onFiles, uploading }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length) onFiles(files);
  };

  return (
    <div
      style={{
        ...S.dropZone,
        ...(dragging ? S.dropZoneActive : {}),
        ...(uploading ? { opacity:.5, pointerEvents:"none" } : {}),
      }}
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        style={{ display:"none" }}
        onChange={e => {
          const files = Array.from(e.target.files);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />
      <div style={S.dropZoneIcon}>{uploading ? Icon.spinner : Icon.upload}</div>
      <div style={S.dropZoneText}>
        {uploading ? "Uploading…" : "Drop files here or click to browse"}
      </div>
      <div style={S.dropZoneSub}>Any file type · Multiple files supported</div>
    </div>
  );
}

function FilesPage() {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(null); // file id being deleted
  const [search, setSearch] = useState("");
  const { toast, show: showToast } = useToast();

  const loadFiles = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/api/files/");
      setFiles(data);
    } catch (e) {
      showToast(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadFiles(); }, [loadFiles]);

  const handleUpload = async (fileList) => {
    setUploading(true);
    let successCount = 0;
    for (const file of fileList) {
      try {
        const fd = new FormData();
        fd.append("file", file);
        await api.upload("/api/files/", fd);
        successCount++;
      } catch (e) {
        showToast(`Failed to upload ${file.name}: ${e.message}`, "error");
      }
    }
    if (successCount > 0) {
      showToast(
        successCount === 1
          ? "File uploaded successfully"
          : `${successCount} files uploaded`,
        "success"
      );
      await loadFiles();
    }
    setUploading(false);
  };

  const handleDelete = async (file) => {
    if (!window.confirm(`Delete "${file.original_name}"? This cannot be undone.`)) return;
    setDeleting(file.id);
    try {
      await api.delete(`/api/files/${file.id}/`);
      showToast("File deleted", "info");
      setFiles(prev => prev.filter(f => f.id !== file.id));
    } catch (e) {
      showToast(e.message, "error");
    } finally {
      setDeleting(null);
    }
  };

  const filtered = files.filter(f =>
    f.original_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={S.pageWrap}>
      <Toast toast={toast} />

      {/* Header */}
      <div style={S.pageHeader}>
        <div>
          <div style={S.breadcrumb}>
            <span style={{opacity:.5}}>Admin</span>
            <span style={{opacity:.35,margin:"0 6px"}}>/</span>
            <span>Files</span>
          </div>
          <h1 style={S.pageTitle}>Files</h1>
          <div style={S.pageSubtitle}>{files.length} total files</div>
        </div>
      </div>

      {/* Drop zone */}
      <DropZone onFiles={handleUpload} uploading={uploading} />

      {/* Search */}
      <div style={{...S.toolbar, marginTop:16}}>
        <div style={S.searchWrap}>
          <span style={S.searchIcon}>{Icon.search}</span>
          <input
            style={S.searchInput}
            placeholder="Search files…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div style={S.tableLoadingWrap}>{Icon.spinner}<span style={{marginLeft:12,opacity:.6}}>Loading files…</span></div>
      ) : (
        <div style={S.tableWrap}>
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>Name</th>
                <th style={S.th}>Type</th>
                <th style={S.th}>Size</th>
                <th style={S.th}>Uploaded</th>
                <th style={{...S.th, width:100, textAlign:"right"}}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={5} style={S.emptyCell}>
                    {search ? "No files match your search" : "No files uploaded yet"}
                  </td>
                </tr>
              )}
              {filtered.map(file => (
                <tr key={file.id} style={S.tr}>
                  <td style={S.td}>
                    <div style={{display:"flex",alignItems:"center",gap:8}}>
                      <span style={{color:"#475569",display:"flex"}}>{Icon.file}</span>
                      <span style={{color:"#e2e8f0",fontWeight:500}}>{file.original_name}</span>
                    </div>
                  </td>
                  <td style={S.td}><FileExtBadge ext={file.extension} /></td>
                  <td style={{...S.td,fontFamily:"'JetBrains Mono',monospace",fontSize:12,opacity:.7}}>
                    {file.size_display}
                  </td>
                  <td style={{...S.td,fontFamily:"'JetBrains Mono',monospace",fontSize:12,opacity:.7}}>
                    {new Date(file.created_at).toLocaleString()}
                  </td>
                  <td style={{...S.td,textAlign:"right"}}>
                    <a
                      href={file.url}
                      target="_blank"
                      rel="noreferrer"
                      style={{...S.actionBtn, textDecoration:"none", display:"inline-flex", alignItems:"center"}}
                      title="Download"
                    >
                      {Icon.download}
                    </a>
                    <button
                      style={{...S.actionBtn, ...S.actionBtnDanger}}
                      onClick={() => handleDelete(file)}
                      disabled={deleting === file.id}
                      title="Delete"
                    >
                      {deleting === file.id ? Icon.spinner : Icon.trash}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Dynamic Table ────────────────────────────────────────────────────────
function DynamicTable({ schema, data, onEdit, onDelete, loading }) {
  const listFields = schema.fields.filter(f => schema.list_display.includes(f.name));

  function renderCell(field, value) {
    if (value == null) return <span style={{opacity:.35}}>—</span>;
    if (field.type === "boolean") return value
      ? <span style={S.badge.green}>{Icon.check} Yes</span>
      : <span style={S.badge.red}>{Icon.x} No</span>;
    if (field.type === "select") {
      const choice = field.choices?.find(c => c.value === value);
      return <span style={S.badge.gray}>{choice?.label ?? value}</span>;
    }
    if (field.type === "datetime") return <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:12,opacity:.7}}>{new Date(value).toLocaleString()}</span>;
    if (field.type === "date") return <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:12,opacity:.7}}>{new Date(value).toLocaleDateString()}</span>;
    if (field.type === "number" && field.name === "price") return <span style={{fontFamily:"'JetBrains Mono',monospace"}}>${Number(value).toFixed(2)}</span>;
    return <span>{String(value)}</span>;
  }

  if (loading) return (
    <div style={S.tableLoadingWrap}>{Icon.spinner}<span style={{marginLeft:12,opacity:.6}}>Loading records…</span></div>
  );

  return (
    <div style={S.tableWrap}>
      <table style={S.table}>
        <thead>
          <tr>
            {listFields.map(f => <th key={f.name} style={S.th}>{f.label}</th>)}
            <th style={{...S.th, width:100, textAlign:"right"}}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {data?.length === 0 && (
            <tr><td colSpan={listFields.length + 1} style={S.emptyCell}>No records found</td></tr>
          )}
          {data?.map((row, i) => (
            <tr key={row.id ?? i} style={S.tr}>
              {listFields.map(f => <td key={f.name} style={S.td}>{renderCell(f, row[f.name])}</td>)}
              <td style={{...S.td, textAlign:"right"}}>
                <button style={S.actionBtn} onClick={() => onEdit(row)} title="Edit">{Icon.edit}</button>
                <button style={{...S.actionBtn, ...S.actionBtnDanger}} onClick={() => onDelete(row)} title="Delete">{Icon.trash}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Dynamic Form ─────────────────────────────────────────────────────────
function DynamicForm({ schema, initial, onSubmit, onCancel, loading }) {
  const editableFields = schema.fields.filter(f => !f.read_only);
  const [values, setValues] = useState(() => {
    const init = {};
    editableFields.forEach(f => {
      // For relation fields, extract the FK id from nested objects
      const raw = initial?.[f.name];
      init[f.name] = (raw != null && typeof raw === "object" && "id" in raw)
        ? raw.id
        : raw ?? "";
    });
    return init;
  });
  const [relationOptions, setRelationOptions] = useState({});
  const [errors, setErrors] = useState({});

  useEffect(() => {
    editableFields.forEach(async (f) => {
      if (f.type === "relation" && f.related_endpoint) {
        try {
          const res = await api.get(f.related_endpoint, { page_size: 200 });
          const opts = (res.results || []).map(item => ({
            value: item.id,
            label: item.name ?? item.title ?? item.username ?? String(item.id),
          }));
          setRelationOptions(prev => ({ ...prev, [f.name]: opts }));
        } catch {}
      }
    });
  }, [schema.name]);

  const set = (name, value) => {
    setValues(v => ({ ...v, [name]: value }));
    setErrors(e => ({ ...e, [name]: undefined }));
  };

  const validate = () => {
    const errs = {};
    editableFields.forEach(f => {
      if (f.required && !f.nullable && (values[f.name] === "" || values[f.name] == null)) {
        errs[f.name] = `${f.label} is required`;
      }
    });
    return errs;
  };

  const submit = (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }
    const payload = {};
    editableFields.forEach(f => {
      let v = values[f.name];
      if (v === "" || v == null) { payload[f.name] = null; return; }
      if (f.type === "number") v = Number(v);
      if (f.type === "boolean") v = Boolean(v);
      payload[f.name] = v;
    });
    onSubmit(payload);
  };

  function renderField(f) {
    const val = values[f.name];
    const err = errors[f.name];
    const style = { ...S.input, ...(err ? S.inputError : {}) };

    if (f.type === "boolean") return (
      <label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer"}}>
        <input type="checkbox" checked={!!val} onChange={e => set(f.name, e.target.checked)}
          style={{width:16,height:16,accentColor:"#22d3ee"}} />
        <span style={{fontSize:14,opacity:.8}}>{val ? "Enabled" : "Disabled"}</span>
      </label>
    );
    if (f.type === "select") return (
      <select style={style} value={val} onChange={e => set(f.name, e.target.value)}>
        <option value="">— Select —</option>
        {f.choices?.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>
    );
    if (f.type === "relation") {
      const opts = relationOptions[f.name] || [];
      return (
        <select style={style} value={val} onChange={e => set(f.name, e.target.value)}>
          <option value="">— None —</option>
          {opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    }
    if (f.type === "text") return (
      <textarea style={{...style, minHeight:100, resize:"vertical"}} value={val}
        onChange={e => set(f.name, e.target.value)} />
    );
    const inputType = f.type === "email" ? "email" : f.type === "url" ? "url"
      : f.type === "number" ? "number" : f.type === "datetime" ? "datetime-local"
      : f.type === "date" ? "date" : "text";
    return (
      <input style={style} type={inputType} value={val}
        onChange={e => set(f.name, e.target.value)}
        maxLength={f.max_length} required={f.required} />
    );
  }

  return (
    <form onSubmit={submit} style={S.formGrid}>
      {editableFields.map(f => (
        <div key={f.name} style={S.formField}>
          <label style={S.label}>
            {f.label}
            {f.required && <span style={{color:"#f87171",marginLeft:4}}>*</span>}
          </label>
          {renderField(f)}
          {errors[f.name] && <div style={S.fieldError}>{errors[f.name]}</div>}
          {f.help_text && <div style={S.helpText}>{f.help_text}</div>}
        </div>
      ))}
      <div style={{gridColumn:"1/-1",display:"flex",gap:10,justifyContent:"flex-end",marginTop:8}}>
        <button type="button" style={{...S.btn,...S.btnGhost}} onClick={onCancel}>Cancel</button>
        <button type="submit" style={{...S.btn,...S.btnPrimary}} disabled={loading}>
          {loading
            ? <span style={{display:"flex",alignItems:"center",gap:8}}>{Icon.spinner} Saving…</span>
            : (initial ? "Update Record" : "Create Record")}
        </button>
      </div>
    </form>
  );
}

// ─── Modal ────────────────────────────────────────────────────────────────
function Modal({ title, children, onClose }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);
  return (
    <div style={S.modalOverlay} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={S.modalCard}>
        <div style={S.modalHeader}>
          <h3 style={S.modalTitle}>{title}</h3>
          <button style={S.modalClose} onClick={onClose}>{Icon.x}</button>
        </div>
        <div style={S.modalBody}>{children}</div>
      </div>
    </div>
  );
}

// ─── Pagination ───────────────────────────────────────────────────────────
function Pagination({ count, currentPage, totalPages, onPageChange }) {
  if (totalPages <= 1) return null;
  return (
    <div style={S.pagination}>
      <span style={S.paginationInfo}>{count} records · Page {currentPage} of {totalPages}</span>
      <div style={{display:"flex",gap:6}}>
        <button style={{...S.btn,...S.btnGhost,padding:"6px 12px"}}
          disabled={currentPage === 1} onClick={() => onPageChange(currentPage - 1)}>← Prev</button>
        <button style={{...S.btn,...S.btnGhost,padding:"6px 12px"}}
          disabled={currentPage === totalPages} onClick={() => onPageChange(currentPage + 1)}>Next →</button>
      </div>
    </div>
  );
}

// ─── Delete Confirm Modal ─────────────────────────────────────────────────
function DeleteConfirm({ record, onConfirm, onCancel, loading }) {
  const label = record?.name ?? record?.title ?? record?.username ?? `ID ${record?.id}`;
  return (
    <div style={{textAlign:"center",padding:"8px 0"}}>
      <div style={{fontSize:42,marginBottom:16}}>⚠️</div>
      <p style={{opacity:.8,marginBottom:8}}>You are about to permanently delete</p>
      <p style={{fontWeight:700,fontSize:18,color:"#f87171",marginBottom:20}}>"{label}"</p>
      <p style={{opacity:.5,fontSize:13,marginBottom:24}}>This action cannot be undone.</p>
      <div style={{display:"flex",gap:10,justifyContent:"center"}}>
        <button style={{...S.btn,...S.btnGhost}} onClick={onCancel}>Cancel</button>
        <button style={{...S.btn,background:"#ef4444",color:"#fff",border:"none"}}
          onClick={onConfirm} disabled={loading}>
          {loading ? "Deleting…" : "Delete"}
        </button>
      </div>
    </div>
  );
}

// ─── Dynamic Admin Page ───────────────────────────────────────────────────
function DynamicPage({ modelName }) {
  const [schema, setSchema] = useState(null);
  const [schemaLoading, setSchemaLoading] = useState(true);
  const [schemaError, setSchemaError] = useState(null);
  const [listData, setListData] = useState(null);
  const [listLoading, setListLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [modal, setModal] = useState(null);
  const [activeRecord, setActiveRecord] = useState(null);
  const [saving, setSaving] = useState(false);
  const { toast, show: showToast } = useToast();
  const searchTimer = useRef(null);

  useEffect(() => {
    setSchemaLoading(true); setSchemaError(null);
    schemaApi.getSchema(modelName)
      .then(s => { setSchema(s); setSchemaLoading(false); })
      .catch(e => { setSchemaError(e.message); setSchemaLoading(false); });
  }, [modelName]);

  const loadList = useCallback(() => {
    if (!schema) return;
    setListLoading(true);
    const params = { page, page_size: 25 };
    if (search) params.search = search;
    crudApi.list(schema.endpoint, params)
      .then(d => { setListData(d); setListLoading(false); })
      .catch(e => { showToast(e.message, "error"); setListLoading(false); });
  }, [schema, page, search]);

  useEffect(() => { loadList(); }, [loadList]);

  const handleSearchChange = (v) => {
    setSearchInput(v);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => { setSearch(v); setPage(1); }, 400);
  };

  const handleCreate = async (data) => {
    setSaving(true);
    try { await crudApi.create(schema.endpoint, data); showToast("Record created"); setModal(null); loadList(); }
    catch (e) { showToast(e.message, "error"); }
    finally { setSaving(false); }
  };

  const handleUpdate = async (data) => {
    setSaving(true);
    try { await crudApi.update(schema.endpoint, activeRecord.id, data); showToast("Record updated"); setModal(null); setActiveRecord(null); loadList(); }
    catch (e) { showToast(e.message, "error"); }
    finally { setSaving(false); }
  };

  const handleDelete = async () => {
    setSaving(true);
    try { await crudApi.delete(schema.endpoint, activeRecord.id); showToast("Record deleted","info"); setModal(null); setActiveRecord(null); loadList(); }
    catch (e) { showToast(e.message, "error"); }
    finally { setSaving(false); }
  };

  if (schemaLoading) return <div style={S.centerFlex}>{Icon.spinner}<span style={{marginLeft:12,opacity:.6}}>Loading schema…</span></div>;
  if (schemaError) return <div style={S.centerFlex}><span style={{color:"#f87171"}}>Schema error: {schemaError}</span></div>;

  return (
    <div style={S.pageWrap}>
      <Toast toast={toast} />
      <div style={S.pageHeader}>
        <div>
          <div style={S.breadcrumb}>
            <span style={{opacity:.5}}>Admin</span>
            <span style={{opacity:.35,margin:"0 6px"}}>/</span>
            <span>{schema.name}</span>
          </div>
          <h1 style={S.pageTitle}>{schema.name}</h1>
          <div style={S.pageSubtitle}>{listData?.count ?? "—"} total records</div>
        </div>
        <button style={{...S.btn,...S.btnPrimary}} onClick={() => { setActiveRecord(null); setModal("create"); }}>
          {Icon.plus} New {schema.name}
        </button>
      </div>
      <div style={S.toolbar}>
        <div style={S.searchWrap}>
          <span style={S.searchIcon}>{Icon.search}</span>
          <input style={S.searchInput} placeholder={`Search ${schema.name}…`}
            value={searchInput} onChange={e => handleSearchChange(e.target.value)} />
        </div>
      </div>
      <DynamicTable schema={schema} data={listData?.results} loading={listLoading}
        onEdit={row => { setActiveRecord(row); setModal("edit"); }}
        onDelete={row => { setActiveRecord(row); setModal("delete"); }} />
      <Pagination count={listData?.count ?? 0}
        currentPage={listData?.current_page ?? page}
        totalPages={listData?.total_pages ?? 1}
        onPageChange={p => setPage(p)} />
      {modal === "create" && (
        <Modal title={`Create ${schema.name}`} onClose={() => setModal(null)}>
          <DynamicForm schema={schema} initial={null} onSubmit={handleCreate} onCancel={() => setModal(null)} loading={saving} />
        </Modal>
      )}
      {modal === "edit" && activeRecord && (
        <Modal title={`Edit ${schema.name} #${activeRecord.id}`} onClose={() => { setModal(null); setActiveRecord(null); }}>
          <DynamicForm schema={schema} initial={activeRecord} onSubmit={handleUpdate} onCancel={() => { setModal(null); setActiveRecord(null); }} loading={saving} />
        </Modal>
      )}
      {modal === "delete" && activeRecord && (
        <Modal title="Confirm Deletion" onClose={() => { setModal(null); setActiveRecord(null); }}>
          <DeleteConfirm record={activeRecord} onConfirm={handleDelete} onCancel={() => { setModal(null); setActiveRecord(null); }} loading={saving} />
        </Modal>
      )}
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────
function Dashboard({ schemas }) {
  const { user } = useAuth();
  return (
    <div style={S.pageWrap}>
      <div style={S.pageHeader}>
        <div>
          <h1 style={S.pageTitle}>Dashboard</h1>
          <div style={S.pageSubtitle}>Welcome back, {user?.username}</div>
        </div>
      </div>
      <div style={S.dashGrid}>
        {/* Files card */}
        <button key="files" style={S.dashCard} onClick={() => navigate("/admin/files")}>
          <div style={{...S.dashCardIcon, color:"#22d3ee"}}>{Icon.file}</div>
          <div style={S.dashCardName}>Files</div>
          <div style={S.dashCardSub}>Upload &amp; manage files</div>
          <div style={S.dashCardArrow}>{Icon.chevronRight}</div>
        </button>
        {schemas?.map(s => (
          <button key={s.label} style={S.dashCard} onClick={() => navigate(`/admin/${s.label.toLowerCase()}`)}>
            <div style={S.dashCardIcon}>{Icon.db}</div>
            <div style={S.dashCardName}>{s.label}</div>
            <div style={S.dashCardSub}>View &amp; manage records</div>
            <div style={S.dashCardArrow}>{Icon.chevronRight}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── App Shell ────────────────────────────────────────────────────────────
function AdminShell() {
  const path = useRoute();
  const [schemas, setSchemas] = useState([]);
  const [schemasLoading, setSchemasLoading] = useState(true);

  useEffect(() => {
    schemaApi.listing()
      .then(s => { setSchemas(s); setSchemasLoading(false); })
      .catch(() => setSchemasLoading(false));
  }, []);

  const match = path.match(/^\/admin\/([^/]+)/);
  const currentModel = match ? match[1] : null;
  const isFilesPage = path === "/admin/files";

  return (
    <div style={S.shell}>
      <Sidebar schemas={schemas} currentModel={isFilesPage ? null : currentModel} />
      <main style={S.mainContent}>
        {path === "/admin" || path === "/admin/" ? (
          <Dashboard schemas={schemas} />
        ) : isFilesPage ? (
          <FilesPage />
        ) : currentModel ? (
          <DynamicPage modelName={currentModel} />
        ) : (
          <div style={S.centerFlex}>
            <span style={{opacity:.4}}>Select a model from the sidebar</span>
          </div>
        )}
      </main>
    </div>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────
function App() {
  const { isAuthenticated, loading } = useAuth();
  const path = useRoute();
  if (loading) return <div style={{...S.centerFlex,height:"100vh",background:"#0a0c0f"}}>{Icon.spinner}</div>;
  if (!isAuthenticated) {
    if (path !== "/login") { navigate("/login"); return null; }
    return <LoginPage />;
  }
  if (path === "/login") { navigate("/admin"); return null; }
  return <AdminShell />;
}

export default function Root() {
  return <AuthProvider><App /></AuthProvider>;
}

// ─── Styles ───────────────────────────────────────────────────────────────
const S = {
  loginWrap: { minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:"#0a0c0f",fontFamily:"'IBM Plex Sans',system-ui,sans-serif" },
  loginCard: { background:"#111318",border:"1px solid #1e2230",borderRadius:12,padding:40,width:380,boxShadow:"0 24px 80px rgba(0,0,0,.6)" },
  loginLogo: { display:"flex",alignItems:"center",gap:10,marginBottom:8 },
  logoIcon:  { color:"#22d3ee",display:"flex" },
  logoText:  { fontFamily:"'JetBrains Mono',monospace",fontSize:20,fontWeight:700,letterSpacing:4,color:"#e2e8f0" },
  loginSub:  { color:"#64748b",fontSize:13,marginBottom:28,marginTop:0 },

  sidebar: { width:220,flexShrink:0,background:"#0d0f14",borderRight:"1px solid #1a1f2e",display:"flex",flexDirection:"column",height:"100vh",position:"sticky",top:0 },
  sidebarHeader: { padding:"22px 20px 18px",display:"flex",alignItems:"center",gap:10,borderBottom:"1px solid #1a1f2e" },
  sidebarLogoIcon: { color:"#22d3ee",display:"flex" },
  sidebarLogoText: { fontFamily:"'JetBrains Mono',monospace",fontSize:15,fontWeight:700,letterSpacing:4,color:"#e2e8f0" },
  sidebarSection: { padding:"18px 12px 8px" },
  sidebarSectionLabel: { fontSize:10,fontWeight:700,letterSpacing:2,color:"#334155",textTransform:"uppercase",paddingLeft:8,marginBottom:6 },
  navItem: { display:"flex",alignItems:"center",gap:9,width:"100%",padding:"8px 10px",borderRadius:7,border:"none",background:"transparent",color:"#94a3b8",fontSize:13,fontWeight:500,cursor:"pointer",textAlign:"left",transition:"all .15s" },
  navItemActive: { background:"rgba(34,211,238,.08)",color:"#22d3ee" },
  navDot: { width:5,height:5,borderRadius:"50%",background:"currentColor",opacity:.4,flexShrink:0 },
  sidebarFooter: { marginTop:"auto",padding:14,borderTop:"1px solid #1a1f2e",display:"flex",alignItems:"center",gap:10 },
  userBadge: { display:"flex",alignItems:"center",gap:10,flex:1,overflow:"hidden" },
  userAvatar: { width:30,height:30,borderRadius:8,background:"linear-gradient(135deg,#22d3ee,#7c3aed)",display:"flex",alignItems:"center",justifyContent:"center",fontWeight:700,fontSize:13,color:"#fff",flexShrink:0 },
  userName: { fontSize:13,fontWeight:600,color:"#e2e8f0",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap" },
  userRole: { fontSize:11,color:"#475569" },
  logoutBtn: { background:"transparent",border:"none",color:"#475569",cursor:"pointer",padding:6,borderRadius:6,display:"flex",alignItems:"center" },

  shell: { display:"flex",minHeight:"100vh",background:"#0a0c0f",fontFamily:"'IBM Plex Sans',system-ui,sans-serif",color:"#cbd5e1" },
  mainContent: { flex:1,overflow:"auto" },

  pageWrap: { padding:"28px 32px",maxWidth:1200,position:"relative" },
  pageHeader: { display:"flex",alignItems:"flex-start",justifyContent:"space-between",marginBottom:24,gap:16 },
  breadcrumb: { fontSize:12,color:"#475569",marginBottom:8,display:"flex",alignItems:"center" },
  pageTitle: { fontSize:26,fontWeight:700,color:"#f1f5f9",margin:0,letterSpacing:"-0.5px" },
  pageSubtitle: { fontSize:13,color:"#475569",marginTop:4 },
  centerFlex: { display:"flex",alignItems:"center",justifyContent:"center",height:"60vh",color:"#475569" },

  dashGrid: { display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(200px,1fr))",gap:14,marginTop:8 },
  dashCard: { background:"#111318",border:"1px solid #1a1f2e",borderRadius:10,padding:"20px 18px",cursor:"pointer",textAlign:"left",transition:"all .2s",display:"flex",flexDirection:"column",gap:6,position:"relative" },
  dashCardIcon: { color:"#475569",opacity:.6,marginBottom:4 },
  dashCardName: { fontWeight:700,fontSize:16,color:"#e2e8f0" },
  dashCardSub: { fontSize:12,color:"#475569" },
  dashCardArrow: { position:"absolute",top:18,right:16,color:"#334155" },

  toolbar: { display:"flex",gap:10,marginBottom:16,alignItems:"center" },
  searchWrap: { position:"relative",flex:1,maxWidth:360 },
  searchIcon: { position:"absolute",left:12,top:"50%",transform:"translateY(-50%)",color:"#475569",pointerEvents:"none" },
  searchInput: { width:"100%",padding:"9px 12px 9px 38px",background:"#111318",border:"1px solid #1e2230",borderRadius:8,color:"#e2e8f0",fontSize:14,outline:"none",boxSizing:"border-box" },

  tableWrap: { background:"#111318",border:"1px solid #1a1f2e",borderRadius:10,overflow:"hidden" },
  table: { width:"100%",borderCollapse:"collapse",fontSize:13 },
  th: { padding:"11px 16px",textAlign:"left",color:"#475569",fontSize:11,fontWeight:700,letterSpacing:1,textTransform:"uppercase",borderBottom:"1px solid #1a1f2e",background:"#0d0f14" },
  tr: { transition:"background .1s" },
  td: { padding:"12px 16px",borderBottom:"1px solid #131720",color:"#cbd5e1",verticalAlign:"middle" },
  emptyCell: { padding:48,textAlign:"center",color:"#334155",fontSize:14 },
  tableLoadingWrap: { padding:48,display:"flex",alignItems:"center",justifyContent:"center",color:"#475569" },

  badge: {
    green: { background:"rgba(34,197,94,.1)",color:"#4ade80",padding:"2px 8px",borderRadius:4,fontSize:12,display:"inline-flex",alignItems:"center",gap:4,fontWeight:600 },
    red:   { background:"rgba(248,113,113,.1)",color:"#f87171",padding:"2px 8px",borderRadius:4,fontSize:12,display:"inline-flex",alignItems:"center",gap:4,fontWeight:600 },
    gray:  { background:"rgba(100,116,139,.12)",color:"#94a3b8",padding:"2px 8px",borderRadius:4,fontSize:12,fontWeight:600 },
  },

  actionBtn: { background:"transparent",border:"1px solid #1e2230",borderRadius:6,padding:"5px 8px",color:"#64748b",cursor:"pointer",marginLeft:4,display:"inline-flex",alignItems:"center",transition:"all .15s" },
  actionBtnDanger: { color:"#ef4444",borderColor:"rgba(239,68,68,.2)" },

  pagination: { display:"flex",alignItems:"center",justifyContent:"space-between",padding:"14px 0",marginTop:8 },
  paginationInfo: { fontSize:13,color:"#475569" },

  modalOverlay: { position:"fixed",inset:0,background:"rgba(0,0,0,.7)",backdropFilter:"blur(4px)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:1000,padding:20 },
  modalCard: { background:"#111318",border:"1px solid #1e2230",borderRadius:14,width:"100%",maxWidth:640,maxHeight:"90vh",display:"flex",flexDirection:"column",boxShadow:"0 40px 120px rgba(0,0,0,.8)" },
  modalHeader: { display:"flex",alignItems:"center",justifyContent:"space-between",padding:"18px 24px",borderBottom:"1px solid #1a1f2e" },
  modalTitle: { margin:0,fontSize:17,fontWeight:700,color:"#f1f5f9" },
  modalClose: { background:"transparent",border:"none",color:"#475569",cursor:"pointer",padding:6,borderRadius:6,display:"flex",alignItems:"center" },
  modalBody: { padding:"20px 24px 24px",overflow:"auto" },

  formGrid: { display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))",gap:16 },
  formField: { display:"flex",flexDirection:"column",gap:6 },
  label: { fontSize:12,fontWeight:600,color:"#94a3b8",letterSpacing:.5 },
  input: { padding:"9px 12px",background:"#0d0f14",border:"1px solid #1e2230",borderRadius:8,color:"#e2e8f0",fontSize:14,outline:"none",boxSizing:"border-box",width:"100%",fontFamily:"inherit" },
  inputError: { borderColor:"#f87171" },
  fieldError: { fontSize:12,color:"#f87171" },
  helpText: { fontSize:11,color:"#475569" },
  errorBanner: { background:"rgba(248,113,113,.1)",border:"1px solid rgba(248,113,113,.25)",borderRadius:7,padding:"9px 12px",color:"#fca5a5",fontSize:13 },

  btn: { display:"inline-flex",alignItems:"center",gap:7,padding:"9px 16px",borderRadius:8,fontSize:13,fontWeight:600,cursor:"pointer",border:"1px solid transparent",transition:"all .15s",fontFamily:"inherit" },
  btnPrimary: { background:"linear-gradient(135deg,#0ea5e9,#22d3ee)",color:"#0f172a",border:"none" },
  btnGhost: { background:"transparent",border:"1px solid #1e2230",color:"#94a3b8" },

  toast: { position:"fixed",bottom:24,right:24,background:"#111318",border:"1px solid #1e2230",borderLeft:"3px solid #22d3ee",borderRadius:8,padding:"12px 18px",color:"#e2e8f0",fontSize:14,zIndex:2000,boxShadow:"0 8px 32px rgba(0,0,0,.5)",maxWidth:340 },

  // Drop zone
  dropZone: { border:"2px dashed #1e2230",borderRadius:12,padding:"32px 24px",textAlign:"center",cursor:"pointer",transition:"all .2s",background:"#0d0f14",marginBottom:4 },
  dropZoneActive: { borderColor:"#22d3ee",background:"rgba(34,211,238,.04)" },
  dropZoneIcon: { color:"#334155",display:"flex",justifyContent:"center",marginBottom:10,transform:"scale(1.5)" },
  dropZoneText: { color:"#64748b",fontSize:14,fontWeight:500,marginBottom:4 },
  dropZoneSub: { color:"#334155",fontSize:12 },
};

// ─── Global CSS ───────────────────────────────────────────────────────────
if (!document.getElementById("nexus-global-styles")) {
  const style = document.createElement("style");
  style.id = "nexus-global-styles";
  style.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
    * { box-sizing: border-box; }
    body { margin: 0; background: #0a0c0f; }
    @keyframes spin { to { transform: rotate(360deg); } }
    button:hover { opacity: .85; }
    input:focus, select:focus, textarea:focus { border-color: #22d3ee !important; box-shadow: 0 0 0 3px rgba(34,211,238,.08); }
    tr:hover td { background: rgba(255,255,255,.02); }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0d0f14; }
    ::-webkit-scrollbar-thumb { background: #1e2230; border-radius: 3px; }
    select option { background: #111318; }
  `;
  document.head.appendChild(style);
}