import React, { useEffect, useMemo, useState } from "react";

const API_BASE = "https://dracobackend-production-6b8f.up.railway.app";

function prettyCode(code) {
  if (!code) return "Dragon";
  return code.charAt(0).toUpperCase() + code.slice(1).toLowerCase();
}

function formatDate(value) {
  if (!value) return "Henüz collect yok";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

export default function App() {
  const [telegramId, setTelegramId] = useState("");
  const [playerName, setPlayerName] = useState("Dragon Master");
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collecting, setCollecting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    tg?.ready?.();
    tg?.expand?.();

    const tgUser = tg?.initDataUnsafe?.user;
    if (tgUser?.id) {
      setTelegramId(String(tgUser.id));
      setPlayerName(tgUser.first_name || tgUser.username || "Dragon Master");
      return;
    }

    // Telegram dışında önizleme için fallback
    setTelegramId("1525781970");
    setPlayerName("Dragon Master");
  }, []);

  const activeCount = useMemo(() => profile?.dragons?.length || 0, [profile]);

  async function ensureRegistered(id) {
    await fetch(`${API_BASE}/users/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ telegram_id: id })
    });
  }

  async function loadProfile(id) {
    try {
      setLoading(true);
      setError("");

      await ensureRegistered(id);

      const res = await fetch(`${API_BASE}/users/${id}/profile`);
      if (!res.ok) {
        throw new Error(`Profil yüklenemedi (${res.status})`);
      }

      const data = await res.json();
      setProfile(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bilinmeyen hata");
    } finally {
      setLoading(false);
    }
  }

  async function handleCollect() {
    if (!telegramId) return;

    try {
      setCollecting(true);
      setError("");

      const res = await fetch(`${API_BASE}/users/${telegramId}/collect`, {
        method: "POST"
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Collect başarısız (${res.status})`);
      }

      await loadProfile(telegramId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Collect hatası");
    } finally {
      setCollecting(false);
    }
  }

  useEffect(() => {
    if (!telegramId) return;
    loadProfile(telegramId);
  }, [telegramId]);

  return (
    <div className="app-shell">
      <div className="container">
        <div className="card hero-card">
          <div className="hero-top">
            <div>
              <p className="muted">🐉 Draco Kingdom</p>
              <h1>{playerName}</h1>
              <p className="tiny">Telegram ID: {telegramId || "yükleniyor..."}</p>
            </div>
            <div className="stat-badge">
              <span className="tiny">Active Dragons</span>
              <strong>{activeCount}</strong>
            </div>
          </div>

          {loading ? (
            <div className="status-box">Profil yükleniyor...</div>
          ) : error ? (
            <div className="status-box error-box">{error}</div>
          ) : (
            <>
              <div className="stats-grid">
                <div className="stat-card">
                  <p className="muted">🥚 Eggs</p>
                  <h2>{profile?.total_eggs_ay ?? 0}</h2>
                  <p className="tiny">Stored: {profile?.stored_eggs_ay ?? 0}</p>
                </div>

                <div className="stat-card">
                  <p className="muted">💰 USDT</p>
                  <h2>{profile?.usdt_balance ?? 0}</h2>
                  <p className="tiny">Pending eggs: {profile?.pending_eggs_ay ?? 0}</p>
                </div>
              </div>

              <button
                className="collect-btn"
                onClick={handleCollect}
                disabled={collecting}
              >
                {collecting ? "Collecting..." : "Collect Eggs"}
              </button>

              <p className="tiny last-collect">
                Last collect: {formatDate(profile?.last_collect_at ?? null)}
              </p>
            </>
          )}
        </div>

        <div className="card">
          <div className="section-head">
            <h3>My Dragons</h3>
            <span className="muted">{activeCount} Active</span>
          </div>

          <div className="dragon-list">
            {!loading && !profile?.dragons?.length ? (
              <div className="dragon-item empty-item">Henüz dragon yok.</div>
            ) : (
              profile?.dragons?.map((dragon) => (
                <div key={dragon.id} className="dragon-item">
                  <div className="dragon-row">
                    <div>
                      <p className="dragon-name">{prettyCode(dragon.dragon_code)}</p>
                      <p className="muted">
                        Level {dragon.level} • XP {dragon.xp}
                      </p>
                    </div>
                    <div className="dragon-right">
                      <p className="muted">{dragon.eggs_per_day} eggs/day</p>
                      <p className="days-left">{dragon.remaining_days} days left</p>
                    </div>
                  </div>
                  <div className="tiny pending-line">
                    Pending eggs: {dragon.pending_eggs_ay}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="bottom-grid">
          <button className="nav-card">
            <span className="nav-title">🏪 Market</span>
            <span className="muted">Buy new dragons</span>
          </button>

          <button className="nav-card">
            <span className="nav-title">💸 Withdraw</span>
            <span className="muted">Cash out USDT</span>
          </button>
        </div>
      </div>
    </div>
  );
}
