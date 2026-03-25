import React, { useEffect, useMemo, useRef, useState } from "react";
import minikImg from "./assets/dragons/minik.png";
import cirakImg from "./assets/dragons/cirak.png";
import bronzImg from "./assets/dragons/bronz.png";
import gumusImg from "./assets/dragons/gumus.png";
import altinImg from "./assets/dragons/altin.png";
import efsaneImg from "./assets/dragons/efsane.png";
import bgImage from "./assets/backgrounds/background.webp";
import { getSavedLanguage, saveLanguage, translate, languageOptions } from "./i18n";

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

const dragonImages = {
  minik: minikImg,
  cirak: cirakImg,
  bronz: bronzImg,
  gumus: gumusImg,
  altin: altinImg,
  efsane: efsaneImg,
};

const dragonVisualMap = {
  minik: {
    icon: "🥚",
    title: "Minik Dragon",
    accent: "#94a3b8",
    bg: "linear-gradient(135deg, #1e293b, #0f172a)",
  },
  cirak: {
    icon: "🐉",
    title: "Çırak Dragon",
    accent: "#22c55e",
    bg: "linear-gradient(135deg, #123524, #0f172a)",
  },
  bronz: {
    icon: "🔥",
    title: "Bronz Dragon",
    accent: "#f97316",
    bg: "linear-gradient(135deg, #3b1d12, #0f172a)",
  },
  gumus: {
    icon: "❄️",
    title: "Gümüş Dragon",
    accent: "#60a5fa",
    bg: "linear-gradient(135deg, #10263b, #0f172a)",
  },
  altin: {
    icon: "👑",
    title: "Altın Dragon",
    accent: "#facc15",
    bg: "linear-gradient(135deg, #3b3210, #0f172a)",
  },
  efsane: {
    icon: "🌌",
    title: "Efsane Dragon",
    accent: "#a855f7",
    bg: "linear-gradient(135deg, #2a123b, #0f172a)",
  },
};

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
  const t = (key) => translate(lang, key);
  const [floatingRewards, setFloatingRewards] = useState([]);
  const [showReferralPanel, setShowReferralPanel] = useState(false);

function handleChangeLanguage(nextLang) {
  setLang(nextLang);
  saveLanguage(nextLang);
}
  const [leaderboard, setLeaderboard] = useState([]);
  const [myRank, setMyRank] = useState(null);
  const [leaderboardLoading, setLeaderboardLoading] = useState(false);
  const [lang, setLang] = useState("tr");

  function maskTelegramId(id) {
  if (!id) return "Unknown";
  const s = String(id);
  if (s.length <= 4) return s;
  return `${s.slice(0, 2)}***${s.slice(-2)}`;
}
  
  function spawnReward(amount) {
  const id = Date.now();

  setFloatingRewards((prev) => [
    ...prev,
    { id, amount }
  ]);

  setTimeout(() => {
    setFloatingRewards((prev) => prev.filter((r) => r.id !== id));
  }, 1200);
} 

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

async function loadProfile(id, silent = false) {
  try {
    if (!silent) setLoading(true);
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
    if (!silent) setLoading(false);
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
  
  async function loadLeaderboard() {
    try {
      setLeaderboardLoading(true);

      const res = await fetch(`${API_BASE}/leaderboard`, {
      headers: getAuthHeaders(),
      });

      if (!res.ok) {
      throw new Error(`Leaderboard alınamadı (${res.status})`);
      }

      const data = await res.json();
      setLeaderboard(data.top_players || []);
      setMyRank(data.me || null);
    } catch (err) {
      console.error("Leaderboard fetch error:", err);
    } finally {
      setLeaderboardLoading(false);
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
    await loadLeaderboard();
    setPage("home");
  } catch (e) {
    alert("Satın alma sırasında bir hata oluştu");
  }
}

  async function handleCollect() {
  if (!telegramId || collecting) return;

  try {
    setCollecting(true);
    setError("");

    const res = await fetch(`${API_BASE}/users/${telegramId}/collect`, {
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
          : `Collect başarısız (${res.status})`
      );
    }
    if (window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.impactOccurred("medium");
    }
    spawnReward(data?.added_eggs_ay ?? profile?.pending_eggs_ay ?? 0);

    await loadProfile(telegramId, true);
    await loadReferrals(telegramId);
    await loadLeaderboard();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Collect hatası";
    alert(msg);
  } finally {
    setCollecting(false);
  }
}
  
async function handleConvert() {
  if (!telegramId || converting) return;

  try {
    setConverting(true);
    setError("");

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

    await loadProfile(telegramId, true);
    await loadReferrals(telegramId);
    await loadLeaderboard();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Convert hatası";
    alert(msg);
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
      await loadLeaderboard();
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
    setLang(getSavedLanguage());
  }, []);

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
  } else {
    // Telegram yoksa kullanıcıyı blokla
    setError("Bu uygulama sadece Telegram içinde çalışır.");
  }
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
    loadLeaderboard();
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
  const groupedDragons = useMemo(() => {
  const dragons = profile?.dragons || [];
  const groups = {};

  for (const dragon of dragons) {
    const code = dragon.dragon_code;

    if (!groups[code]) {
      groups[code] = {
        dragon_code: code,
        count: 0,
        total_eggs_per_day: 0,
        min_remaining_days: Number.POSITIVE_INFINITY,
        levels: [],
        items: [],
      };
    }

    groups[code].count += 1;
    groups[code].total_eggs_per_day += Number(dragon.eggs_per_day || 0);
    groups[code].min_remaining_days = Math.min(
      groups[code].min_remaining_days,
      Number(dragon.remaining_days || 0)
    );
    groups[code].levels.push(Number(dragon.level || 1));
    groups[code].items.push(dragon);
  }

  return Object.values(groups).map((group) => ({
    ...group,
    levelsLabel: [...new Set(group.levels)].sort((a, b) => a - b).join(", "),
  }));
}, [profile]);

  const inviteLink = telegramId
    ? `https://t.me/dracokingdom_bot?start=${telegramId}`
    : "";

  return (   
    <div
      className="app-shell"
      style={{ backgroundImage: `url(${bgImage})` }}
    >
      <div className="floating-rewards">
  {floatingRewards.map((r) => (
    <div key={r.id} className="floating-reward">
      +{r.amount} 🥚
    </div>
  ))}
</div>
      <div className="container app-content">
   {page === "home" && (
  <>
    {loading ? (
      <div className="status-box">Profil yükleniyor...</div>
    ) : error ? (
      <div className="status-box error-box">{error}</div>
    ) : (
      <>
        <div className="top-hud">
          <div className="player-hud">
            <div className="player-mini">{t("appName")}</div>
            <h1>{playerName && playerName !== "." ? playerName : "Dragon Master"}</h1>
            <p className="tiny">ID: {telegramId || "yükleniyor..."}</p>
          </div>

          <div className="hud-right">
            <div className="dragon-badge-mini">
              <span className="tiny">{t("activeDragons")}</span>
              <strong>{activeCount}</strong>
            </div>

            <div className="hud-controls">
              <button
                className="hud-icon-btn"
                onClick={() => {
                  playClick();
                  setMusicOn((prev) => !prev);
                }}
              >
                {musicOn ? "🎵" : "🔇"}
              </button>

              <button
                className="hud-icon-btn"
                onClick={() => {
                  playClick();
                  setSfxOn((prev) => !prev);
                }}
              >
                {sfxOn ? "🔘" : "⚪"}
              </button>

              <button
                className="hud-lang-btn"
                onClick={() => {
                  playClick();
                  const currentIndex = languageOptions.findIndex((item) => item.code === lang);
                  const nextIndex = (currentIndex + 1) % languageOptions.length;
                  handleChangeLanguage(languageOptions[nextIndex].code);
                }}
              >
                {languageOptions.find((item) => item.code === lang)?.flag} {lang.toUpperCase()}
              </button>
            </div>
          </div>
        </div>

        <div className="dragon-stage">
  <div className="dragon-stage-topbar">
    <div className="stage-resource-pill eggs-pill">
      🥚 {profile?.total_eggs_ay ?? 0}
    </div>

    <div className="dragon-stage-title">🔥 Dragon Chamber</div>

    <div className="stage-resource-pill usdt-pill">
      💰 {profile?.usdt_balance ?? 0}
    </div>
  </div>

  <div className="dragon-stage-grid">
    {groupedDragons.length ? (
      groupedDragons.map((group) => {
const visual = dragonVisualMap[group.dragon_code] || {
  icon: "🐲",
  title: prettyCode(group.dragon_code),
  accent: "#b8924a",
  bg: "linear-gradient(135deg, rgba(19,34,53,0.55), rgba(15,23,42,0.28))",
};

return (
  <div
    key={group.dragon_code}
    className="dragon-slot"
    style={{
      borderColor: visual.accent,
      background: visual.bg,
    }}
  >
    <div className="dragon-slot-top">
      <div
        className="dragon-slot-image-wrap"
        style={{ borderColor: visual.accent }}
      >
        <img
          src={dragonImages[group.dragon_code] || minikImg}
          alt={visual.title}
          className="dragon-slot-img"
        />
      </div>

      <div className="dragon-slot-meta">
        <div
          className="dragon-slot-title"
          style={{ color: visual.accent }}
        >
          {visual.title} {group.count > 1 ? `x${group.count}` : ""}
        </div>
        <div className="tiny">Lv. {group.levelsLabel}</div>
      </div>
    </div>

    <div className="dragon-slot-stats">
      <span>🥚 {group.total_eggs_per_day}/day</span>
      <span>⏳ {group.min_remaining_days}d</span>
    </div>
  </div>
);

        return (
          <div
            key={dragon.id}
            className="dragon-slot"
            style={{
              borderColor: visual.accent,
              background: visual.bg,
            }}
          >
            <div className="dragon-slot-top">
              <div
                className="dragon-slot-image-wrap"
                style={{ borderColor: visual.accent }}
              >
                <img
                  src={dragonImages[dragon.dragon_code] || minikImg}
                  alt={visual.title}
                  className="dragon-slot-img"
                />
              </div>

              <div className="dragon-slot-meta">
                <div
                  className="dragon-slot-title"
                  style={{ color: visual.accent }}
                >
                  {visual.title}
                </div>
                <div className="tiny">Lv. {dragon.level}</div>
              </div>
            </div>

            <div className="dragon-slot-stats">
              <span>🥚 {dragon.eggs_per_day}/day</span>
              <span>⏳ {dragon.remaining_days}d</span>
            </div>
          </div>
        );
      })
    ) : (
      <div className="tiny">Henüz dragonun yok 🐣</div>
    )}
  </div>
        <div className="dragon-bottom-actions">
  <button
  className="bottom-action-btn collect-bottom-btn"
  onClick={() => {
    playClick();
    handleCollect();
  }}
  disabled={collecting}
>
  <div className="btn-main">
    {collecting ? t("collecting") : "Yumurtaları Topla"}
  </div>

  <div className="btn-sub">
    Bekleyen: {profile?.pending_eggs_ay ?? 0} AY
  </div>
</button>

  <button
  className="bottom-action-btn convert-bottom-btn"
  onClick={() => {
    playClick();
    handleConvert();
  }}
  disabled={converting}
>
  <div className="btn-main">
    {converting ? t("converting") : "AY=USDT ÇEVİR"}
  </div>

  <div className="btn-sub">
    500 AY = 1 USDT
  </div>
</button>
</div>

<div className="dragon-actions-foot tiny">
  500 AY = 1 USDT · {t("lastCollect")}: {formatDate(profile?.last_collect_at ?? null)}
</div>
</div>
      </>
    )}
  </>
)}

      {page === "market" && (
        <div className="dragon-chamber">
          <div className="section-title-main">🏪 Draco Market</div>

          <div className="dragon-grid">
            {marketDragons.map((dragon) => (
              <div
                key={dragon.code}
                className="dragon-card fantasy-dragon-card market-card"
              >
                <div className="market-card-top">
                  <div className="market-dragon-head">
                    <div className="market-dragon-image-wrap">
                      <img
                        src={dragonImages[dragon.code] || minikImg}
                        alt={prettyCode(dragon.code)}
                        className="dragon-img"
                      />
                    </div>

                    <div>
                      <div className="market-card-title">
                       {prettyCode(dragon.code)}
                      </div>

                      <div className="market-price">
                        💰 {dragon.price_usdt} USDT
                      </div>
                    </div>
                  </div>
                </div>

                <div className="tiny">🥚 {dragon.eggs_per_day} eggs/day</div>
              <div className="tiny">⏳ {dragon.lifetime_days} days</div>

                <button
                  className="buy-btn"
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
            className="secondary-btn"
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
    <div className="section-title-main">➕ Deposit USDT</div>

    <div className="dragon-card">
      <div className="tiny">Current balance</div>
      <strong>{profile?.usdt_balance ?? 0} USDT</strong>
    </div>

    {!depositOrder && (
      <>
        <input
          className="form-input"
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
          className="form-input"
          readOnly
          value={depositOrder.pay_to || ""}
          style={{ marginTop: 6 }}
        />

        <button
          className="secondary-btn"
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
          className="secondary-btn"
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
            className="secondary-btn"
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
      className="secondary-btn"
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
    <div className="section-title-main">💸 Withdraw</div>

    <div className="dragon-card">
      <div className="tiny">Available balance</div>
      <strong>{profile?.usdt_balance ?? 0} USDT</strong>
    </div>

    <input
      className="form-input"
      placeholder="Wallet address"
      style={{ marginTop: 12 }}
      value={withdrawAddress}
      onChange={(e) => setWithdrawAddress(e.target.value)}
    />

    <input
      className="form-input"
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
      className="secondary-btn"
      style={{ marginTop: 12 }}
      onClick={() => {
        playClick();
        setPage("home");
      }}
    >
      Back to Home
    </button>

    <div style={{ marginTop: 20 }}>
      <div className="section-title-sub">📜 Withdraw History</div>

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

    {page === "leaderboard" && (
  <div className="dragon-chamber">
    <div className="section-title-main">{t("leaderboardTitle")}</div>

    {leaderboardLoading ? (
      <div className="tiny">{t("loadingLeaderboard")}</div>
    ) : leaderboard.length === 0 ? (
      <div className="tiny">{t("noPlayersYet")}</div>
    ) : (
      <div style={{ display: "grid", gap: 10 }}>
        {leaderboard.map((player) => (
          <div
            key={player.rank}
            className="dragon-card"
            style={{
              border:
                String(player.telegram_id) === String(telegramId)
                  ? "1px solid #facc15"
                  : "1px solid transparent",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <div>
                <strong>
                  {player.rank === 1
                    ? "🥇"
                    : player.rank === 2
                    ? "🥈"
                    : player.rank === 3
                    ? "🥉"
                    : `#${player.rank}`}{" "}
                  {String(player.telegram_id) === String(telegramId)
                    ? `${playerName} (You)`
                    : maskTelegramId(player.telegram_id)}
                </strong>

                <div className="tiny">Eggs: {player.eggs_ay}</div>
                <div className="tiny">USDT: {player.usdt_balance}</div>
              </div>

              <div style={{ textAlign: "right" }}>
                <div className="tiny">{t("power")}</div>
                <strong>{player.total_power}</strong>
                <div className="tiny">{player.dragon_count} {t("dragons")}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    )}

    {myRank && (
      <div
        className="dragon-card"
        style={{ marginTop: 14, border: "1px solid #facc15" }}
      >
        <div className="tiny">{t("yourRank")}</div>
        <strong>#{myRank.rank}</strong>
        <div className="tiny">Eggs: {myRank.eggs_ay}</div>
        <div className="tiny">USDT: {myRank.usdt_balance}</div>
        <div className="tiny">Power: {myRank.total_power}</div>
        <div className="tiny">Dragons: {myRank.dragon_count}</div>
      </div>
    )}

    <button
      className="collect-btn"
      style={{ marginTop: 12 }}
      onClick={() => {
        playClick();
        loadLeaderboard();
      }}
      disabled={leaderboardLoading}
    >
      {t("refreshLeaderboard")}
    </button>

    <button
      className="secondary-btn"
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

{false && refs && (
  <div className="card compact-card">
    <button
      className="secondary-btn compact-section-toggle"
      onClick={() => {
        playClick();
        setShowReferralPanel((prev) => !prev);
      }}
    >
      👥 Referanslar {showReferralPanel ? "▲" : "▼"}
    </button>

    {showReferralPanel && (
      <div className="referral-panel-inner">
        <div className="section-head" style={{ marginTop: 14 }}>
          <h3>{t("inviteFriends")}</h3>
          <span className="muted">{t("referralLink")}</span>
        </div>

        <input
          value={inviteLink}
          readOnly
          className="invite-input"
          style={{ marginTop: 10 }}
        />

        <button
          className="collect-btn compact-copy-btn"
          style={{ marginTop: 12 }}
          onClick={async () => {
            playClick();
            try {
              await navigator.clipboard.writeText(inviteLink);
              alert("Link kopyalandı!");
            } catch {
              alert("Kopyalama başarısız");
            }
          }}
        >
          {t("copyLink")}
        </button>

        <div className="section-head" style={{ marginTop: 18 }}>
          <h3>{t("referrals")}</h3>
          <span className="muted">{t("threeLevels")}</span>
        </div>

        <div className="stats-grid compact-ref-grid">
          <div className="stat-card compact-stat-card">
            <p className="muted">{t("level1")}</p>
            <h2>{refs.level1}</h2>
          </div>

          <div className="stat-card compact-stat-card">
            <p className="muted">{t("level2")}</p>
            <h2>{refs.level2}</h2>
          </div>

          <div className="stat-card compact-stat-card">
            <p className="muted">{t("level3")}</p>
            <h2>{refs.level3}</h2>
          </div>
        </div>
      </div>
    )}
  </div>
)}

<div className="bottom-grid bottom-nav">
  <button
    className={`nav-card ${page === "market" ? "nav-card-active" : ""}`}
    onClick={() => {
    playClick();
    setPage("market");
  }}
>
    <span className="nav-title">{t("market")}</span>
    <span className="muted">{t("buyNewDragons")}</span>
  </button>

  <button
    className={`nav-card ${page === "deposit" ? "nav-card-active" : ""}`}
    onClick={() => {
      playClick();
      setPage("deposit");
    }}
  >
    <span className="nav-title">{t("deposit")}</span>
    <span className="muted">{t("loadUsdt")}</span>
  </button>

  <button
    className={`nav-card ${page === "withdraw" ? "nav-card-active" : ""}`}
    onClick={() => {
      playClick();
      setPage("withdraw");
    }}
  >
    <span className="nav-title">{t("withdraw")}</span>
    <span className="muted">{t("cashOutUsdt")}</span>
  </button>

  <button
    className={`nav-card ${page === "leaderboard" ? "nav-card-active" : ""}`}
    onClick={() => {
      playClick();
      setPage("leaderboard");
      loadLeaderboard();
    }}
  >
    <span className="nav-title">{t("leaderboard")}</span>
    <span className="muted">{t("topPlayers")}</span>
  </button>
</div>

    </div>
  </div>
);
}
