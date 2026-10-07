import { useCallback, useEffect, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import type { AnalyzeResponse, RenderSettings } from '../types';
import { useLanguage } from '../locales';

interface User {
  id: string;
  email: string;
  display_name: string;
}

interface Project {
  id: string;
  name: string;
  role: 'owner' | 'admin' | 'editor' | 'viewer';
  member_count: number;
  created_at: string;
  updated_at: string;
  assets?: Record<string, { data: unknown; updated_by: string; updated_at: string }>;
}

interface Member {
  id: string;
  email: string;
  display_name: string;
  role: Project['role'];
}

interface AuditEvent {
  id: number;
  actor_email: string;
  action: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface WorkspacePayload {
  analysis?: AnalyzeResponse;
  renderSettings?: RenderSettings;
  onLoadAnalysis?: (analysis: AnalyzeResponse) => void;
  onLoadRenderSettings?: (settings: RenderSettings) => void;
}

interface EnterpriseGateProps {
  children: (openWorkspace: (payload?: WorkspacePayload) => void) => ReactNode;
}

async function apiRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: 'same-origin',
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(data?.detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function EnterpriseGate({ children }: EnterpriseGateProps) {
  const { language } = useLanguage();
  const isIndonesian = language === 'id';
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [showWorkspace, setShowWorkspace] = useState(false);
  const [workspacePayload, setWorkspacePayload] = useState<WorkspacePayload>({});
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [authBusy, setAuthBusy] = useState(false);

  const acceptUser = useCallback((nextUser: User) => {
    localStorage.setItem('cheat_clip_active_user', nextUser.id);
    setUser(nextUser);
    setAuthError('');
  }, []);

  useEffect(() => {
    let mounted = true;
    apiRequest<{ user: User }>('/api/auth/me')
      .then((data) => {
        if (mounted) acceptUser(data.user);
      })
      .catch((error: unknown) => {
        if (mounted && !(error instanceof Error && error.message === 'Sign in to continue')) {
          setAuthError(error instanceof Error ? error.message : String(error));
        }
      })
      .finally(() => {
        if (mounted) setCheckingSession(false);
      });
    return () => {
      mounted = false;
    };
  }, [acceptUser]);

  const submitAuth = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthBusy(true);
    setAuthError('');
    try {
      const body = authMode === 'register'
        ? { email, display_name: displayName, password }
        : { email, password };
      const data = await apiRequest<{ user: User }>(`/api/auth/${authMode === 'register' ? 'register' : 'login'}`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      acceptUser(data.user);
      setPassword('');
    } catch (error: unknown) {
      setAuthError(error instanceof Error ? error.message : String(error));
    } finally {
      setAuthBusy(false);
    }
  };

  const openWorkspace = (payload: WorkspacePayload = {}) => {
    setWorkspacePayload(payload);
    setShowWorkspace(true);
  };

  const signOut = async () => {
    await apiRequest<void>('/api/auth/logout', { method: 'POST' });
    localStorage.removeItem('cheat_clip_active_user');
    setUser(null);
    setShowWorkspace(false);
  };

  if (checkingSession) {
    return <main className="enterprise-auth-shell"><p>{isIndonesian ? 'Memeriksa sesi...' : 'Checking session...'}</p></main>;
  }

  if (!user) {
    return (
      <main className="enterprise-auth-shell">
        <form className="enterprise-auth-card" onSubmit={submitAuth}>
          <div className="enterprise-brand">⚡ CHEAT CLIP <span>PRO</span></div>
          <h1>{authMode === 'login' ? (isIndonesian ? 'Selamat datang kembali' : 'Welcome back') : (isIndonesian ? 'Buat akun' : 'Create your account')}</h1>
          <p>{isIndonesian ? 'Masuk untuk mengakses project bersama dan kontrol akses.' : 'Sign in to access shared projects and access controls.'}</p>
          {authMode === 'register' && (
            <label>
              {isIndonesian ? 'Nama' : 'Name'}
              <input autoComplete="name" required maxLength={80} value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
            </label>
          )}
          <label>
            Email
            <input type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            {isIndonesian ? 'Kata sandi' : 'Password'}
            <input type="password" autoComplete={authMode === 'register' ? 'new-password' : 'current-password'} required minLength={authMode === 'register' ? 10 : 1} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} />
            {authMode === 'register' && <small>{isIndonesian ? 'Minimal 10 karakter.' : 'At least 10 characters.'}</small>}
          </label>
          {authError && <div className="enterprise-alert" role="alert">{authError}</div>}
          <button className="enterprise-primary" type="submit" disabled={authBusy}>
            {authBusy ? (isIndonesian ? 'Memproses...' : 'Please wait...') : authMode === 'login' ? (isIndonesian ? 'Masuk' : 'Sign in') : (isIndonesian ? 'Buat akun' : 'Create account')}
          </button>
          <button className="enterprise-link" type="button" onClick={() => { setAuthMode(authMode === 'login' ? 'register' : 'login'); setAuthError(''); }}>
            {authMode === 'login' ? (isIndonesian ? 'Belum punya akun? Daftar' : 'New here? Create an account') : (isIndonesian ? 'Sudah punya akun? Masuk' : 'Already have an account? Sign in')}
          </button>
        </form>
      </main>
    );
  }

  return (
    <>
      {children(openWorkspace)}
      {showWorkspace && (
        <WorkspaceModal
          user={user}
          payload={workspacePayload}
          onClose={() => setShowWorkspace(false)}
          onSignOut={() => { void signOut().catch((error: unknown) => setAuthError(error instanceof Error ? error.message : String(error))); }}
          onLoadAnalysis={(analysis) => {
            workspacePayload.onLoadAnalysis?.(analysis);
            setShowWorkspace(false);
          }}
          onLoadRenderSettings={(settings) => {
            workspacePayload.onLoadRenderSettings?.(settings);
            setShowWorkspace(false);
          }}
        />
      )}
      {authError && <div className="enterprise-global-error" role="alert">{authError}</div>}
    </>
  );
}

function WorkspaceModal({
  user,
  payload,
  onClose,
  onSignOut,
  onLoadAnalysis,
  onLoadRenderSettings,
}: {
  user: User;
  payload: WorkspacePayload;
  onClose: () => void;
  onSignOut: () => void;
  onLoadAnalysis: (analysis: AnalyzeResponse) => void;
  onLoadRenderSettings: (settings: RenderSettings) => void;
}) {
  const { language } = useLanguage();
  const id = language === 'id';
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [projectName, setProjectName] = useState('');
  const [memberEmail, setMemberEmail] = useState('');
  const [memberRole, setMemberRole] = useState<'admin' | 'editor' | 'viewer'>('editor');
  const [renameValue, setRenameValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const loadProjects = useCallback(async () => {
    const data = await apiRequest<Project[]>('/api/projects');
    setProjects(data);
    setSelectedId((current) => data.some((item) => item.id === current) ? current : data[0]?.id || '');
  }, []);

  const loadProject = useCallback(async (projectId: string) => {
    const details = await apiRequest<Project>(`/api/projects/${projectId}`);
    const projectMembers = await apiRequest<Member[]>(`/api/projects/${projectId}/members`);
    setProject(details);
    setMembers(projectMembers);
    setRenameValue(details.name);
    if (details.role === 'owner' || details.role === 'admin') {
      setAudit(await apiRequest<AuditEvent[]>(`/api/audit?project_id=${encodeURIComponent(projectId)}&limit=100`));
    } else {
      setAudit([]);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const initializeProjects = async () => {
      try {
        await loadProjects();
      } catch (reason: unknown) {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      }
    };
    void initializeProjects();
    return () => {
      active = false;
    };
  }, [loadProjects]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    const initializeProject = async () => {
      try {
        await loadProject(selectedId);
      } catch (reason: unknown) {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      }
    };
    void initializeProject();
    return () => {
      active = false;
    };
  }, [loadProject, selectedId]);

  const runAction = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await action();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const createProject = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runAction(async () => {
      const created = await apiRequest<Project>('/api/projects', {
        method: 'POST',
        body: JSON.stringify({ name: projectName }),
      });
      setProjectName('');
      await loadProjects();
      setSelectedId(created.id);
      setNotice(id ? 'Project dibuat.' : 'Project created.');
    });
  };

  const saveAssets = (assetType: 'analysis' | 'render_settings') => {
    if (!project) return;
    const analysis = assetType === 'analysis' ? payload.analysis : undefined;
    const settings = assetType === 'render_settings' ? payload.renderSettings : undefined;
    if (!analysis && !settings) return;
    void runAction(async () => {
      const renderSettings = settings ? {
        ...settings,
        bgmFilePath: undefined,
        hookSfxFilePath: undefined,
        watermarkFilePath: undefined,
      } : undefined;
      await apiRequest(`/api/projects/${project.id}/assets`, {
        method: 'PUT',
        body: JSON.stringify({
          ...(analysis ? { analysis } : {}),
          ...(renderSettings ? { render_settings: renderSettings } : {}),
        }),
      });
      await loadProject(project.id);
      await loadProjects();
      setNotice(id ? 'Konten tersimpan ke project.' : 'Content saved to project.');
    });
  };

  const addMember = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project) return;
    void runAction(async () => {
      await apiRequest(`/api/projects/${project.id}/members`, {
        method: 'POST',
        body: JSON.stringify({ email: memberEmail, role: memberRole }),
      });
      setMemberEmail('');
      await loadProject(project.id);
      setNotice(id ? 'Anggota ditambahkan.' : 'Member added.');
    });
  };

  const changeRole = (member: Member, role: string) => {
    if (!project) return;
    void runAction(async () => {
      await apiRequest(`/api/projects/${project.id}/members/${member.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ role }),
      });
      await loadProject(project.id);
    });
  };

  const removeMember = (member: Member) => {
    if (!project) return;
    const confirmed = window.confirm(id ? `Hapus ${member.email} dari project?` : `Remove ${member.email} from this project?`);
    if (!confirmed) return;
    void runAction(async () => {
      await apiRequest(`/api/projects/${project.id}/members/${member.id}`, { method: 'DELETE' });
      await loadProject(project.id);
      setNotice(id ? 'Akses anggota dicabut.' : 'Member access removed.');
    });
  };

  const canManage = project?.role === 'owner' || project?.role === 'admin';
  const canEdit = canManage || project?.role === 'editor';

  return (
    <div className="enterprise-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="enterprise-workspace" role="dialog" aria-modal="true" aria-labelledby="enterprise-title">
        <header className="enterprise-workspace-header">
          <div>
            <p className="enterprise-eyebrow">{user.email}</p>
            <h2 id="enterprise-title">{id ? 'Project bersama' : 'Shared projects'}</h2>
          </div>
          <div className="enterprise-header-actions">
            <button type="button" className="enterprise-secondary" onClick={onSignOut}>{id ? 'Keluar' : 'Sign out'}</button>
            <button type="button" className="enterprise-close" aria-label={id ? 'Tutup' : 'Close'} onClick={onClose}>×</button>
          </div>
        </header>
        <div className="enterprise-workspace-body">
          <aside className="enterprise-project-list">
            <form className="enterprise-create-project" onSubmit={createProject}>
              <input aria-label={id ? 'Nama project baru' : 'New project name'} required maxLength={120} value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder={id ? 'Nama project' : 'Project name'} />
              <button className="enterprise-primary" disabled={busy} type="submit">{id ? 'Buat' : 'Create'}</button>
            </form>
            {projects.map((item) => (
              <button key={item.id} type="button" className={`enterprise-project-item${item.id === selectedId ? ' selected' : ''}`} onClick={() => { setProject(null); setSelectedId(item.id); }}>
                <strong>{item.name}</strong><span>{item.role} · {item.member_count} {id ? 'anggota' : 'members'}</span>
              </button>
            ))}
            {projects.length === 0 && <p className="enterprise-muted">{id ? 'Belum ada project. Buat project pertama Anda.' : 'No projects yet. Create your first project.'}</p>}
          </aside>
          <main className="enterprise-project-details">
            {error && <div className="enterprise-alert" role="alert">{error}</div>}
            {notice && <div className="enterprise-success" role="status">{notice}</div>}
            {!project ? <p className="enterprise-muted">{id ? 'Pilih atau buat project untuk memulai.' : 'Select or create a project to get started.'}</p> : (
              <>
                <div className="enterprise-project-heading">
                  <div><span className="enterprise-role-badge">{project.role}</span><h3>{project.name}</h3><p>{project.member_count} {id ? 'anggota' : 'members'}</p></div>
                  {canManage && (
                    <div className="enterprise-project-actions">
                      <input aria-label={id ? 'Nama project' : 'Project name'} value={renameValue} maxLength={120} onChange={(event) => setRenameValue(event.target.value)} />
                      <button type="button" className="enterprise-secondary" disabled={busy || !renameValue.trim()} onClick={() => { void runAction(async () => { await apiRequest(`/api/projects/${project.id}`, { method: 'PATCH', body: JSON.stringify({ name: renameValue }) }); await loadProjects(); await loadProject(project.id); }); }}>{id ? 'Ubah nama' : 'Rename'}</button>
                      {project.role === 'owner' && <button type="button" className="enterprise-danger" disabled={busy} onClick={() => { if (!window.confirm(id ? 'Hapus project dan seluruh kontennya?' : 'Delete this project and all its content?')) return; void runAction(async () => { await apiRequest(`/api/projects/${project.id}`, { method: 'DELETE' }); setProject(null); setSelectedId(''); await loadProjects(); }); }}>{id ? 'Hapus' : 'Delete'}</button>}
                    </div>
                  )}
                </div>

                {(payload.analysis || payload.renderSettings) && canEdit && (
                  <section className="enterprise-section">
                    <h4>{id ? 'Simpan dari sesi ini' : 'Save from this session'}</h4>
                    <div className="enterprise-inline-actions">
                      {payload.analysis && <button className="enterprise-primary" type="button" disabled={busy} onClick={() => saveAssets('analysis')}>{id ? 'Simpan analisis' : 'Save analysis'}</button>}
                      {payload.renderSettings && <button className="enterprise-secondary" type="button" disabled={busy} onClick={() => saveAssets('render_settings')}>{id ? 'Simpan pengaturan render' : 'Save render settings'}</button>}
                    </div>
                  </section>
                )}

                {project.assets?.analysis && (
                  <section className="enterprise-section">
                    <h4>{id ? 'Analisis bersama' : 'Shared analysis'}</h4>
                    <p>{String((project.assets.analysis.data as AnalyzeResponse).title || '')}</p>
                    <button type="button" className="enterprise-secondary" onClick={() => onLoadAnalysis(project.assets!.analysis!.data as AnalyzeResponse)}>{id ? 'Muat analisis' : 'Load analysis'}</button>
                  </section>
                )}
                {project.assets?.render_settings && (
                  <section className="enterprise-section">
                    <h4>{id ? 'Pengaturan render tersimpan' : 'Saved render settings'}</h4>
                    <button
                      type="button"
                      className="enterprise-secondary"
                      onClick={() => onLoadRenderSettings(project.assets!.render_settings!.data as RenderSettings)}
                    >
                      {id ? 'Terapkan pengaturan' : 'Apply settings'}
                    </button>
                    <details>
                      <summary>{id ? 'Lihat detail' : 'View details'}</summary>
                      <pre className="enterprise-json">{JSON.stringify(project.assets.render_settings.data, null, 2)}</pre>
                    </details>
                  </section>
                )}

                <section className="enterprise-section">
                  <h4>{id ? 'Anggota & peran' : 'Members & roles'}</h4>
                  {canManage && (
                    <form className="enterprise-member-form" onSubmit={addMember}>
                      <input type="email" required aria-label="Email" placeholder={id ? 'Email akun terdaftar' : 'Registered account email'} value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} />
                      <select aria-label={id ? 'Peran anggota' : 'Member role'} value={memberRole} onChange={(event) => setMemberRole(event.target.value as typeof memberRole)}>
                        {project.role === 'owner' && <option value="admin">Admin</option>}
                        <option value="editor">Editor</option><option value="viewer">Viewer</option>
                      </select>
                      <button type="submit" className="enterprise-primary" disabled={busy}>{id ? 'Tambah' : 'Add'}</button>
                    </form>
                  )}
                  <div className="enterprise-members">
                    {members.map((member) => (
                      <div className="enterprise-member-row" key={member.id}>
                        <div><strong>{member.display_name}</strong><span>{member.email}</span></div>
                        {member.role === 'owner' ? <span className="enterprise-role-badge">Owner</span> : canManage ? (
                          <div className="enterprise-member-actions">
                            <select aria-label={`${id ? 'Peran' : 'Role'} ${member.email}`} value={member.role} disabled={busy || (project.role === 'admin' && member.role === 'admin')} onChange={(event) => changeRole(member, event.target.value)}>
                              {project.role === 'owner' && <option value="admin">Admin</option>}
                              <option value="editor">Editor</option><option value="viewer">Viewer</option>
                            </select>
                            <button type="button" className="enterprise-danger" disabled={busy} onClick={() => removeMember(member)}>{id ? 'Hapus' : 'Remove'}</button>
                          </div>
                        ) : <span className="enterprise-role-badge">{member.role}</span>}
                      </div>
                    ))}
                  </div>
                </section>

                {canManage && (
                  <section className="enterprise-section">
                    <h4>{id ? 'Audit aktivitas project' : 'Project activity audit'}</h4>
                    <div className="enterprise-audit-list">
                      {audit.map((event) => (
                        <div className="enterprise-audit-row" key={event.id}>
                          <span><strong>{event.action}</strong><small>{event.actor_email}</small></span>
                          <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>
                        </div>
                      ))}
                      {audit.length === 0 && <p className="enterprise-muted">{id ? 'Belum ada aktivitas.' : 'No activity yet.'}</p>}
                    </div>
                  </section>
                )}
              </>
            )}
          </main>
        </div>
      </section>
    </div>
  );
}
