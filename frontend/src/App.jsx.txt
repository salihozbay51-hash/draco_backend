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
  const [refs, setRefs] = useState(null);
  const [page, setPage] = useState("home");
  const [marketDragons, setMarketDragons] = useState([]);

  async function ensureRegistered(id) {
    await fetch(`${API_BASE}/users/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ telegram_id: id }),
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

  async function loadMarket() {
  try {
    const res = await fetch(`${API_BASE}/market/dragons`);
    if (!res.ok) {
      throw new Error("Market yüklenemedi");
    }

    const data = await res.json();

    // Minik starter-only olduğu için markette gösterme
    const filtered = (data.dragons || []).filter((d) => !d.is_starter_only);
    setMarketDragons(filtered);
  } catch (err) {
    console.error("Market fetch error:", err);
  }
}

  async function buyDragon(code) {
  try {
    const res = await fetch(`${API_BASE}/users/${telegramId}/buy/${code}`, {
      method: "POST",
    });

    const data = await res.json();

    if (!res.ok) {
      alert(data.detail || "Purchase failed");
      return;
    }

    alert(`${prettyCode(data.dragon_code)} başarıyla satın alındı!`);
    await loadProfile(telegramId);
    await loadReferrals(telegramId);
    setPage("home");
  } catch (e) {
    alert("Purchase failed");
  }
}

  async function handleCollect() {
    if (!telegramId) return;

    try {
      setCollecting(true);
      setError("");

      const res = await fetch(`${API_BASE}/users/${telegramId}/collect`, {
        method: "POST",
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Collect başarısız (${res.status})`);
      }

      await loadProfile(telegramId);
      await loadReferrals(telegramId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Collect hatası");
    } finally {
      setCollecting(false);
    }
  }

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

    setTelegramId("1525781970");
    setPlayerName("Dragon Master");
  }, []);

  useEffect(() => {
  if (!telegramId) return;
  loadProfile(telegramId);
  loadReferrals(telegramId);
  loadMarket();
}, [telegramId]);

  const activeCount = useMemo(() => profile?.dragons?.length || 0, [profile]);

  const inviteLink = telegramId
    ? `https://t.me/dracokingdom_bot?start=${telegramId}`
    : "";

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

        {page === "home" && (
          <>
            <div className="dragon-chamber">
              <div className="chamber-title">🔥 Dragon Chamber</div>

              <div className="dragon-grid">
                {profile?.dragons?.map((dragon) => (
                  <div key={dragon.id} className="dragon-card">
                    <strong>🐉 {prettyCode(dragon.dragon_code)}</strong>

                    <div className="muted">Level {dragon.level}</div>

                    <div className="tiny">
                      🥚 {dragon.eggs_per_day} eggs/day
                    </div>

                    <div className="tiny">
                      ⏳ {dragon.remaining_days} days left
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {page === "market" && (
  <div className="dragon-chamber">
    <div className="chamber-title">🏪 Draco Market</div>

    <div className="dragon-grid">
      {marketDragons.map((dragon) => (
        <div key={dragon.code} className="dragon-card">
          <strong>🐉 {prettyCode(dragon.code)}</strong>
          <div className="tiny">🥚 {dragon.eggs_per_day} eggs/day</div>
          <div className="tiny">💰 Price: {dragon.price_usdt} USDT</div>
          <div className="tiny">⏳ {dragon.lifetime_days} days</div>

          <button
            className="collect-main"
            onClick={() => buyDragon(dragon.code)}
          >
            Buy
          </button>
        </div>
      ))}
    </div>

    <button
      className="collect-btn"
      style={{ marginTop: 16 }}
      onClick={() => setPage("home")}
    >
      Back to Home
    </button>
  </div>
)}

        <div className="bottom-grid">
          <button className="nav-card" onClick={() => setPage("market")}>
            <span className="nav-title">🏪 Market</span>
            <span className="muted">Buy new dragons</span>
          </button>

          <button className="nav-card">
            <span className="nav-title">💸 Withdraw</span>
            <span className="muted">Cash out USDT</span>
          </button>
        </div>

        <div className="card">
          <div className="section-head">
            <h3>Invite Friends</h3>
            <span className="muted">Referral System</span>
          </div>

          <div className="dragon-item">
            <p className="muted" style={{ marginBottom: 8 }}>
              Your invite link
            </p>

            <input value={inviteLink} readOnly className="invite-input" />

            <button
              className="collect-btn"
              style={{ marginTop: 12 }}
              onClick={() => {
                if (inviteLink) {
                  navigator.clipboard.writeText(inviteLink);
                }
              }}
            >
              Copy Link
            </button>
          </div>
        </div>

        {refs && (
          <div className="card">
            <div className="section-head">
              <h3>Referrals</h3>
              <span className="muted">3 Levels</span>
            </div>

            <div className="stats-grid">
              <div className="stat-card">
                <p className="muted">Level 1</p>
                <h2>{refs.level1}</h2>
              </div>

              <div className="stat-card">
                <p className="muted">Level 2</p>
                <h2>{refs.level2}</h2>
              </div>

              <div className="stat-card">
                <p className="muted">Level 3</p>
                <h2>{refs.level3}</h2>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}