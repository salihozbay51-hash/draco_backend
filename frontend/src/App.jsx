import React, { useEffect, useMemo, useRef, useState } from "react";

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
  const [withdrawAddress, setWithdrawAddress] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [withdrawHistory, setWithdrawHistory] = useState([]);
  const [depositAmount, setDepositAmount] = useState("");
  const [depositOrder, setDepositOrder] = useState(null);
  const [depositChecking, setDepositChecking] = useState(false);
  const [depositCreating, setDepositCreating] = useState(false);
  const [converting, setConverting] = useState(false);
  const [tgInitData, setTgInitData] = useState("");
  const [musicOn, setMusicOn] = useState(true);
  const [sfxOn, setSfxOn] = useState(true);
  const bgmRef = useRef(null);
  
  function playClick() {
    if (!sfxOn) return;

    const audio = new Audio("/sounds/click.mp3");
    audio.volume = 0.3;
    audio.play().catch(() => {});
  }

  function getAuthHeaders(extra = {}) {
  return {
    ...extra,
    "X-Telegram-Init-Data": tgInitData,
  };
}

  async function ensureRegistered(id) {
  const res = await fetch(`${API_BASE}/users/register`, {
    method: "POST",
    headers: getAuthHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify({ telegram_id: id }),
  });

  if (!res.ok) {
    throw new Error(`Kayıt işlemi başarısız (${res.status})`);
  }
}

  async function loadProfile(id) {
    try {
      setLoading(true);
      setError("");

      await ensureRegistered(id);

      const res = await fetch(`${API_BASE}/users/${id}/profile`, {
        headers: getAuthHeaders(),
      });
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

  async function loadReferrals(id) {
    try {
      const res = await fetch(`${API_BASE}/users/${id}/referrals`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        throw new Error(`Referral bilgisi alınamadı (${res.status})`);
      }

      const data = await res.json();
      setRefs(data);
    } catch (err) {
      console.error("Referral fetch error:", err);
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

  async function loadWithdrawHistory(id) {
    try {
      const res = await fetch(`${API_BASE}/users/${id}/withdraws`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        throw new Error(`Withdraw history alınamadı (${res.status})`);
      }

      const data = await res.json();
      setWithdrawHistory(data.items || []);
    } catch (err) {
      console.error("Withdraw history fetch error:", err);
    }
  }

 async function buyDragon(code) {
  try {
    const res = await fetch(`${API_BASE}/users/${telegramId}/buy/${code}`, {
      method: "POST",
      headers: getAuthHeaders(),
    });

    let data = null;

    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (!res.ok) {
      alert(data?.detail || "Yetersiz bakiye veya satın alma başarısız");
      return;
    }

    alert(`${prettyCode(data?.dragon_code || code)} başarıyla satın alındı!`);
    await loadProfile(telegramId);
    await loadReferrals(telegramId);
    setPage("home");
  } catch (e) {
    alert("Satın alma sırasında bir hata oluştu");
  }
}

  async function handleCollect() {
    if (!telegramId) return;

    try {
      setCollecting(true);
      setError("");

      const res = await fetch(`${API_BASE}/users/${telegramId}/collect`, {
        method: "POST",
        headers: getAuthHeaders(),
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
  
  async function handleConvert() {
  if (!telegramId) return;

  try {
    setError("");
    setConverting(true);

    const res = await fetch(`${API_BASE}/users/${telegramId}/convert`, {
      method: "POST",
      headers: getAuthHeaders(),
    });

    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (!res.ok) {
      throw new Error(
        typeof data?.detail === "string"
          ? data.detail
          : "Convert hatası"
      );
    }

    alert(`Converted: +${data.converted_usdt} USDT`);

    await loadProfile(telegramId);
    await loadReferrals(telegramId);
  } catch (err) {
    setError(err instanceof Error ? err.message : "Convert hatası");
  } finally {
    setConverting(false);
  }
}

  async function handleWithdraw() {
  if (!telegramId) return;

  try {
    setError("");

    const amount = Number(withdrawAmount);

    if (!withdrawAddress.trim()) {
      setError("Cüzdan adresi zorunlu");
      return;
    }

    if (!withdrawAmount.trim()) {
      setError("Miktar zorunlu");
      return;
    }

    if (!Number.isFinite(amount)) {
      setError("Geçerli bir miktar gir");
      return;
    }

    if (amount < 5) {
      setError("Minimum çekim 5 USDT");
      return;
    }

    const res = await fetch(`${API_BASE}/users/${telegramId}/withdraw/request`, {
      method: "POST",
      headers: getAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify({
        address: withdrawAddress,
        amount_usdt: amount,
      }),
    });

    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (!res.ok) {
      throw new Error(
        typeof data?.detail === "string"
          ? data.detail
          : "Withdraw hatası"
      );
    }

    alert("Withdraw talebi gönderildi!");

    setWithdrawAddress("");
    setWithdrawAmount("");

    await loadProfile(telegramId);
    await loadWithdrawHistory(telegramId);
  } catch (err) {
    setError(err instanceof Error ? err.message : "Withdraw hatası");
  }
}

async function createDepositOrder() {
  if (!telegramId) return;

  try {
    setError("");
    setDepositCreating(true);

    const amount = Number(depositAmount);

    if (!depositAmount.trim()) {
      setError("Yükleme miktarı zorunlu");
      return;
    }

    if (!Number.isFinite(amount)) {
      setError("Geçerli bir yükleme miktarı gir");
      return;
    }

    if (amount < 1) {
      setError("Minimum yükleme 1 USDT");
      return;
    }

    const res = await fetch(`${API_BASE}/wallet/deposit/orders`, {
      method: "POST",
      headers: getAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify({
        telegram_id: telegramId,
        amount_usdt: amount,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(
        typeof data?.detail === "string"
          ? data.detail
          : "Deposit order oluşturulamadı"
      );
    }

    setDepositOrder(data);
  } catch (err) {
    setError(err instanceof Error ? err.message : "Deposit oluşturma hatası");
  } finally {
    setDepositCreating(false);
  }
}

async function refreshDepositStatus() {
  if (!depositOrder?.order_id) return;

  try {
    setDepositChecking(true);
    setError("");

    const res = await fetch(
      `${API_BASE}/wallet/deposit/orders/${depositOrder.order_id}`,
      {
        headers: getAuthHeaders(),
      }
    );
    const data = await res.json();

    if (!res.ok) {
      throw new Error(
        typeof data?.detail === "string"
          ? data.detail
          : "Deposit durumu alınamadı"
      );
    }

    setDepositOrder((prev) => ({
      ...(prev || {}),
      ...data,
      order_id: prev?.order_id ?? data.id,
    }));

    if (data.status === "paid") {
      await loadProfile(telegramId);
      alert("Ödeme alındı, bakiyen güncellendi!");
    }
  } catch (err) {
    setError(err instanceof Error ? err.message : "Deposit status hatası");
  } finally {
    setDepositChecking(false);
  }
}

function resetDepositForm() {
  setDepositAmount("");
  setDepositOrder(null);
}

  useEffect(() => {
  const tg = window.Telegram?.WebApp;
  tg?.ready?.();
  tg?.expand?.();

  const tgUser = tg?.initDataUnsafe?.user;
  const initData = tg?.initData || "";
  setTgInitData(initData);

  if (tgUser?.id) {
    setTelegramId(String(tgUser.id));
    setPlayerName(tgUser.first_name || tgUser.username || "Dragon Master");
    return;
  }

  setTelegramId("1525781970");
  setPlayerName("Dragon Master");
}, []);
  
  useEffect(() => {
  if (!bgmRef.current) {
    bgmRef.current = new Audio("/sounds/bgm.mp3");
    bgmRef.current.loop = true;
    bgmRef.current.volume = 0.2;
  }

  if (musicOn) {
    bgmRef.current.play().catch(() => {});
  } else {
    bgmRef.current.pause();
  }
}, [musicOn]);

  useEffect(() => {
    if (!telegramId) return;
    if (!tgInitData) return;

    loadProfile(telegramId);
    loadReferrals(telegramId);
    loadMarket();
    loadWithdrawHistory(telegramId);
  }, [telegramId, tgInitData]);

  useEffect(() => {
  if (!depositOrder?.order_id) return;
  if (depositOrder?.status === "paid" || depositOrder?.status === "expired") return;

  const interval = setInterval(() => {
    refreshDepositStatus();
  }, 10000);

  return () => clearInterval(interval);
}, [depositOrder?.order_id, depositOrder?.status]);

  const activeCount = useMemo(() => profile?.dragons?.length || 0, [profile]);

  const inviteLink = telegramId
    ? `https://t.me/dracokingdom_bot?start=${telegramId}`
    : "";

  return (
    <div className="app-shell">
      <div className="container">
        <div className="card hero-card">
  <div className="hero-top">
    <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
  <button
    className="nav-card"
    onClick={() => setMusicOn((prev) => !prev)}
  >
    {musicOn ? "🎵 Music On" : "🎵 Music Off"}
  </button>

  <button
    className="nav-card"
    onClick={() => setSfxOn((prev) => !prev)}
  >
    {sfxOn ? "🔘 Click On" : "🔘 Click Off"}
  </button>
</div>
    <button
  className="nav-card"
  style={{ marginTop: 12 }}
  onClick={() => {
  playClick();
  setSoundOn((prev) => !prev);
}}
>
  {soundOn ? "🔊 Sound On" : "🔇 Sound Off"}
</button>
    <div>
      <p className="muted">🐉 Draco Kingdom</p>
      <h1>{playerName}</h1>
      <p className="tiny">Telegram ID: {telegramId || "yükleniyor..."}</p>
    </div>
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
            onClick={() => {
              playClick();
              handleCollect();
            }}
            disabled={collecting}
          >
            {collecting ? "Collecting..." : "Collect Eggs"}
          </button>

          <button
            className="collect-btn"
            style={{ marginTop: 10, background: "#facc15", color: "#422006" }}
            onClick={() => {
              playClick();
              handleConvert();
            }}
            disabled={converting}
          >
            {converting ? "Converting..." : "Convert Eggs → USDT"}
          </button>

          <p className="tiny" style={{ marginTop: 8 }}>
            500 eggs = 1 USDT
          </p>

          <p className="tiny last-collect">
            Last collect: {formatDate(profile?.last_collect_at ?? null)}
          </p>
        </>
      )}

      {page === "home" && (
        <>
          <div className="dragon-chamber">
            <div className="chamber-title">🔥 Dragon Chamber</div>

            <div className="dragon-grid">
              {profile?.dragons?.length ? (
                profile.dragons.map((dragon) => (
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
                 ))
               ) : (
                 <div className="tiny">Henüz dragonun yok 🐣</div>
               )}
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
                  onClick={() => {
                    playClick();
                    buyDragon(dragon.code);
                  }}
                >
                  Buy
                </button>
              </div>
            ))}
          </div>

          <button
            className="collect-btn"
            style={{ marginTop: 16 }}
            onClick={() => {
              playClick();
              setPage("home");
            }}
          >
            Back to Home
          </button>
        </div>
      )}

      {page === "deposit" && (
  <div className="dragon-chamber">
    <div className="chamber-title">➕ Deposit USDT</div>

    <div className="dragon-card">
      <div className="tiny">Current balance</div>
      <strong>{profile?.usdt_balance ?? 0} USDT</strong>
    </div>

    {!depositOrder && (
      <>
        <input
          className="invite-input"
          placeholder="Amount (min 1 USDT)"
          style={{ marginTop: 12 }}
          value={depositAmount}
          onChange={(e) => setDepositAmount(e.target.value)}
        />

        <button
          className="collect-btn"
          style={{ marginTop: 12 }}
          onClick={() => {
            playClick();
            createDepositOrder();
          }}
          disabled={depositCreating}
        >
          {depositCreating ? "Creating..." : "Create Deposit Order"}
        </button>
      </>
    )}

    {depositOrder && (
      <div className="dragon-card" style={{ marginTop: 12 }}>
        <div className="tiny">Network</div>
        <strong>{depositOrder.network || "TRON (TRC-20)"}</strong>

        <div className="tiny" style={{ marginTop: 10 }}>Send to address</div>
        <input
          className="invite-input"
          readOnly
          value={depositOrder.pay_to || ""}
          style={{ marginTop: 6 }}
        />

        <button
          className="collect-btn"
          style={{ marginTop: 10 }}
          onClick={async () => {
            playClick();
            try {
              await navigator.clipboard.writeText(depositOrder.pay_to || "");
              alert("Adres kopyalandı!");
            } catch {
              alert("Adres kopyalanamadı");
            }
          }}
        >
          Copy Address
        </button>

        <div className="tiny" style={{ marginTop: 14 }}>Expected payment</div>
        <strong>{depositOrder.expected_amount_usdt} USDT</strong>

        <div className="tiny" style={{ marginTop: 10 }}>Credited amount</div>
        <strong>{depositOrder.credited_amount_usdt} USDT</strong>

        <div className="tiny" style={{ marginTop: 10 }}>Status</div>
        <strong>{depositOrder.status}</strong>

        <div className="tiny" style={{ marginTop: 10 }}>
          Expires: {depositOrder.expires_at ? new Date(depositOrder.expires_at).toLocaleString() : "-"}
        </div>

        {depositOrder.paid_txid && (
          <div className="tiny" style={{ marginTop: 10 }}>
            TXID: {depositOrder.paid_txid}
          </div>
        )}

        <button
          className="collect-btn"
          style={{ marginTop: 12 }}
          onClick={() => {
            playClick();
            refreshDepositStatus();
          }}
          disabled={depositChecking}
        >
          {depositChecking ? "Checking..." : "Check Payment Status"}
        </button>

        {(depositOrder.status === "paid" || depositOrder.status === "expired") && (
          <button
            className="collect-btn"
            style={{ marginTop: 12 }}
            onClick={() => {
              playClick();
              resetDepositForm();
            }}
          >
            New Deposit
          </button>
        )}
      </div>
    )}

    <button
      className="collect-btn"
      style={{ marginTop: 12 }}
      onClick={() => {
        playClick();
        setPage("home");
      }}
    >
      Back to Home
    </button>
  </div>
)}

      {page === "withdraw" && (
  <div className="dragon-chamber">
    <div className="chamber-title">💸 Withdraw</div>

    <div className="dragon-card">
      <div className="tiny">Available balance</div>
      <strong>{profile?.usdt_balance ?? 0} USDT</strong>
    </div>

    <input
      className="invite-input"
      placeholder="Wallet address"
      style={{ marginTop: 12 }}
      value={withdrawAddress}
      onChange={(e) => setWithdrawAddress(e.target.value)}
    />

    <input
      className="invite-input"
      placeholder="Amount"
      style={{ marginTop: 12 }}
      value={withdrawAmount}
      onChange={(e) => setWithdrawAmount(e.target.value)}
    />

    <button
      className="collect-btn"
      style={{ marginTop: 12 }}
      onClick={() => {
        playClick();
        handleWithdraw();
      }}
    >
      Submit Withdraw
    </button>

    <button
      className="collect-btn"
      style={{ marginTop: 12 }}
      onClick={() => {
        playClick();
        setPage("home");
      }}
    >
      Back to Home
    </button>

    <div style={{ marginTop: 20 }}>
      <div className="chamber-title">📜 TEST HISTORY</div>

      {withdrawHistory.length === 0 ? (
        <div className="tiny">Henüz çekim talebi yok</div>
      ) : (
        withdrawHistory.map((w) => (
          <div key={w.id} className="dragon-card" style={{ marginTop: 10 }}>
            <div><strong>{w.amount_net_usdt} USDT</strong></div>
            <div className="tiny">Fee: {w.fee_usdt} USDT</div>
            <div className="tiny">Total Debit: {w.amount_gross_usdt} USDT</div>
            <div className="tiny">Status: {w.status}</div>
            <div className="tiny">Address: {w.address}</div>
            <div className="tiny">
              Date: {new Date(w.created_at).toLocaleString()}
            </div>
            {w.note && <div className="tiny">Note: {w.note}</div>}
          </div>
        ))
      )}
    </div>
  </div>
)}

<div className="bottom-grid">
  <button className="nav-card" onClick={() => {
                                 playClick();
                                 setPage("market");
                               }}>
    <span className="nav-title">🏪 Market</span>
    <span className="muted">Buy new dragons</span>
  </button>

  <button className="nav-card" onClick={() => {
                                 playClick();
                                 setPage("deposit");
                               }}>
    <span className="nav-title">➕ Deposit</span>
    <span className="muted">Load USDT</span>
  </button>

  <button className="nav-card" onClick={() => {
                                 playClick();
                                 setPage("withdraw");
                               }}>
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
      onClick={async () => {
        playClick();
        try {
          if (inviteLink) {
            await navigator.clipboard.writeText(inviteLink);
            alert("Link kopyalandı!");
          }
        } catch (e) {
          alert("Kopyalama başarısız");
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