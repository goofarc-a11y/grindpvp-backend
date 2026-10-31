import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  AudioLines,
  Axe,
  BadgeCheck,
  Bomb,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Crown,
  Droplets,
  Eye,
  EyeOff,
  Flame,
  Gem,
  LoaderCircle,
  LogIn,
  LogOut,
  Medal,
  Moon,
  RefreshCw,
  Search,
  Settings2,
  Shield,
  Swords,
  Target,
  Trophy,
  UserRound,
  UsersRound,
  Waves,
  Wind,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError, query } from "./api";
import grindPvPLogo from "./assets/grindpvp-logo.png";
import type {
  AdminLog,
  Catalog,
  LeaderboardEntry,
  MatchRecord,
  Page,
  PageResult,
  Player,
  TierDefinition,
} from "./types";

const KIT_LABELS: Record<string, string> = {
  overall: "Overall",
  sword: "Sword",
  axe: "Axe",
  uhc: "UHC",
  diapot: "DiaPot",
  nethop: "NethOP",
  smp: "SMP",
  mace: "Mace",
  crystal: "Crystal",
  speed: "Speed",
  diasmp: "DiaSMP",
  ogvanilla: "OGVanilla",
  cart: "Cart",
  spearmace: "Spearmace",
  manhunt: "Manhunt",
};
const KIT_ICONS: Record<string, LucideIcon> = {
  overall: Trophy,
  sword: Swords,
  axe: Axe,
  uhc: Flame,
  diapot: Droplets,
  nethop: Shield,
  smp: Waves,
  mace: Zap,
  crystal: Gem,
  speed: Wind,
  diasmp: Shield,
  ogvanilla: Crown,
  cart: Bomb,
  spearmace: Target,
  manhunt: Search,
};
const MAIN_KITS = ["sword", "axe", "uhc", "diapot", "nethop", "smp", "mace", "crystal"];
const SUB_KITS = ["speed", "diasmp", "ogvanilla", "cart", "spearmace", "manhunt"];
const PAGE_SIZE = 25;
const TOKEN_KEY = "grindpvp.admin.session";
const MY_PROFILE_KEY = "grindpvp.my-profile.uuid";
const SETTINGS_KEY = "grindpvp.website.settings";
const DEFAULT_SETTINGS = { animations: true, sounds: true, hoverSounds: false, volume: 18 };

type Settings = typeof DEFAULT_SETTINGS;

function useLocalSettings(): [Settings, (next: Settings) => void] {
  const [settings, setSettings] = useState<Settings>(() => {
    try {
      const saved = localStorage.getItem(SETTINGS_KEY);
      return saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : DEFAULT_SETTINGS;
    } catch {
      return DEFAULT_SETTINGS;
    }
  });
  const update = (next: Settings) => {
    setSettings(next);
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
  };
  return [settings, update];
}

function playUiSound(settings: Settings, kind: "click" | "hover" | "page") {
  if (!settings.sounds || settings.volume <= 0 || (kind === "hover" && !settings.hoverSounds)) return;
  try {
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    const start = context.currentTime;
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(kind === "page" ? 560 : kind === "hover" ? 820 : 680, start);
    oscillator.frequency.exponentialRampToValueAtTime(kind === "page" ? 280 : 460, start + 0.075);
    gain.gain.setValueAtTime((settings.volume / 100) * (kind === "hover" ? 0.025 : 0.045), start);
    gain.gain.exponentialRampToValueAtTime(0.001, start + (kind === "page" ? 0.15 : 0.09));
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(start);
    oscillator.stop(start + 0.16);
    oscillator.onended = () => void context.close();
  } catch {
    // Audio is an enhancement; browser audio policy or device support may block it.
  }
}

function displayKit(kit: string) {
  return KIT_LABELS[kit] || kit;
}

function tierColor(name: string, tiers: TierDefinition[]) {
  return tiers.find((tier) => tier.name === name)?.color || "#8a8e95";
}

function avatarUrl(uuid: string, body = true) {
  return `https://mc-heads.net/${body ? "body" : "avatar"}/${encodeURIComponent(uuid)}/${body ? "128" : "96"}`;
}

function App() {
  const [settings, setSettings] = useLocalSettings();
  const [page, setPage] = useState<Page>("leaderboard");
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selectedKit, setSelectedKit] = useState("overall");
  const [leaderboard, setLeaderboard] = useState<PageResult<LeaderboardEntry> | null>(null);
  const [leaderboardPage, setLeaderboardPage] = useState(1);
  const [loadingLeaderboard, setLoadingLeaderboard] = useState(true);
  const [profileUuid, setProfileUuid] = useState("");
  const [profile, setProfile] = useState<Player | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [matches, setMatches] = useState<PageResult<MatchRecord> | null>(null);
  const [searchValue, setSearchValue] = useState("");
  const [searchResults, setSearchResults] = useState<Player[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [myProfileUuid, setMyProfileUuid] = useState(() => localStorage.getItem(MY_PROFILE_KEY) || "");
  const [adminToken, setAdminToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const [statusMessage, setStatusMessage] = useState("");
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [databaseEngine, setDatabaseEngine] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [showAdminPassword, setShowAdminPassword] = useState(false);
  const [adminLoading, setAdminLoading] = useState(false);
  const [matchRows, setMatchRows] = useState<PageResult<MatchRecord> | null>(null);
  const [logRows, setLogRows] = useState<PageResult<AdminLog> | null>(null);
  const transitionTimeout = useRef<number | undefined>(undefined);

  const changePage = useCallback(
    (next: Page) => {
      if (next === page) return;
      playUiSound(settings, "page");
      setPage(next);
      if (next === "my-profile") setProfileUuid(myProfileUuid);
      if (next === "profiles") setProfileUuid("");
      setStatusMessage("");
      if (settings.animations) {
        document.documentElement.classList.add("page-transition");
        window.clearTimeout(transitionTimeout.current);
        transitionTimeout.current = window.setTimeout(
          () => document.documentElement.classList.remove("page-transition"),
          340,
        );
      }
    },
    [page, settings, myProfileUuid],
  );

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (!document.hidden) setRefreshVersion((version) => version + 1);
    };
    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, []);

  useEffect(() => {
    let active = true;
    api<Catalog>("/catalog")
      .then((data) => {
        if (active) setCatalog(data);
      })
      .catch((error: Error) => {
        if (active) setStatusMessage(`Could not load GrindPvP catalog: ${error.message}`);
      });
    api<{ status: string; database_engine?: string }>("/health")
      .then((health) => {
        if (active) {
          setApiOnline(health.status === "ok");
          setDatabaseEngine(health.database_engine || "");
        }
      })
      .catch(() => active && setApiOnline(false));
    return () => {
      active = false;
      window.clearTimeout(transitionTimeout.current);
    };
  }, [refreshVersion]);

  useEffect(() => {
    if (page !== "leaderboard") return;
    const controller = new AbortController();
    setLeaderboard(null);
    setLoadingLeaderboard(true);
    setStatusMessage("");
    const endpoint = selectedKit === "overall" ? "/leaderboard/overall" : `/leaderboard/${selectedKit}`;
    api<PageResult<LeaderboardEntry>>(`${endpoint}?${query({ page: leaderboardPage, page_size: PAGE_SIZE })}`, {
      signal: controller.signal,
    })
      .then(setLeaderboard)
      .catch((error: Error) => {
        if (error.name !== "AbortError") setStatusMessage(`Leaderboard unavailable: ${error.message}`);
      })
      .finally(() => !controller.signal.aborted && setLoadingLeaderboard(false));
    return () => controller.abort();
  }, [page, selectedKit, leaderboardPage, refreshVersion]);

  useEffect(() => {
    if (!profileUuid) {
      setProfile(null);
      setMatches(null);
      return;
    }
    if (page !== "my-profile" && page !== "profiles") return;
    const controller = new AbortController();
    setProfileLoading(true);
    setProfile(null);
    setMatches(null);
    api<Player>(`/profiles/${encodeURIComponent(profileUuid)}`, { signal: controller.signal })
      .then((data) => {
        setProfile(data);
        setStatusMessage("");
      })
      .catch((error: Error) => {
        if (error.name !== "AbortError") {
          setProfile(null);
          setStatusMessage(`Could not load this profile: ${error.message}`);
        }
      })
      .finally(() => !controller.signal.aborted && setProfileLoading(false));
    api<PageResult<MatchRecord>>(`/matches/${encodeURIComponent(profileUuid)}?page=1&page_size=5`, {
      signal: controller.signal,
    })
      .then(setMatches)
      .catch(() => !controller.signal.aborted && setMatches(null));
    return () => controller.abort();
  }, [page, profileUuid, refreshVersion]);

  useEffect(() => {
    if (page !== "admin" || !adminToken) return;
    let active = true;
    api<PageResult<AdminLog>>("/admin/logs?page=1&page_size=8", { token: adminToken })
      .then((data) => active && setLogRows(data))
      .catch((error: Error) => {
        if (active) setStatusMessage(`Admin session unavailable: ${error.message}`);
      });
    api<PageResult<MatchRecord>>("/admin/matches?page=1&page_size=8", { token: adminToken })
      .then((data) => active && setMatchRows(data))
      .catch((error: Error) => active && setStatusMessage(`Could not load matches: ${error.message}`));
    return () => {
      active = false;
    };
  }, [page, adminToken, refreshVersion]);

  const performSearch = async (event?: FormEvent) => {
    event?.preventDefault();
    const term = searchValue.trim();
    if (term.length < 1 || term.length > 16) {
      setSearchError("Enter a Minecraft username (up to 16 characters).");
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    setSearchError("");
    try {
      const result = await api<PageResult<Player>>(`/players?${query({ search: term, page: 1, page_size: 100 })}`);
      setSearchResults(result.items);
      if (result.items.length === 0) setSearchError("No verified GrindPvP players found.");
    } catch (error) {
      setSearchError(`Player search failed: ${(error as Error).message}`);
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  };

  const openProfile = (uuid: string, origin: "profiles" | "my-profile" = "profiles") => {
    if (origin === "my-profile") {
      setMyProfileUuid(uuid);
      localStorage.setItem(MY_PROFILE_KEY, uuid);
      setProfileUuid(uuid);
    } else if (page !== "profiles") {
      changePage("profiles");
      setProfileUuid(uuid);
    } else {
      setProfileUuid(uuid);
    }
  };

  const doAdminLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") || "");
    if (!password) {
      setStatusMessage("Enter the existing admin access code.");
      return;
    }
    setAdminLoading(true);
    setStatusMessage("");
    try {
      const result = await api<{ access_token: string }>("/admin/login", {
        method: "POST",
        body: { password },
      });
      if (!result.access_token) throw new Error("Backend did not issue an admin session.");
      sessionStorage.setItem(TOKEN_KEY, result.access_token);
      setAdminToken(result.access_token);
      setStatusMessage("Secure admin session active for this browser tab.");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setAdminLoading(false);
    }
  };

  const doAdminLogout = async () => {
    try {
      await api<void>("/admin/logout", { method: "POST", body: {}, token: adminToken });
      setStatusMessage("Admin session ended.");
    } catch (error) {
      setStatusMessage(`Could not end session cleanly: ${(error as Error).message}`);
    } finally {
      sessionStorage.removeItem(TOKEN_KEY);
      setAdminToken("");
      setLogRows(null);
      setMatchRows(null);
    }
  };

  const sendAdminAction = async <T,>(path: string, body: unknown): Promise<T> => {
    try {
      const result = await api<T>(path, { method: "POST", body, token: adminToken });
      setStatusMessage("Action completed successfully.");
      const [logs, recentMatches] = await Promise.all([
        api<PageResult<AdminLog>>("/admin/logs?page=1&page_size=8", { token: adminToken }),
        api<PageResult<MatchRecord>>("/admin/matches?page=1&page_size=8", { token: adminToken }),
      ]);
      setLogRows(logs);
      setMatchRows(recentMatches);
      return result;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        sessionStorage.removeItem(TOKEN_KEY);
        setAdminToken("");
      }
      setStatusMessage(`Admin action failed: ${(error as Error).message}`);
      throw error;
    }
  };

  const nav = [
    { key: "leaderboard" as const, label: "Leaderboard", icon: Trophy },
    { key: "my-profile" as const, label: "My profile", icon: UserRound },
    { key: "profiles" as const, label: "Profiles", icon: UsersRound },
    { key: "settings" as const, label: "Settings", icon: Settings2 },
  ];

  return (
    <div
      className={`app-shell ${settings.animations ? "" : "reduce-motion"}`}
      onClick={(event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        const control = target.closest("button, a, [role='switch'], tr.player-row");
        if (control && !control.hasAttribute("data-sound-handled")) playUiSound(settings, "click");
      }}
      onPointerOver={(event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        const control = target.closest("button, a, [role='switch'], tr.player-row");
        if (!control || control.hasAttribute("data-sound-handled")) return;
        const previous = event.relatedTarget;
        if (!(previous instanceof Node) || !control.contains(previous)) playUiSound(settings, "hover");
      }}
    >
      <header className="topbar">
        <button className="brand" type="button" data-sound-handled onClick={() => changePage("leaderboard")} aria-label="GrindPvP home">
          <span className="brand-mark"><img src={grindPvPLogo} alt="" /></span>
          <span className="brand-word">GRIND<span>PVP</span></span>
        </button>
        <nav className="main-nav" aria-label="Main navigation">
          {nav.map(({ key, label, icon: Icon }) => (
            <button key={key} type="button" data-sound-handled className={`nav-link ${page === key ? "active" : ""}`}
              onClick={() => changePage(key)}>
              <Icon size={16} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          <div className={`api-status ${apiOnline ? "online" : apiOnline === false ? "offline" : ""}`}
            title={databaseEngine ? `Connected database: ${databaseEngine}` : undefined}>
            <span className="status-dot" />{apiOnline ? databaseEngine && databaseEngine !== "postgresql"
              ? `Database: ${databaseEngine}` : "Live data" : apiOnline === false ? "Offline" : "Connecting"}
          </div>
          <button type="button" className="admin-shortcut refresh-shortcut" aria-label="Refresh current data"
            title="Refresh current data" onClick={() => setRefreshVersion((version) => version + 1)}>
            <RefreshCw size={14} />
          </button>
          <button type="button" data-sound-handled className={`admin-shortcut ${page === "admin" ? "active" : ""}`}
            onClick={() => changePage("admin")}><Shield size={15} /> Admin</button>
        </div>
      </header>

      <div className="page-frame">
        {(page === "leaderboard" || page === "my-profile" || page === "profiles") && (
          <KitSidebar selectedKit={selectedKit} selectKit={(kit) => {
            setSelectedKit(kit);
            setLeaderboardPage(1);
            playUiSound(settings, "click");
          }} />
        )}
        <main className="main-content" key={page}>
          <div className="page-enter">
            {page === "leaderboard" && (
              <LeaderboardView
                catalog={catalog} kit={selectedKit} page={leaderboardPage} data={leaderboard}
                loading={loadingLeaderboard} error={statusMessage} tierColor={(tier) => tierColor(tier, catalog?.tiers || [])}
                onPage={setLeaderboardPage} onProfile={(uuid) => openProfile(uuid)} totalPlayers={leaderboard?.total || 0}
                play={(kind) => playUiSound(settings, kind)}
              />
            )}
            {page === "my-profile" && (
              <ProfilePage
                title="My profile" subtitle="Your GrindPvP stats, pulled directly from the shared ranking database."
                profile={profile} loading={profileLoading} uuid={profileUuid || myProfileUuid}
                matches={matches} catalog={catalog} error={statusMessage} searchValue={searchValue}
                searchResults={searchResults} searching={searchLoading} searchError={searchError}
                onSearchValue={setSearchValue} onSearch={performSearch}
                onSelect={(uuid) => openProfile(uuid, "my-profile")} onChangeProfile={() => {
                  setProfileUuid("");
                  setSearchResults([]);
                  setSearchError("");
                }} />
            )}
            {page === "profiles" && (
              <ProfilesPage
                profile={profile} loading={profileLoading} uuid={profileUuid} matches={matches} catalog={catalog}
                error={statusMessage} searchValue={searchValue} searchResults={searchResults}
                searching={searchLoading} searchError={searchError} onSearchValue={setSearchValue}
                onSearch={performSearch} onSelect={(uuid) => openProfile(uuid)}
                onBack={() => { setProfileUuid(""); setStatusMessage(""); }} />
            )}
            {page === "settings" && <SettingsPage settings={settings} update={setSettings} />}
            {page === "admin" && (
              <AdminPage
                token={adminToken} catalog={catalog} loading={adminLoading} status={statusMessage}
                logs={logRows} matches={matchRows} showPassword={showAdminPassword}
                onShowPassword={setShowAdminPassword} onLogin={doAdminLogin} onLogout={doAdminLogout}
                onAction={sendAdminAction} onMatchRows={setMatchRows} />
            )}
          </div>
        </main>
      </div>
      <footer className="site-footer">
        <span><span className="footer-dot" /> GrindPvP rankings are updated live</span>
        <span>One community. One leaderboard.</span>
      </footer>
    </div>
  );
}

function KitSidebar({ selectedKit, selectKit }: { selectedKit: string; selectKit: (kit: string) => void }) {
  const renderKit = (kit: string) => {
    const Icon = KIT_ICONS[kit] || Swords;
    return (
      <button key={kit} type="button" data-sound-handled className={`kit-link ${selectedKit === kit ? "selected" : ""}`}
        onClick={() => selectKit(kit)} title={displayKit(kit)}>
        <Icon size={16} strokeWidth={1.8} /><span>{displayKit(kit)}</span>
        {selectedKit === kit && <span className="kit-active-dot" />}
      </button>
    );
  };
  return (
    <aside className="kit-sidebar" aria-label="Ranked kits">
      <div className="sidebar-heading"><span className="live-indicator" /> Ranked kits</div>
      {renderKit("overall")}
      <div className="kit-group-label">MAIN KITS</div>
      {MAIN_KITS.map(renderKit)}
      <div className="kit-group-label sub-label">SUB KITS</div>
      {SUB_KITS.map(renderKit)}
      <div className="sidebar-foot">
        <div className="sidebar-foot-icon"><Activity size={17} /></div>
        <span><strong>Ranked season</strong><small>Live rankings</small></span>
        <ArrowDownRight size={14} className="side-arrow" />
      </div>
    </aside>
  );
}

function PageHeading({ eyebrow, title, subtitle, right }: {
  eyebrow: string; title: string; subtitle: string; right?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow"><span className="eyebrow-line" />{eyebrow}</div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {right && <div className="heading-actions">{right}</div>}
    </div>
  );
}

function LeaderboardView({ catalog, kit, page, data, loading, error, tierColor: color,
  onPage, onProfile, totalPlayers, play }: {
  catalog: Catalog | null; kit: string; page: number; data: PageResult<LeaderboardEntry> | null;
  loading: boolean; error: string; tierColor: (tier: string) => string; onPage: (page: number) => void;
  onProfile: (uuid: string) => void; totalPlayers: number; play: (kind: "click" | "hover") => void;
}) {
  const rows = data?.items || [];
  const top = rows.filter((entry) => entry.rank <= 3);
  const pages = Math.max(1, Math.ceil((data?.total || 0) / PAGE_SIZE));
  return (
    <>
      <PageHeading eyebrow="COMPETITIVE RANKINGS" title="Leaderboard"
        subtitle="The players setting the pace across every ranked kit."
        right={<span className="live-pill"><i /> Live database</span>} />
      <section className="hero-strip">
        <div className="hero-text">
          <span className="hero-kicker">CURRENT VIEW</span>
          <strong>{displayKit(kit)} <span>rankings</span></strong>
          <small>Verified players · Updated from GrindPvP</small>
        </div>
        <div className="hero-stats">
          <div><UsersRound size={17} /><span><b>{totalPlayers.toLocaleString()}</b><small>ranked players</small></span></div>
          <div><Medal size={17} /><span><b>{kit === "overall" ? "14" : catalog?.tiers.length || "11"}</b><small>{kit === "overall" ? "ranked kits" : "rank tiers"}</small></span></div>
        </div>
        <div className="hero-decoration"><span /><span /><span /></div>
      </section>

      {error && <Notice message={error} />}
      <section className="podium-section">
        <div className="section-title-row"><div><h2>Top competitors</h2><p>Leading the {displayKit(kit)} board</p></div>
          <span className="season-label"><Trophy size={14} /> TOP 3</span></div>
        {loading ? <div className="podium-grid">{[1, 2, 3].map((n) => <Skeleton key={n} className="podium-skeleton" />)}</div>
          : <div className="podium-grid">
            {[2, 1, 3].map((rank) => {
              const entry = top.find((item) => item.rank === rank);
              return <PodiumCard key={rank} entry={entry} rank={rank}
                color={entry ? color(entry.tier) : "#86888d"} onClick={() => entry && onProfile(entry.uuid)} />;
            })}
          </div>}
      </section>

      <section className="panel leaderboard-panel">
        <div className="panel-heading">
          <div><h2>All competitors</h2><p>{data?.total ?? "—"} verified players on this board</p></div>
          <div className="table-kit-label"><span className="table-kit-icon">{(() => {
            const Icon = KIT_ICONS[kit] || Trophy; return <Icon size={15} />;
          })()}</span>{displayKit(kit)}<ChevronDown size={14} /></div>
        </div>
        <div className="table-scroll">
          <table className="player-table">
            <thead><tr><th>RANK</th><th>PLAYER</th><th>TIER</th><th>POINTS</th><th>W / L</th><th>WIN RATE</th><th /></tr></thead>
            <tbody>
              {loading ? Array.from({ length: 7 }, (_, index) => <SkeletonRow key={index} />)
                : rows.length ? rows.map((entry) => (
                  <tr key={entry.uuid} className="player-row" onClick={() => onProfile(entry.uuid)} tabIndex={0}
                    onKeyDown={(event) => event.key === "Enter" && onProfile(entry.uuid)}>
                    <td><RankValue rank={entry.rank} /></td>
                    <td><div className="table-player"><img src={avatarUrl(entry.uuid, false)} alt="" loading="lazy" />
                      <span><strong>{entry.username}</strong><small>{entry.role_name ? `${entry.role_name} · ` : ""}{entry.title_name || "GrindPvP player"}</small></span>
                      {entry.title_name && <BadgeCheck size={14} className="verified-mark" />}</div></td>
                    <td><TierBadge name={entry.tier} color={color(entry.tier)} /></td>
                    <td className="points-cell">{(entry.points ?? entry.average_points ?? 0).toFixed(entry.average_points !== undefined ? 2 : 0)}
                      {entry.average_points !== undefined && <small> avg</small>}</td>
                    <td className="muted-cell">{entry.wins !== undefined ? `${entry.wins} / ${entry.losses ?? 0}` : "—"}</td>
                    <td>{entry.winrate !== undefined ? <span className="winrate"><span className="winrate-track"><i style={{ width: `${Math.min(100, Math.max(0, entry.winrate))}%` }} /></span>{entry.winrate}%</span> : <span className="muted-cell">—</span>}</td>
                    <td><ArrowRight size={15} className="row-arrow" /></td>
                  </tr>
                )) : <tr><td colSpan={7}><EmptyState icon={Trophy} title="No rankings yet"
                  message="Verified GrindPvP players will appear here as soon as they have rankings." /></td></tr>}
            </tbody>
          </table>
        </div>
        <Pagination page={page} pages={pages} total={data?.total || 0} onPage={(next) => {
          play("click");
          onPage(next);
        }} />
      </section>
    </>
  );
}

function PodiumCard({ entry, rank, color, onClick }: {
  entry?: LeaderboardEntry; rank: number; color: string; onClick: () => void;
}) {
  const order = rank === 1 ? "first" : rank === 2 ? "second" : "third";
  return (
    <button type="button" disabled={!entry} className={`podium-card ${order}`} onClick={onClick}>
      <div className="podium-card-top">
        <div className="podium-rank">{rank === 1 ? <Crown size={17} /> : `0${rank}`}</div>
        <span className="podium-arrow"><ArrowRight size={15} /></span>
      </div>
      {entry ? <>
        <img className="podium-avatar" src={avatarUrl(entry.uuid, false)} alt="" />
        <span className="podium-username">{entry.username}</span>
        <span className="podium-tier" style={{ color, borderColor: `${color}50`, background: `${color}12` }}>{entry.tier}</span>
        <span className="podium-points">{(entry.points ?? entry.average_points ?? 0).toFixed(entry.average_points !== undefined ? 2 : 0)}
          <small>{entry.average_points !== undefined ? "avg pts" : "points"}</small></span>
      </> : <span className="podium-empty">Waiting for a ranked player</span>}
      <div className="podium-glow" />
    </button>
  );
}

function ProfilesPage(props: {
  profile: Player | null; loading: boolean; uuid: string; matches: PageResult<MatchRecord> | null;
  catalog: Catalog | null; error: string; searchValue: string; searchResults: Player[]; searching: boolean;
  searchError: string; onSearchValue: (value: string) => void; onSearch: (event?: FormEvent) => void;
  onSelect: (uuid: string) => void; onBack: () => void;
}) {
  if (props.uuid) return <ProfileDetail title="Player profile" subtitle="Competitive stats and kit rankings."
    profile={props.profile} loading={props.loading} matches={props.matches} catalog={props.catalog}
    error={props.error} onBack={props.onBack} />;
  return (
    <>
      <PageHeading eyebrow="THE COMMUNITY" title="Find a player"
        subtitle="Search verified competitors and explore their full ranked profile." />
      <div className="search-hero">
        <div className="search-visual"><div className="search-orbit orbit-one" /><div className="search-orbit orbit-two" />
          <UsersRound size={32} /></div>
        <div className="search-copy"><span className="hero-kicker">PLAYER DIRECTORY</span>
          <h2>Every match starts<br />with a name.</h2><p>Find a verified player by their in-game Minecraft username.</p></div>
        <form className="player-search" onSubmit={props.onSearch}>
          <label htmlFor="player-query">Minecraft username</label>
          <div className="search-control"><Search size={17} />
            <input id="player-query" value={props.searchValue} maxLength={16} placeholder="e.g. PlayerName"
              onChange={(event) => props.onSearchValue(event.target.value)} />
            <button className="button-primary" type="submit" disabled={props.searching}>
              {props.searching ? <LoaderCircle size={16} className="spin" /> : "Search"}
            </button>
          </div>
          <small>Search only shows players verified in GrindPvP.</small>
        </form>
      </div>
      {props.searchError && <Notice message={props.searchError} />}
      <div className="search-result-heading">
        <div><h2>{props.searchResults.length ? "Search results" : "Discover players"}</h2>
          <p>{props.searchResults.length ? `${props.searchResults.length} verified ${props.searchResults.length === 1 ? "player" : "players"} found` : "Search for a username to see player profiles."}</p></div>
      </div>
      {props.searchResults.length > 0 && <div className="profile-results-grid">
        {props.searchResults.map((player, index) => <button type="button" className="profile-result-card"
          key={player.uuid} style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }} onClick={() => props.onSelect(player.uuid)}>
          <img src={avatarUrl(player.uuid, false)} alt="" />
          <span className="result-player-name">{player.username}<BadgeCheck size={14} /></span>
          <span className="result-tier" style={{ color: tierColor(player.overall_tier, props.catalog?.tiers || []) }}>
            {player.overall_tier} <small>overall</small></span>
          <span className="result-points">{player.overall_average_points.toFixed(2)} avg points</span>
          <ArrowRight size={16} className="result-arrow" />
        </button>)}
      </div>}
    </>
  );
}

function ProfilePage({ title, subtitle, profile, loading, uuid, matches, catalog, error, searchValue,
  searchResults, searching, searchError, onSearchValue, onSearch, onSelect, onChangeProfile }: {
  title: string; subtitle: string; profile: Player | null; loading: boolean; uuid: string;
  matches: PageResult<MatchRecord> | null; catalog: Catalog | null; error: string;
  searchValue: string; searchResults: Player[]; searching: boolean; searchError: string;
  onSearchValue: (value: string) => void; onSearch: (event?: FormEvent) => void;
  onSelect: (uuid: string) => void; onChangeProfile: () => void;
}) {
  if (profile || loading) return <ProfileDetail title={title} subtitle={subtitle} profile={profile} loading={loading}
    matches={matches} catalog={catalog} error={error} />;
  return (
    <>
      <PageHeading eyebrow="YOUR PLAYER CARD" title={title} subtitle={subtitle} />
      <div className="my-profile-empty panel">
        <div className="my-empty-art"><div className="empty-ring"><UserRound size={31} /></div><span /><span /></div>
        <div className="my-empty-content">
          <span className="hero-kicker">{uuid ? "PROFILE LOOKUP" : "CONNECT YOUR PROFILE"}</span>
          <h2>Bring your stats<br />into the spotlight.</h2>
          <p>Enter your Minecraft username to find the verified player record linked to the shared GrindPvP rankings.</p>
          <form onSubmit={onSearch} className="my-profile-search">
            <div className="search-control"><Search size={16} /><input value={searchValue} maxLength={16}
              placeholder="Your Minecraft username" onChange={(event) => onSearchValue(event.target.value)} />
              <button type="submit" className="button-primary" disabled={searching}>
                {searching ? <LoaderCircle size={16} className="spin" /> : "Find profile"}
              </button></div>
          </form>
          {searchError && <p className="inline-error">{searchError}</p>}
          {searchResults.length > 0 && <div className="my-search-results">
            <span className="field-label">SELECT YOUR VERIFIED ACCOUNT</span>
            {searchResults.map((player) => <button key={player.uuid} type="button" className="my-result"
              onClick={() => onSelect(player.uuid)}><img src={avatarUrl(player.uuid, false)} alt="" />
              <strong>{player.username}</strong><span>{player.overall_tier}</span><ArrowRight size={15} /></button>)}
          </div>}
          <div className="privacy-note"><CircleHelp size={15} /> Profile selection is saved only in this browser.</div>
          {error && <Notice message={error} />}
          <button type="button" className="text-button" onClick={onChangeProfile}>Choose a different profile <ChevronRight size={14} /></button>
        </div>
      </div>
    </>
  );
}

function ProfileDetail({ title, subtitle, profile, loading, matches, catalog, error, onBack }: {
  title: string; subtitle: string; profile: Player | null; loading: boolean;
  matches: PageResult<MatchRecord> | null; catalog: Catalog | null; error: string; onBack?: () => void;
}) {
  const [skinFailed, setSkinFailed] = useState(false);
  useEffect(() => setSkinFailed(false), [profile?.uuid]);
  return (
    <>
      <PageHeading eyebrow={title.toUpperCase()} title={profile?.username || title}
        subtitle={profile ? subtitle : "Verified GrindPvP player overview."}
        right={onBack ? <button className="button-quiet" type="button" onClick={onBack}><ChevronLeft size={16} /> Back to search</button> : null} />
      {error && <Notice message={error} />}
      {loading ? <ProfileSkeleton /> : profile ? <>
        <section className="profile-hero panel">
          <div className="profile-art">
            {!skinFailed ? <img key={profile.uuid} src={avatarUrl(profile.uuid)} alt={`${profile.username}'s Minecraft skin`}
              onError={() => setSkinFailed(true)} /> : <img src={avatarUrl(profile.uuid, false)} alt={`${profile.username}'s Minecraft avatar`} />}
            <span className="skin-caption">PLAYER SKIN</span>
          </div>
          <div className="profile-identity">
            <div className="profile-badges">
              {profile.verified && <span className="verified-pill"><BadgeCheck size={13} /> Verified</span>}
              <span className="profile-id">UUID · {profile.uuid.slice(0, 8)}…</span>
            </div>
            <h2>{profile.username}</h2>
            <div className="profile-role-row">
              {profile.role_name && <span className="role-pill" style={{ color: roleColor(profile.role_name, catalog) }}>{profile.role_name}</span>}
              {profile.title_name && <span className="title-pill">{profile.title_name}</span>}
            </div>
            <div className="profile-overall-row">
              <TierBadge name={profile.overall_tier} color={tierColor(profile.overall_tier, catalog?.tiers || [])} large />
              <span className="overall-score"><b>{profile.overall_average_points.toFixed(2)}</b><small>overall average points</small></span>
            </div>
          </div>
          <div className="profile-summary-stats">
            <StatCard label="Total wins" value={profile.kits.reduce((sum, kit) => sum + kit.wins, 0).toLocaleString()} icon={Trophy} />
            <StatCard label="Matches played" value={profile.kits.reduce((sum, kit) => sum + kit.matches, 0).toLocaleString()} icon={Swords} />
            <StatCard label="Kits ranked" value={profile.kits.filter((kit) => kit.tier !== "Unranked").length.toString()} icon={Activity} />
          </div>
          <div className="profile-glow" />
        </section>

        <div className="profile-content-grid">
          <section className="panel kit-stats-panel">
            <div className="panel-heading"><div><h2>Kit statistics</h2><p>All main kits and sub kits</p></div><span className="panel-count">{profile.kits.length} KITS</span></div>
            <div className="kit-stats-list">
              {profile.kits.map((kit) => {
                const Icon = KIT_ICONS[kit.kit] || Swords;
                return <div key={kit.kit} className="kit-stat-row">
                  <span className="kit-stat-icon"><Icon size={17} /></span>
                  <span className="kit-stat-name">{displayKit(kit.kit)}<small>{kit.matches} matches</small></span>
                  <TierBadge name={kit.tier} color={tierColor(kit.tier, catalog?.tiers || [])} />
                  <span className="kit-stat-record"><b>{kit.wins}</b><small>W</small><span>/</span><b>{kit.losses}</b><small>L</small></span>
                  <span className="kit-stat-winrate"><b>{kit.winrate.toFixed(1)}%</b><small>win rate</small></span>
                  <span className="kit-stat-points">{kit.points}<small>pts</small></span>
                </div>;
              })}
            </div>
            <TierLegend tiers={catalog?.tiers || []} />
          </section>
          <section className="panel match-history-panel">
            <div className="panel-heading"><div><h2>Recent matches</h2><p>Latest results for this player</p></div><ClipboardList size={17} className="panel-heading-icon" /></div>
            {matches?.items.length ? <div className="match-list">{matches.items.map((match) => {
              const won = match.winner_uuid.toLowerCase() === profile.uuid.toLowerCase();
              return <div key={match.id} className="match-item">
                <span className={`match-result ${won ? "won" : "lost"}`}>{won ? "W" : "L"}</span>
                <span className="match-info"><b>{displayKit(match.kit)}</b><small>{formatDate(match.created_at)}</small></span>
                <span className="match-tiers"><span>{won ? match.winner_tier_before : match.loser_tier_before}</span><ArrowRight size={12} />
                  <b style={{ color: tierColor(won ? match.winner_tier_after : match.loser_tier_after, catalog?.tiers || []) }}>
                    {won ? match.winner_tier_after : match.loser_tier_after}</b></span>
              </div>;
            })}</div> : <div className="empty-matches"><ClipboardList size={21} /><span>No match history available</span>
              <small>Matches appear here after an admin records a result.</small></div>}
          </section>
        </div>
      </> : <div className="panel"><EmptyState icon={UserRound} title="Profile unavailable"
        message="This player profile is not available in the shared GrindPvP database." /></div>}
    </>
  );
}

function SettingsPage({ settings, update }: { settings: Settings; update: (next: Settings) => void }) {
  const set = (key: keyof Settings, value: boolean | number) => update({ ...settings, [key]: value });
  return (
    <>
      <PageHeading eyebrow="PREFERENCES" title="Settings" subtitle="Tune your GrindPvP experience. Preferences are saved on this device." />
      <div className="settings-layout">
        <section className="panel settings-panel">
          <div className="panel-heading"><div><h2>Experience</h2><p>Motion and sound preferences</p></div><Settings2 size={18} className="panel-heading-icon" /></div>
          <SettingToggle icon={Activity} title="Interface animations" description="Smooth page transitions and staggered content reveals."
            checked={settings.animations} onChange={(value) => set("animations", value)} />
          <SettingToggle icon={AudioLines} title="Interface sounds" description="Play gentle tones for navigation and actions."
            checked={settings.sounds} onChange={(value) => set("sounds", value)} />
          <SettingToggle icon={Waves} title="Hover sounds" description="Add a subtle tone when hovering over interactive elements."
            checked={settings.hoverSounds} onChange={(value) => set("hoverSounds", value)} />
          <div className="setting-volume">
            <div className="setting-icon"><AudioLines size={17} /></div>
            <div className="setting-description"><strong>Sound volume</strong><small>Adjust the interface sound level.</small></div>
            <span className="volume-value">{settings.volume}%</span>
            <input aria-label="Sound volume" type="range" min="0" max="60" step="1" value={settings.volume}
              onChange={(event) => set("volume", Number(event.target.value))} style={{ "--range-progress": `${(settings.volume / 60) * 100}%` } as React.CSSProperties} />
          </div>
        </section>
        <aside className="settings-aside">
          <div className="settings-note"><div className="settings-note-icon"><Moon size={18} /></div>
            <h3>Built for focus.</h3><p>Your preferences stay in this browser and never affect your rankings or account data.</p>
          </div>
          <div className="settings-note settings-note-accent"><div className="settings-note-icon"><Shield size={18} /></div>
            <h3>One shared source.</h3><p>Website and Minecraft mod read the same live GrindPvP backend.</p>
          </div>
        </aside>
      </div>
    </>
  );
}

function AdminPage({ token, catalog, loading, status, logs, matches, showPassword, onShowPassword, onLogin,
  onLogout, onAction, onMatchRows }: {
  token: string; catalog: Catalog | null; loading: boolean; status: string; logs: PageResult<AdminLog> | null;
  matches: PageResult<MatchRecord> | null; showPassword: boolean; onShowPassword: (show: boolean) => void;
  onLogin: (event: FormEvent<HTMLFormElement>) => void; onLogout: () => void;
  onAction: <T,>(path: string, body: unknown) => Promise<T>;
  onMatchRows: (rows: PageResult<MatchRecord>) => void;
}) {
  const [busyAction, setBusyAction] = useState("");
  const [matchSearch, setMatchSearch] = useState("");
  const [matchQuery, setMatchQuery] = useState("");
  const [matchSearchError, setMatchSearchError] = useState("");
  const [matchSearchBusy, setMatchSearchBusy] = useState(false);
  const roleOptions = catalog?.roles || [];
  const titleOptions = catalog?.titles || [];
  const kitOptions = catalog?.kits || [];
  const tierOptions = catalog?.tiers || [];

  const submit = async (event: FormEvent<HTMLFormElement>, action: string, path: string,
    makeBody: (form: FormData) => unknown) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusyAction(action);
    try {
      await onAction(path, makeBody(form));
      if (action === "match") formElement.reset();
    } catch {
      // The shared action handler exposes API errors in the admin status panel.
    } finally {
      setBusyAction("");
    }
  };

  const searchAdminMatches = async (event: FormEvent) => {
    event.preventDefault();
    setMatchSearchBusy(true);
    setMatchSearchError("");
    try {
      const endpoint = matchSearch.trim()
        ? `/admin/matches?${query({ username: matchSearch.trim(), page: 1, page_size: 10 })}`
        : `/admin/matches?${query({ page: 1, page_size: 10 })}`;
      const result = await api<PageResult<MatchRecord>>(endpoint, { token });
      setMatchQuery(matchSearch.trim());
      onMatchRows(result);
    } catch (error) {
      setMatchSearchError((error as Error).message);
    } finally {
      setMatchSearchBusy(false);
    }
  };

  if (!token) {
    return (
      <>
        <PageHeading eyebrow="RESTRICTED ACCESS" title="Admin panel" subtitle="Manage verified players, ranks, and match results." />
        <div className="admin-login-wrap">
          <section className="admin-login-card panel">
            <div className="admin-lock-mark"><Shield size={23} /></div>
            <span className="hero-kicker">ADMINISTRATOR ACCESS</span>
            <h2>Welcome back.</h2><p>Enter the existing admin access code to open the control panel.</p>
            <form onSubmit={onLogin}>
              <label htmlFor="admin-password">Access code</label>
              <div className="password-control"><input id="admin-password" name="password"
                type={showPassword ? "text" : "password"} autoComplete="current-password" maxLength={256}
                placeholder="Enter access code" required />
                <button type="button" aria-label={showPassword ? "Hide access code" : "Show access code"}
                  onClick={() => onShowPassword(!showPassword)}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
              <button type="submit" className="button-primary full-width" disabled={loading}>
                {loading ? <LoaderCircle size={16} className="spin" /> : <><LogIn size={16} /> Sign in securely</>}
              </button>
            </form>
            {status && <Notice message={status} />}
            <div className="secure-caption"><Shield size={13} /> Authenticated by the GrindPvP backend · Access code is not stored</div>
          </section>
          <div className="admin-login-side"><div className="admin-login-pattern"><Crown size={30} /></div>
            <span>CONTROL CENTER</span><h3>Keep the rankings<br />running true.</h3>
            <p>Manage the competitive ecosystem using the same secure backend as the Minecraft mod.</p>
          </div>
        </div>
      </>
    );
  }

  const playerIdentifier = (form: FormData) => ({ username: String(form.get("username") || "").trim() });
  return (
    <>
      <PageHeading eyebrow="CONTROL CENTER" title="Admin panel" subtitle="Manage players and competitive results."
        right={<button type="button" className="button-quiet logout-button" onClick={onLogout}><LogOut size={15} /> Sign out</button>} />
      {status && <Notice message={status} />}
      <div className="admin-layout">
        <div className="admin-actions-column">
          <AdminSection title="Player management" subtitle="Create, verify, assign roles and titles." icon={UsersRound}>
            <form className="admin-form" onSubmit={(event) => submit(event, "player", "/admin/players", playerIdentifier)}>
              <label>Minecraft username<input name="username" required minLength={3} maxLength={16} pattern="[A-Za-z0-9_]+" placeholder="PlayerName" /></label>
              <button type="submit" className="button-primary" disabled={busyAction === "player"}>
                {busyAction === "player" ? <LoaderCircle size={15} className="spin" /> : "Create / update"}
              </button>
            </form>
            <form className="admin-form" onSubmit={(event) => submit(event, "verify", "/admin/verify",
              (form) => ({ ...playerIdentifier(form), verified: form.get("verified") === "true" }))}>
              <label>Player<input name="username" required minLength={3} maxLength={16} placeholder="PlayerName" /></label>
              <label>Verification<select name="verified"><option value="true">Verify</option><option value="false">Unverify</option></select></label>
              <button type="submit" className="button-secondary" disabled={busyAction === "verify"}>Apply</button>
            </form>
            <form className="admin-form" onSubmit={(event) => submit(event, "role", "/admin/roles",
              (form) => ({ ...playerIdentifier(form), role: String(form.get("role") || "") || null }))}>
              <label>Player<input name="username" required minLength={3} maxLength={16} placeholder="PlayerName" /></label>
              <label>Role<select name="role"><option value="">Remove role</option>{roleOptions.map((role) =>
                <option key={role.name} value={role.name}>{role.name}</option>)}</select></label>
              <button type="submit" className="button-secondary" disabled={busyAction === "role"}>Set role</button>
            </form>
            <form className="admin-form" onSubmit={(event) => submit(event, "title", "/admin/titles",
              (form) => ({ ...playerIdentifier(form), title: String(form.get("title") || "") || null }))}>
              <label>Player<input name="username" required minLength={3} maxLength={16} placeholder="PlayerName" /></label>
              <label>Title<select name="title"><option value="">Remove title</option>{titleOptions.map((title) =>
                <option key={title.name} value={title.name}>{title.name}</option>)}</select></label>
              <button type="submit" className="button-secondary" disabled={busyAction === "title"}>Set title</button>
            </form>
          </AdminSection>
          <AdminSection title="Rank & stats" subtitle="Set a player's kit tier or correct recorded stats." icon={Medal}>
            <form className="admin-form" onSubmit={(event) => submit(event, "tier", "/admin/tiers",
              (form) => ({ ...playerIdentifier(form), kit: form.get("kit"), tier: String(form.get("tier") || "") || null }))}>
              <label>Player<input name="username" required minLength={3} maxLength={16} placeholder="PlayerName" /></label>
              <label>Kit<select name="kit">{kitOptions.map((kit) => <option key={kit} value={kit}>{displayKit(kit)}</option>)}</select></label>
              <label>Tier<select name="tier"><option value="">Unranked</option>{tierOptions.filter((tier) => tier.name !== "Unranked").map((tier) =>
                <option key={tier.name} value={tier.name}>{tier.name}</option>)}</select></label>
              <button type="submit" className="button-secondary" disabled={busyAction === "tier"}>Set tier</button>
            </form>
            <form className="admin-form stats-form" onSubmit={(event) => submit(event, "stats", "/admin/stats",
              (form) => ({ ...playerIdentifier(form), kit: form.get("kit"),
                wins: Number(form.get("wins")), losses: Number(form.get("losses")) }))}>
              <label>Player<input name="username" required minLength={3} maxLength={16} placeholder="PlayerName" /></label>
              <label>Kit<select name="kit">{kitOptions.map((kit) => <option key={kit} value={kit}>{displayKit(kit)}</option>)}</select></label>
              <label>Wins<input name="wins" type="number" min="0" max="1000000" required defaultValue="0" /></label>
              <label>Losses<input name="losses" type="number" min="0" max="1000000" required defaultValue="0" /></label>
              <button type="submit" className="button-secondary" disabled={busyAction === "stats"}>Save stats</button>
            </form>
          </AdminSection>
          <AdminSection title="Record a match" subtitle="Submit a confirmed match to update both players' rankings." icon={Swords}>
            <form className="admin-form match-submit-form" onSubmit={(event) => submit(event, "match", "/admin/matches",
              (form) => ({ idempotency_key: `website:${crypto.randomUUID()}`, kit: form.get("kit"),
                winner_username: String(form.get("winner") || "").trim(), loser_username: String(form.get("loser") || "").trim() }))}>
              <label>Ranked kit<select name="kit" required>{kitOptions.map((kit) => <option key={kit} value={kit}>{displayKit(kit)}</option>)}</select></label>
              <div className="match-form-players">
                <label>Winner<input name="winner" required minLength={3} maxLength={16} pattern="[A-Za-z0-9_]+" placeholder="Winner name" /></label>
                <span className="match-vs">VS</span>
                <label>Loser<input name="loser" required minLength={3} maxLength={16} pattern="[A-Za-z0-9_]+" placeholder="Loser name" /></label>
              </div>
              <button type="submit" className="button-primary" disabled={busyAction === "match"}>
                {busyAction === "match" ? <LoaderCircle size={15} className="spin" /> : <><Check size={15} /> Submit result</>}
              </button>
            </form>
          </AdminSection>
        </div>
        <div className="admin-data-column">
          <section className="panel admin-data-panel">
            <div className="panel-heading"><div><h2>Recent matches</h2><p>{matchQuery ? `Filtered for ${matchQuery}` : "Latest recorded results"}</p></div><Swords size={17} className="panel-heading-icon" /></div>
            <form className="admin-match-search" onSubmit={searchAdminMatches}>
              <input value={matchSearch} maxLength={16} placeholder="Filter by player"
                onChange={(event) => setMatchSearch(event.target.value)} />
              <button type="submit" aria-label="Filter matches" disabled={matchSearchBusy}>
                {matchSearchBusy ? <LoaderCircle size={15} className="spin" /> : <Search size={15} />}
              </button>
            </form>
            {matchSearchError && <p className="inline-error">{matchSearchError}</p>}
            <div className="admin-match-list">{matches?.items.length ? matches.items.map((match) =>
              <div key={match.id} className="admin-match-row"><span className="admin-match-kit">{displayKit(match.kit)}</span>
                <span className="admin-match-tiers"><b>{match.winner_tier_before}</b><ArrowRight size={12} />{match.winner_tier_after}</span>
                <span className="admin-match-time">{formatDate(match.created_at)}</span></div>)
              : <div className="admin-empty">No matches found.</div>}</div>
          </section>
          <section className="panel admin-data-panel logs-panel">
            <div className="panel-heading"><div><h2>Admin activity</h2><p>Audited changes from this shared backend</p></div><ClipboardList size={17} className="panel-heading-icon" /></div>
            <div className="admin-log-list">{logs?.items.length ? logs.items.map((log) =>
              <div key={log.id} className="admin-log-row"><span className="log-icon"><Activity size={14} /></span>
                <span className="log-detail"><b>{log.action.replaceAll(".", " ")}</b><small>{log.target_uuid ? `${log.target_uuid.slice(0, 8)}…` : "System"} · {formatDate(log.created_at)}</small></span>
              </div>) : <div className="admin-empty">No recent activity.</div>}</div>
          </section>
          <div className="admin-security-note"><Shield size={15} /><span>Actions are applied directly to the shared GrindPvP database and recorded in the admin audit log.</span></div>
        </div>
      </div>
    </>
  );
}

function AdminSection({ title, subtitle, icon: Icon, children }: {
  title: string; subtitle: string; icon: LucideIcon; children: ReactNode;
}) {
  return <section className="panel admin-section"><div className="admin-section-heading">
    <div className="admin-section-icon"><Icon size={17} /></div><div><h2>{title}</h2><p>{subtitle}</p></div>
  </div>{children}</section>;
}

function SettingToggle({ icon: Icon, title, description, checked, onChange }: {
  icon: LucideIcon; title: string; description: string; checked: boolean; onChange: (value: boolean) => void;
}) {
  return <div className="setting-row"><div className="setting-icon"><Icon size={17} /></div>
    <div className="setting-description"><strong>{title}</strong><small>{description}</small></div>
    <button type="button" role="switch" aria-label={title} aria-checked={checked} className={`switch ${checked ? "on" : ""}`}
      onClick={() => onChange(!checked)}><span /></button></div>;
}

function StatCard({ label, value, icon: Icon }: { label: string; value: string; icon: LucideIcon }) {
  return <div className="profile-stat-card"><span className="profile-stat-icon"><Icon size={15} /></span>
    <small>{label}</small><strong>{value}</strong></div>;
}

function TierBadge({ name, color, large = false }: { name: string; color: string; large?: boolean }) {
  return <span className={`tier-badge ${large ? "large" : ""}`} style={{ color, borderColor: `${color}45`, background: `${color}12` }}>
    <i style={{ backgroundColor: color }} />{name}</span>;
}

function RankValue({ rank }: { rank: number }) {
  return <span className={`rank-value ${rank <= 3 ? `rank-${rank}` : ""}`}>
    {rank <= 3 ? <Medal size={16} /> : `#${rank.toString().padStart(2, "0")}`}
  </span>;
}

function Pagination({ page, pages, total, onPage }: {
  page: number; pages: number; total: number; onPage: (page: number) => void;
}) {
  return <div className="pagination">
    <span>Showing <b>{total ? (page - 1) * PAGE_SIZE + 1 : 0}–{Math.min(page * PAGE_SIZE, total)}</b> of <b>{total}</b></span>
    <div><button type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft size={16} /></button>
      <span className="page-count">{page} <small>/ {pages}</small></span>
      <button type="button" aria-label="Next page" disabled={page >= pages} onClick={() => onPage(page + 1)}><ChevronRight size={16} /></button></div>
  </div>;
}

function TierLegend({ tiers }: { tiers: TierDefinition[] }) {
  return <div className="tier-legend"><span>RANK POINTS</span>{tiers.map((tier) =>
    <span key={tier.name} title={`${tier.name}: ${tier.points} points`}><i style={{ backgroundColor: tier.color }} />{tier.name}<b>{tier.points}</b></span>)}</div>;
}

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

function SkeletonRow() {
  return <tr className="skeleton-row"><td><Skeleton /></td><td><Skeleton /></td><td><Skeleton /></td>
    <td><Skeleton /></td><td><Skeleton /></td><td><Skeleton /></td><td /></tr>;
}

function ProfileSkeleton() {
  return <><div className="panel profile-skeleton"><Skeleton className="skeleton-skin" /><div><Skeleton /><Skeleton /><Skeleton /></div></div>
    <div className="panel profile-skeleton-list">{[1, 2, 3, 4].map((index) => <Skeleton key={index} />)}</div></>;
}

function EmptyState({ icon: Icon, title, message }: { icon: LucideIcon; title: string; message: string }) {
  return <div className="empty-state"><span><Icon size={22} /></span><strong>{title}</strong><p>{message}</p></div>;
}

function Notice({ message }: { message: string }) {
  return <div className="notice" role="status"><CircleHelp size={15} /><span>{message}</span></div>;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {
    dateStyle: "medium", timeStyle: "short",
  });
}

function roleColor(role: string, catalog: Catalog | null) {
  return catalog?.roles.find((item) => item.name === role)?.color || "#ff7a24";
}

export default App;
