"""
ポケモン選出補助ツール (シングルバトル 6→3)

使い方:
  1. サイドバーで「環境ポケモン(相手候補)」を登録
  2. 「自分のチーム登録」タブで自分の6体を登録
     - 各ポケモンに「刺さる相手」「優先度」「確定選出」を設定
  3. 「選出」タブで相手6体を選ぶと、最適な3体の選出が自動表示される

起動: streamlit run pokemon_selector.py
"""

import json
import os
from datetime import datetime
import streamlit as st

# stlite(ブラウザ実行)版:
#   データは IndexedDB 永続化された /mnt/data に保存する。
#   index.html 側の idbfsMountpoints: ["/mnt/data"] でマウントされ、
#   ページを閉じても端末内(ブラウザ)にデータが残る。
DATA_DIR = "/mnt"
DATA_FILE = os.path.join(DATA_DIR, "team_data.json")

ROLES = ["エース", "アタッカー", "クッション", "サポート", "対策枠", "未設定"]
ROLE_EMOJI = {
    "エース": "👑", "アタッカー": "⚔️", "クッション": "🛡️",
    "サポート": "🤝", "対策枠": "🎯", "未設定": "❔",
}
TEAM_SIZE = 6
SELECT_SIZE = 3


# ───────────────────────── データ永続化 ─────────────────────────
def default_data():
    return {
        "opponents_master": [],
        "my_team": [
            {"name": "", "role": "未設定", "priority": 50,
             "fixed": False, "targets": [], "losses": [], "memo": ""}
            for _ in range(TEAM_SIZE)
        ],
        "exclusions": [],  # 同時選出できないペア [[名前A, 名前B], ...]
        "matches": [],     # 試合記録
    }


def normalize_data(raw):
    """任意のdictを正規のデータ構造に整形(不正値は安全側に補正)。"""
    if not isinstance(raw, dict):
        return default_data()

    out = {}
    om = raw.get("opponents_master", [])
    if not isinstance(om, list):
        om = []
    seen, uniq = set(), []
    for x in om:
        s = str(x).strip()
        if s and s not in seen:
            seen.add(s); uniq.append(s)
    out["opponents_master"] = uniq

    team = raw.get("my_team", [])
    if not isinstance(team, list):
        team = []
    norm = []
    for p in team[:TEAM_SIZE]:
        if not isinstance(p, dict):
            continue
        try:
            prio = int(p.get("priority", 50))
        except (TypeError, ValueError):
            prio = 50
        prio = max(0, min(100, prio))
        tg = p.get("targets", [])
        if not isinstance(tg, list):
            tg = []
        ls = p.get("losses", [])
        if not isinstance(ls, list):
            ls = []
        norm.append({
            "name": str(p.get("name", "")).strip(),
            "role": p.get("role") if p.get("role") in ROLES else "未設定",
            "priority": prio,
            "fixed": bool(p.get("fixed", False)),
            "targets": [str(t).strip() for t in tg if str(t).strip()],
            "losses": [str(t).strip() for t in ls if str(t).strip()],
            "memo": str(p.get("memo", "")).strip(),
        })
    while len(norm) < TEAM_SIZE:
        norm.append({"name": "", "role": "未設定", "priority": 50,
                     "fixed": False, "targets": [], "losses": [], "memo": ""})
    out["my_team"] = norm[:TEAM_SIZE]

    ex = raw.get("exclusions", [])
    norm_ex, ex_seen = [], set()
    if isinstance(ex, list):
        for pair in ex:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                a, b = str(pair[0]).strip(), str(pair[1]).strip()
                key = frozenset((a, b))
                if a and b and a != b and key not in ex_seen:
                    ex_seen.add(key); norm_ex.append([a, b])
    out["exclusions"] = norm_ex

    def name_list(v, limit=None):
        if not isinstance(v, list):
            return []
        r = [str(x).strip() for x in v if str(x).strip()]
        return r[:limit] if limit else r

    matches = raw.get("matches", [])
    norm_matches = []
    if isinstance(matches, list):
        for m in matches:
            if not isinstance(m, dict):
                continue
            result = m.get("result")
            if result not in ("win", "lose"):
                continue
            norm_matches.append({
                "id": str(m.get("id", "")) or str(len(norm_matches)),
                "datetime": str(m.get("datetime", "")),
                "my_team": name_list(m.get("my_team"), TEAM_SIZE),
                "my_selection": name_list(m.get("my_selection"), SELECT_SIZE),
                "opp_team": name_list(m.get("opp_team"), TEAM_SIZE),
                "opp_selection": name_list(m.get("opp_selection"), SELECT_SIZE),
                "result": result,
                "memo": str(m.get("memo", "")).strip(),
            })
    out["matches"] = norm_matches
    return out


def _load_seed():
    """初回起動用の同梱データ(seed_data.json)を探して読み込む。無ければ None。"""
    candidates = ["seed_data.json", "/seed_data.json",
                  os.path.join(os.getcwd(), "seed_data.json")]
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(here, "seed_data.json"))
    except Exception:
        pass
    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return normalize_data(json.load(f))
        except Exception:
            continue
    return None


def load_data():
    # 1. この端末に保存済みのデータがあれば最優先
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return normalize_data(json.load(f))
        except Exception:
            pass
    # 2. 初回(保存データなし)は同梱のシードデータで初期化し、端末に保存
    seed = _load_seed()
    if seed is not None:
        try:
            save_data(seed)
        except Exception:
            pass
        return seed
    # 3. どちらも無ければ空データ
    return default_data()


def save_data(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_team_widget_state():
    """チーム登録フォームを作り直して、読み込んだ/リセットしたデータを確実に反映させる。

    Streamlitはウィジェットにkeyを付けると過去の入力値(session_state)が優先され、
    後から value= を変えても表示が更新されない。そこでウィジェットのkeyに付ける
    バージョン番号(team_nonce)を増やし、別物のウィジェットとして作り直させる。
    """
    st.session_state["team_nonce"] = st.session_state.get("team_nonce", 0) + 1
    # 古いkeyの残骸も掃除(任意)
    for k in list(st.session_state.keys()):
        if any(str(k).startswith(p) for p in
               ("name_", "role_", "prio_", "fix_", "tgt_", "loss_", "memo_")):
            st.session_state.pop(k, None)


# ───────────────────────── 選出アルゴリズム ─────────────────────────
from itertools import combinations


def order_combo(combo):
    """表示用に選出順を整える: 確定→優先度の高い順。"""
    return sorted(combo, key=lambda p: (not p.get("fixed"), -p.get("priority", 0)))


def rank_selections(my_team, opponents, exclusions=None, n_select=SELECT_SIZE):
    """
    全組合せ(最大6C3=20通り)を評価し、良い順にランキングして返す。

    制約:
      - 同時選出NG(exclusions)のペアを両方含む組合せは除外
      - 確定選出(fixed)はできるだけ多く含む組合せを上位に
    評価キー(降順): (含む確定数, カバレッジ数, -リスク(不利の露出), 合計優先度)
      ※リスク = 選出個体の『絶対に勝てない相手』が相手チームにいる件数

    戻り値: (results, opp_set, relaxed)
      results : [{combo, covered, uncovered, n_fixed, exposure, exposed, score}, ...] 良い順
      opp_set : 相手名のset
      relaxed : 同時選出NGを満たす組合せが無く制約を緩めたか(bool)
    """
    opp_list = [o for o in opponents if o]
    opp_set = set(opp_list)
    active = [p for p in my_team if p.get("name")]
    excl = exclusions or []
    fixed_names = {p["name"] for p in active if p.get("fixed")}

    def violates_excl(combo):
        names = {p["name"] for p in combo}
        return any(a in names and b in names for a, b in excl)

    def evaluate(combos, apply_excl):
        out = []
        for combo in combos:
            if apply_excl and violates_excl(combo):
                continue
            covered = set()
            exposed = {}          # {個体名: [相手チームにいる『絶対に勝てない相手』,...]}
            for p in combo:
                covered |= set(p.get("targets", [])) & opp_set
                bad = sorted(set(p.get("losses", [])) & opp_set)
                if bad:
                    exposed[p["name"]] = bad
            exposure = sum(len(v) for v in exposed.values())
            n_fixed = sum(1 for p in combo if p["name"] in fixed_names)
            out.append({
                "combo": list(combo),
                "covered": covered,
                "uncovered": [o for o in opp_list if o not in covered],
                "n_fixed": n_fixed,
                "exposure": exposure,
                "exposed": exposed,
                # 確定数 → カバレッジ → リスク小 → 優先度
                "score": (n_fixed, len(covered), -exposure,
                          sum(p.get("priority", 0) for p in combo)),
            })
        return out

    k = min(n_select, len(active))
    all_combos = list(combinations(active, k)) if active else []

    results = evaluate(all_combos, apply_excl=True)
    relaxed = False
    if not results:                       # NG制約で全滅 → 緩めて提示
        results = evaluate(all_combos, apply_excl=False)
        relaxed = True

    results.sort(key=lambda r: r["score"], reverse=True)
    return results, opp_set, relaxed


def pick_patterns(results, k=3):
    """カバレッジ内容ができるだけ異なる選出を最大k個選ぶ(別パターン提示用)。"""
    chosen, cover_keys = [], set()
    for r in results:
        key = frozenset(r["covered"])
        if key in cover_keys:
            continue
        chosen.append(r); cover_keys.add(key)
        if len(chosen) >= k:
            return chosen
    # カバレッジ内容が同じものしか残ってなければ、別の組合せで埋める
    name_keys = {frozenset(p["name"] for p in r["combo"]) for r in chosen}
    for r in results:
        nk = frozenset(p["name"] for p in r["combo"])
        if nk in name_keys:
            continue
        chosen.append(r); name_keys.add(nk)
        if len(chosen) >= k:
            break
    return chosen


def assignments_for(combo, opp_set):
    """{個体名: [対応する相手名,...]}"""
    return {p["name"]: sorted(set(p.get("targets", [])) & opp_set) for p in combo}


def opp_handlers(my_team, opp_name):
    """ある相手に対して刺さる自分の個体名リスト(優先度順)"""
    hs = [p for p in my_team if p.get("name") and opp_name in p.get("targets", [])]
    return [p["name"] for p in sorted(hs, key=lambda p: -p.get("priority", 0))]


def cov_color(ratio):
    return "#4ade80" if ratio >= 0.8 else "#fbbf24" if ratio >= 0.5 else "#f87171"


# ───────────────────────── 戦績分析 ─────────────────────────
def wr_color(rate):
    return "#4ade80" if rate >= 0.6 else "#fbbf24" if rate >= 0.4 else "#f87171"


def match_overall(matches):
    total = len(matches)
    wins = sum(1 for m in matches if m["result"] == "win")
    return total, wins, total - wins, (wins / total if total else 0.0)


def _aggregate(matches, key_fn):
    """key_fn(match)->iterable of keys。各キーごとに games/wins を集計。"""
    agg = {}
    for m in matches:
        for k in key_fn(m):
            d = agg.setdefault(k, {"games": 0, "wins": 0})
            d["games"] += 1
            if m["result"] == "win":
                d["wins"] += 1
    rows = []
    for k, d in agg.items():
        rows.append({"key": k, "games": d["games"], "wins": d["wins"],
                     "losses": d["games"] - d["wins"],
                     "rate": d["wins"] / d["games"] if d["games"] else 0.0})
    return rows


def winrate_by_opp_pokemon(matches):
    """相手チームに含まれた各ポケモンごとの勝率(対面した試合ベース)。"""
    rows = _aggregate(matches, lambda m: set(m["opp_team"]))
    return sorted(rows, key=lambda r: (-r["rate"], -r["games"]))


def winrate_by_build(matches):
    """相手構築(6体セット)ごとの勝率。"""
    def key_fn(m):
        if not m["opp_team"]:
            return []
        return [" / ".join(sorted(m["opp_team"]))]
    rows = _aggregate(matches, key_fn)
    return sorted(rows, key=lambda r: (-r["games"], -r["rate"]))


def winrate_by_my_selection(matches):
    """自分の選出(3体)ごとの勝率。"""
    def key_fn(m):
        if not m["my_selection"]:
            return []
        return [" / ".join(sorted(m["my_selection"]))]
    rows = _aggregate(matches, key_fn)
    return sorted(rows, key=lambda r: (-r["games"], -r["rate"]))


def selection_rate_opp(matches):
    """
    相手ポケモン別の選出率。
    分母 = その相手が相手チームにいて、かつ相手の選出が記録された試合数
    分子 = そのうち実際に相手が選出した試合数
    （相手選出が未記録の試合は集計対象外）
    戻り値: [{key, in_team, selected, rate}, ...] 選出率の高い順
    """
    rec = [m for m in matches if m["opp_selection"]]
    agg = {}
    for m in rec:
        sel = set(m["opp_selection"])
        for p in set(m["opp_team"]):
            d = agg.setdefault(p, {"in_team": 0, "selected": 0})
            d["in_team"] += 1
            if p in sel:
                d["selected"] += 1
    rows = [{"key": k, "in_team": d["in_team"], "selected": d["selected"],
             "rate": d["selected"] / d["in_team"] if d["in_team"] else 0.0}
            for k, d in agg.items() if d["in_team"] > 0]
    return sorted(rows, key=lambda r: (-r["rate"], -r["in_team"]))


def render_pattern_card(pat, opponents, label, recommended=False):
    """別パターン比較用のコンパクトなカード。"""
    combo = order_combo(pat["combo"])
    cov, total = len(pat["covered"]), len(opponents)
    color = cov_color(cov / total if total else 0)
    members = "<br>".join(
        f"{ROLE_EMOJI.get(p['role'],'❔')} <b>{p['name']}</b>"
        + (" <span class='pill pill-ok'>⭐</span>" if p.get("fixed") else "")
        for p in combo)
    unc = ("、".join(pat["uncovered"]) if pat["uncovered"] else "なし")
    border = "#facc15" if recommended else "rgba(120,140,255,0.25)"
    head = f"パターン{label}" + ("　⭐おすすめ" if recommended else "")
    risk = pat.get("exposure", 0)
    risk_html = (f"<div style='font-size:12px;color:#f87171;margin-top:4px'>"
                 f"⚠️ 不利リスク: {risk}件</div>" if risk else
                 "<div style='font-size:12px;color:#4ade80;margin-top:4px'>"
                 "不利リスク: なし</div>")
    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.04);border:2px solid {border};
         border-radius:14px;padding:14px;margin-bottom:8px;min-height:220px">
      <div style="font-weight:800;font-size:15px;margin-bottom:8px;color:#cdd3f0">{head}</div>
      <div style="font-size:14px;line-height:1.9">{members}</div>
      <div style="margin-top:10px;font-size:13px">
        カバレッジ <b style="color:{color};font-size:16px">{cov}/{total}</b></div>
      <div style="font-size:12px;color:#9aa6d0;margin-top:4px">未対応: {unc}</div>
      {risk_html}
    </div>
    """, unsafe_allow_html=True)


def render_pattern_detail(data, opponents, pattern):
    """1つの選出パターンの詳細(選出カード / 対応マップ / 控え)を描画。"""
    opp_set = set(opponents)
    combo = order_combo(pattern["combo"])
    assignments = assignments_for(combo, opp_set)
    sel_names = [p["name"] for p in combo]
    covered, uncovered = pattern["covered"], pattern["uncovered"]
    exposed = pattern.get("exposed", {})

    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"### ✅ 選出 ({len(combo)}体)")
        for idx, p in enumerate(combo, 1):
            emoji = ROLE_EMOJI.get(p["role"], "❔")
            handles = assignments.get(p["name"], [])
            fixed_badge = " <span class='pill pill-ok'>⭐確定</span>" if p.get("fixed") else ""
            handle_html = ("".join(f"<span class='pill pill-ok'>{h}</span>" for h in handles)
                           if handles else "<span class='pill pill-warn'>明確な対応相手なし(汎用枠)</span>")
            bad = exposed.get(p["name"], [])
            danger_html = ("<div style='margin-top:8px;font-size:13px;color:#f87171'>"
                           "❌ 絶対に勝てない相手が相手チームにいます:</div>"
                           + "<div>" + "".join(f"<span class='pill pill-warn'>{b}</span>" for b in bad)
                           + "</div>") if bad else ""
            border_style = "border-color:#f87171" if bad else ""
            memo_html = (f"<div style='color:#9aa6d0;font-size:12px;margin-top:6px'>📝 {p['memo']}</div>"
                         if p.get("memo") else "")
            st.markdown(f"""
            <div class="sel-card" style="{border_style}">
              <div style="font-size:18px;font-weight:800">
                {idx}. {emoji} {p['name']}
                <span class="pill">{p['role']}</span>
                <span class="pill">優先度 {p['priority']}</span>{fixed_badge}
              </div>
              <div style="margin-top:8px;font-size:13px;color:#cdd3f0">対応する相手:</div>
              <div>{handle_html}</div>
              {danger_html}
              {memo_html}
            </div>
            """, unsafe_allow_html=True)

    with right:
        cov_n, total = len(covered), len(opponents)
        color = cov_color(cov_n / total if total else 0)
        st.markdown("### 📊 カバレッジ")
        st.markdown(f"""
        <div style="font-size:30px;font-weight:900;color:{color}">{cov_n} / {total}</div>
        <div style="color:#9aa6d0;font-size:12px">相手のうち対応できる数</div>
        """, unsafe_allow_html=True)

        if uncovered:
            st.markdown("##### ⚠️ 対応できない相手(負け筋注意)")
            for o in uncovered:
                benchers = [h for h in opp_handlers(data["my_team"], o) if h not in sel_names]
                note = (f" → 控えに対応可: {', '.join(benchers)}" if benchers
                        else " → チーム全体で対応役なし")
                st.markdown(f"<span class='pill pill-warn'>{o}</span>{note}",
                            unsafe_allow_html=True)
        else:
            st.success("相手すべてに対応役がいます！")

        if exposed:
            st.markdown("##### ❌ 不利な対面(絶対に勝てない相手)")
            for nm, bad in exposed.items():
                st.markdown(
                    f"<div style='font-size:13px;margin:2px 0'>"
                    f"<b style='color:#f87171'>{nm}</b> ⚠️ "
                    + "".join(f"<span class='pill pill-warn'>{b}</span>" for b in bad)
                    + "</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='color:#4ade80;font-size:13px;margin-top:6px'>"
                        "✅ 不利な相手の露出なし</div>", unsafe_allow_html=True)

        st.markdown("##### 🗺 相手別の対応役")
        for o in opponents:
            hs = opp_handlers(data["my_team"], o)
            in_sel = [h for h in hs if h in sel_names]
            if in_sel:
                tag = f"<b style='color:#4ade80'>{in_sel[0]}</b>"
                extra = f"(控え: {', '.join(h for h in hs if h not in in_sel)})" if len(hs) > 1 else ""
            elif hs:
                tag = f"<span style='color:#fbbf24'>{hs[0]} (選出外)</span>"; extra = ""
            else:
                tag = "<span style='color:#f87171'>対応役なし</span>"; extra = ""
            st.markdown(f"<div style='font-size:13px;margin:2px 0'>"
                        f"{o} → {tag} <span style='color:#7a86b0'>{extra}</span></div>",
                        unsafe_allow_html=True)

    # 控え(非選出)
    st.divider()
    excl_set = {frozenset(pair) for pair in data.get("exclusions", [])}
    registered = [p for p in data["my_team"] if p["name"]]
    bench = [p for p in registered if p["name"] not in sel_names]
    if bench:
        st.markdown("#### 🪑 控え(このパターンでは非選出)")
        bcols = st.columns(min(len(bench), 3))
        for i, p in enumerate(bench):
            with bcols[i % len(bcols)]:
                emoji = ROLE_EMOJI.get(p["role"], "❔")
                matched = sorted(set(p["targets"]) & opp_set)
                blocked = [s for s in sel_names if frozenset((p["name"], s)) in excl_set]
                if blocked:
                    reason = f"同時選出NG: {', '.join(blocked)} と被るため"
                elif matched:
                    reason = "対応相手が他の選出と重複"
                else:
                    reason = "今回の相手に刺さる相手なし"
                st.markdown(f"""
                <div class="bench-card">
                  <b>{emoji} {p['name']}</b>
                  <span class="pill">優先度 {p['priority']}</span><br>
                  <span style="color:#9aa6d0;font-size:12px">非選出理由: {reason}</span>
                </div>
                """, unsafe_allow_html=True)


# ───────────────────────── UI ─────────────────────────
def main():
    st.set_page_config(page_title="ポケモン選出補助", page_icon="⚡", layout="wide")

    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg,#0f1226,#1a1340); }
    [data-testid="stHeader"] { background: transparent; }
    .poke-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(120,140,255,0.2);
        border-radius: 14px; padding: 16px; margin-bottom: 10px;
    }
    .sel-card {
        background: linear-gradient(135deg,rgba(80,200,120,0.18),rgba(80,200,120,0.05));
        border: 2px solid #4ade80; border-radius: 16px;
        padding: 18px; margin-bottom: 12px;
    }
    .bench-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 14px; padding: 14px; margin-bottom: 10px; opacity: 0.85;
    }
    .pill {
        display:inline-block; background:rgba(120,140,255,0.2);
        border-radius:999px; padding:2px 10px; margin:2px; font-size:12px;
    }
    .pill-warn { background:rgba(248,113,113,0.25); }
    .pill-ok   { background:rgba(74,222,128,0.22); }

    /* ── iPad / モバイル対応 ── */
    @media (max-width: 1024px) {
        /* ボタンを大きくしてタップしやすく */
        .stButton > button {
            min-height: 48px !important;
            font-size: 15px !important;
        }
        /* セレクトボックスも大きく */
        .stSelectbox > div > div {
            min-height: 44px !important;
        }
        /* テキスト入力も大きく */
        .stTextInput > div > div > input {
            min-height: 44px !important;
            font-size: 16px !important; /* iOS zoom防止 */
        }
        /* チェックボックスのタップ領域を広げる */
        .stCheckbox { padding: 8px 0 !important; }
        /* サイドバーの幅を調整 */
        [data-testid="stSidebar"] { min-width: 260px !important; }
    }
    /* safe-area (ノッチ/ホームバー対応) */
    .stApp {
        padding-bottom: env(safe-area-inset-bottom, 0);
        padding-left: env(safe-area-inset-left, 0);
        padding-right: env(safe-area-inset-right, 0);
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
      <span style="font-size:34px">⚡</span>
      <span style="font-size:30px;font-weight:900;
        background:linear-gradient(90deg,#60a5fa,#c084fc);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent">
        ポケモン選出補助ツール</span>
      <span style="color:#7a86b0;font-size:14px;margin-left:6px">シングルバトル 6 → 3</span>
    </div>
    """, unsafe_allow_html=True)

    data = load_data()

    # ───── サイドバー: 環境ポケモン管理 ─────
    with st.sidebar:
        st.subheader("🌐 環境ポケモン(相手候補)")
        st.caption("相手として登場しうるポケモンを1行に1体ずつ。ここに登録した名前を選出計算で使います。")
        master_text = st.text_area(
            "相手候補リスト",
            value="\n".join(data["opponents_master"]),
            height=260,
            placeholder="カイリュー\nハバタクカミ\nサーフゴー\n…",
            label_visibility="collapsed",
        )
        if st.button("💾 相手候補を保存", use_container_width=True):
            names = [ln.strip() for ln in master_text.splitlines() if ln.strip()]
            # 重複除去(順序保持)
            seen, uniq = set(), []
            for n in names:
                if n not in seen:
                    seen.add(n); uniq.append(n)
            data["opponents_master"] = uniq
            save_data(data)
            st.success(f"{len(uniq)}体を保存しました")
            st.rerun()

        st.divider()
        st.subheader("📂 データの保存 / 読み込み")

        # 初回(データが空)のときは読み込みを促す
        if not data["opponents_master"] and not any(p["name"] for p in data["my_team"]):
            st.info("👋 はじめに、お手持ちの **team_data.json** の中身を下の"
                    "「JSONを貼り付け」に貼り付けて読み込んでください。")

        # ① JSON 読み込み(貼り付け方式 — stliteで確実に動く)
        st.markdown("**📥 JSONを貼り付けて読み込む**")
        st.caption("team_data.json をテキストエディタで開き、全選択→コピーして下へ貼り付け。")
        paste = st.text_area(
            "JSONを貼り付け",
            height=120,
            placeholder='{\n  "opponents_master": [...],\n  "my_team": [...],\n  ...\n}',
            label_visibility="collapsed",
            key="json_paste",
        )
        if st.button("📥 貼り付けたJSONを読み込む", use_container_width=True):
            if not paste.strip():
                st.warning("JSONを貼り付けてください。")
            else:
                try:
                    loaded = normalize_data(json.loads(paste))
                    save_data(loaded)
                    clear_team_widget_state()
                    st.success("読み込みました！")
                    st.rerun()
                except Exception as e:
                    st.error(f"読み込み失敗（JSONの形式を確認してください）: {e}")

        # ② JSONファイル選択(PCのブラウザ用。iPad/stliteでは403になることがあるため補助)
        with st.expander("📁 ファイルから読み込む（PCのブラウザ向け）"):
            up = st.file_uploader("JSONファイルを選択", type=["json"], key="json_uploader")
            if up is not None:
                if st.button("📥 このファイルを読み込む", use_container_width=True):
                    try:
                        loaded = normalize_data(json.load(up))
                        save_data(loaded)
                        clear_team_widget_state()
                        st.success("読み込みました！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"読み込み失敗: {e}")

        # JSON 書き出し(エクスポート)
        st.download_button(
            "💾 現在のデータをJSONで保存",
            data=json.dumps(data, ensure_ascii=False, indent=2),
            file_name="team_data.json",
            mime="application/json",
            use_container_width=True,
        )

        st.divider()
        st.caption("📲 データはこの端末のブラウザ内に自動保存されます。\n"
                   "機種変更・別端末へ移すときは「JSONで保存」でバックアップを。")
        if st.button("🗑 全データをリセット", use_container_width=True):
            save_data(default_data())
            clear_team_widget_state()
            st.rerun()

    master = data["opponents_master"]

    tab_team, tab_select, tab_stats = st.tabs(
        ["🧩 自分のチーム登録", "🎯 選出", "📈 戦績分析"])

    # ═════════════ チーム登録タブ ═════════════
    with tab_team:
        if not master:
            st.info("まずサイドバーで「環境ポケモン(相手候補)」を登録してください。"
                    "それが各ポケモンの『刺さる相手』の選択肢になります。")

        st.caption("自分の6体を登録します。**優先度**が高いほど選出されやすく、"
                   "**確定選出**は必ず3体に含めます。**刺さる相手**には、その個体が有利を取れる相手を選びます。")

        # 読み込み/リセットのたびに増えるバージョン番号。これをkeyに付けることで
        # フォームを"別物"として作り直し、最新データを確実に表示させる。
        nonce = st.session_state.get("team_nonce", 0)
        with st.form("team_form"):
            cols = st.columns(2)
            new_team = []
            for i in range(TEAM_SIZE):
                p = data["my_team"][i]
                with cols[i % 2]:
                    st.markdown(f"<div class='poke-card'>", unsafe_allow_html=True)
                    st.markdown(f"**#{i+1}**")
                    name = st.text_input("名前", value=p["name"], key=f"name_{i}_{nonce}",
                                         placeholder="例: カイリュー")
                    c1, c2 = st.columns(2)
                    role = c1.selectbox("役割", ROLES,
                                        index=ROLES.index(p["role"]) if p["role"] in ROLES else len(ROLES)-1,
                                        key=f"role_{i}_{nonce}")
                    priority = c2.number_input("優先度(高=優先)", min_value=0, max_value=100,
                                               value=int(p["priority"]), step=5, key=f"prio_{i}_{nonce}")
                    fixed = st.checkbox("⭐ 確定選出(必ず入れる)", value=p["fixed"], key=f"fix_{i}_{nonce}")
                    valid_targets = [t for t in p["targets"] if t in master]
                    targets = st.multiselect("⭕ 刺さる相手(この子を出したい相手)",
                                             options=master, default=valid_targets,
                                             key=f"tgt_{i}_{nonce}")
                    valid_losses = [t for t in p.get("losses", []) if t in master]
                    losses = st.multiselect("❌ 絶対に勝てない相手(不利・出すと危険)",
                                            options=master, default=valid_losses,
                                            key=f"loss_{i}_{nonce}")
                    memo = st.text_input("メモ(任意)", value=p["memo"], key=f"memo_{i}_{nonce}",
                                         placeholder="立ち回り・技構成など")
                    st.markdown("</div>", unsafe_allow_html=True)
                    new_team.append({"name": name.strip(), "role": role,
                                     "priority": int(priority), "fixed": fixed,
                                     "targets": targets, "losses": losses,
                                     "memo": memo.strip()})

            submitted = st.form_submit_button("💾 チームを保存", use_container_width=True)
            if submitted:
                data["my_team"] = new_team
                save_data(data)
                st.success("チームを保存しました！")

        # カバレッジ簡易チェック ＆ 対策が薄いポケモン一覧
        registered = [p for p in data["my_team"] if p["name"]]
        if registered and master:
            st.divider()
            st.markdown("##### 📋 登録状況チェック")

            # 各相手候補について、対応できる自分の個体名を集計
            depth = []  # (相手名, [対応個体名,...])
            for m in master:
                handlers = [p["name"] for p in registered if m in p["targets"]]
                depth.append((m, handlers))

            covered_n = sum(1 for _, h in depth if h)
            st.write(f"登録済み: **{len(registered)}/6体** ／ "
                     f"対応できる相手候補: **{covered_n}/{len(master)}種**")

            # 対策の薄い順(対応個体数の少ない順)に並べる
            depth_sorted = sorted(depth, key=lambda x: len(x[1]))
            thin = [d for d in depth_sorted if len(d[1]) <= 1]

            st.markdown("##### 🚨 対策が薄いポケモン一覧")
            st.caption("対応できる自分のポケモンが **0〜1体** の相手。優先して対策枠を用意したい相手です。")
            if not thin:
                st.success("すべての相手候補に2体以上の対応役がいます！手厚い構築です👏")
            else:
                for name, handlers in thin:
                    n = len(handlers)
                    if n == 0:
                        st.markdown(
                            f"<div style='margin:3px 0'>"
                            f"<span class='pill pill-warn'>対応 0体</span> "
                            f"<b style='color:#f87171'>{name}</b> "
                            f"<span style='color:#9aa6d0;font-size:12px'>← 完全ノーマーク</span>"
                            f"</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(
                            f"<div style='margin:3px 0'>"
                            f"<span class='pill' style='background:rgba(251,191,36,0.25)'>対応 1体</span> "
                            f"<b style='color:#fbbf24'>{name}</b> "
                            f"<span style='color:#9aa6d0;font-size:12px'>← {handlers[0]} のみ"
                            f"（倒されると対応不能）</span>"
                            f"</div>", unsafe_allow_html=True)

            # 全相手の対応数を一覧(折りたたみ)
            with st.expander("📊 全相手候補の対応数を見る"):
                for name, handlers in depth_sorted:
                    n = len(handlers)
                    color = "#f87171" if n == 0 else "#fbbf24" if n == 1 else "#4ade80"
                    hl = "、".join(handlers) if handlers else "なし"
                    st.markdown(
                        f"<div style='font-size:13px;margin:2px 0'>"
                        f"<b style='color:{color}'>{n}体</b> {name} "
                        f"<span style='color:#7a86b0'>({hl})</span></div>",
                        unsafe_allow_html=True)

        # ───── 同時選出できない組み合わせ ─────
        reg_names = [p["name"] for p in data["my_team"] if p["name"]]
        if len(reg_names) >= 2:
            st.divider()
            st.markdown("##### 🚫 同時選出できない組み合わせ")
            st.caption("ここで指定したペアは、同じ選出(3体)に同時には入りません。"
                       "役割が被る・並べても噛み合わない2体などに設定します。")

            # 既存ペアの表示と削除
            if data["exclusions"]:
                for idx, (a, b) in enumerate(data["exclusions"]):
                    cc1, cc2 = st.columns([5, 1])
                    cc1.markdown(
                        f"<div style='padding-top:6px'>"
                        f"<span class='pill pill-warn'>{a}</span> "
                        f"<span style='color:#7a86b0'>✕ 同時不可 ✕</span> "
                        f"<span class='pill pill-warn'>{b}</span></div>",
                        unsafe_allow_html=True)
                    if cc2.button("削除", key=f"del_excl_{idx}"):
                        data["exclusions"].pop(idx)
                        save_data(data)
                        st.rerun()
            else:
                st.caption("（未設定）")

            # 新規ペア追加
            ac1, ac2, ac3 = st.columns([3, 3, 1])
            pa = ac1.selectbox("ポケモンA", reg_names, key="excl_a")
            pb = ac2.selectbox("ポケモンB", reg_names, key="excl_b", index=min(1, len(reg_names)-1))
            ac3.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if ac3.button("➕ 追加", key="add_excl"):
                if pa == pb:
                    st.warning("異なる2体を選んでください。")
                elif frozenset((pa, pb)) in {frozenset(x) for x in data["exclusions"]}:
                    st.warning("そのペアは既に登録済みです。")
                else:
                    data["exclusions"].append([pa, pb])
                    save_data(data)
                    st.rerun()

    # ═════════════ 戦績分析タブ ═════════════
    # (選出タブより前に描画する: 選出タブ内の早期returnでmainが終了しても
    #  戦績分析が必ず表示されるようにするため)
    with tab_stats:
        render_stats_tab(data)

    # ═════════════ 選出タブ ═════════════
    with tab_select:
        registered = [p for p in data["my_team"] if p["name"]]
        if len(registered) < SELECT_SIZE:
            st.info("先に「自分のチーム登録」タブで最低3体を登録してください。")
            return
        if not master:
            st.info("サイドバーで相手候補を登録してください。")
            return

        st.markdown("##### 相手の6体を選択")
        opponents = st.multiselect(
            "相手のパーティ(チームプレビュー)",
            options=master, max_selections=TEAM_SIZE,
            placeholder="相手の6体を選択…",
            label_visibility="collapsed",
        )

        if not opponents:
            st.caption("👆 相手のポケモンを選ぶと、自動で最適な選出が表示されます。")
            return

        # 相手の選出予測(過去の戦績から)
        sel_map = {r["key"]: r for r in selection_rate_opp(data["matches"])}
        preds = [(o, sel_map[o]) for o in opponents if o in sel_map]
        if preds:
            preds.sort(key=lambda x: -x[1]["rate"])
            with st.expander("🔮 相手の選出予測（過去の戦績ベース）", expanded=True):
                st.caption("この相手構築の各ポケモンが過去に選出されてきた割合。"
                           "高いものは警戒、低いものは出てこない可能性。")
                for o, r in preds:
                    color = wr_color(r["rate"])
                    st.markdown(
                        f"<div style='font-size:13px;margin:3px 0;display:flex;"
                        f"justify-content:space-between'>"
                        f"<span><b>{o}</b></span>"
                        f"<span style='color:{color};font-weight:700'>選出率 {r['rate']*100:.0f}% "
                        f"<span style='color:#7a86b0;font-weight:400'>"
                        f"({r['selected']}/{r['in_team']}回)</span></span></div>",
                        unsafe_allow_html=True)

        results, opp_set, relaxed = rank_selections(
            data["my_team"], opponents, data["exclusions"])
        if not results:
            st.error("選出可能な組合せがありません。チーム登録を確認してください。")
            return

        if relaxed:
            st.warning("⚠️ 『同時選出NG』をすべて満たす組合せが無かったため、"
                       "制約を一部無視した候補を表示しています。")

        best = results[0]

        # 完全対応できない、または不利な相手の露出がある場合は複数パターン提示
        if best["uncovered"] or best.get("exposure", 0) > 0:
            patterns = pick_patterns(results, 3)
            if best["uncovered"]:
                msg = (f"相手 {len(opponents)} 体すべてに対応できる選出はありません。")
            else:
                msg = "完全対応できますが、不利な相手の露出があります。"
            st.warning(msg + f" トレードオフの異なる **{len(patterns)} パターン**を提示します。"
                       "（下で各パターンの詳細を切り替えて確認できます）")

            cols = st.columns(len(patterns))
            labels = ["A", "B", "C", "D", "E"]
            for i, (col, pat) in enumerate(zip(cols, patterns)):
                with col:
                    render_pattern_card(pat, opponents, labels[i], recommended=(i == 0))

            st.divider()
            choice = st.radio(
                "詳細を見るパターン",
                options=list(range(len(patterns))),
                format_func=lambda i: f"パターン{labels[i]}"
                + ("（おすすめ）" if i == 0 else "")
                + f" ─ カバレッジ {len(patterns[i]['covered'])}/{len(opponents)}"
                + f" / リスク{patterns[i].get('exposure', 0)}",
                horizontal=True,
            )
            st.markdown(f"#### 🔎 詳細：パターン{labels[choice]}")
            render_pattern_detail(data, opponents, patterns[choice])
            shown = patterns[choice]
        else:
            # 完全対応＆リスクなし → 推奨1パターンを詳細表示
            st.success("✅ 相手全体に対応でき、不利な露出もない選出が見つかりました！")
            render_pattern_detail(data, opponents, best)
            shown = best

        # ───── 試合結果の記録 ─────
        st.divider()
        st.markdown("### 📝 試合結果を記録")
        st.caption("この相手構築との対戦結果を記録します。戦績は「📈 戦績分析」タブで集計されます。")

        rec_default = [p["name"] for p in order_combo(shown["combo"])]
        with st.form("match_form", clear_on_submit=True):
            mc1, mc2 = st.columns(2)
            with mc1:
                my_sel = st.multiselect(
                    "自分の選出(実際に出した3体)",
                    options=[p["name"] for p in registered],
                    default=rec_default, max_selections=SELECT_SIZE)
                result = st.radio("勝敗", ["勝ち", "負け"], horizontal=True)
            with mc2:
                opp_sel = st.multiselect(
                    "相手の選出(任意・相手が出した3体)",
                    options=opponents, max_selections=SELECT_SIZE)
                memo = st.text_input("メモ(任意)", placeholder="勝因・負因など")

            if st.form_submit_button("✅ この試合を記録する", use_container_width=True):
                if len(my_sel) == 0:
                    st.warning("自分の選出を1体以上選んでください。")
                else:
                    data["matches"].append({
                        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "my_team": [p["name"] for p in registered],
                        "my_selection": my_sel,
                        "opp_team": list(opponents),
                        "opp_selection": opp_sel,
                        "result": "win" if result == "勝ち" else "lose",
                        "memo": memo.strip(),
                    })
                    save_data(data)
                    st.success(f"記録しました！（通算 {len(data['matches'])} 戦）")


def render_stats_tab(data):
    matches = data.get("matches", [])
    if not matches:
        st.info("まだ試合記録がありません。「🎯 選出」タブの下部「📝 試合結果を記録」から記録できます。")
        return

    total, wins, losses, rate = match_overall(matches)

    # 全体サマリ
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総試合数", total)
    c2.metric("勝ち", wins)
    c3.metric("負け", losses)
    c4.metric("勝率", f"{rate*100:.1f}%")
    st.markdown(
        f"<div style='height:10px;border-radius:5px;overflow:hidden;background:#f87171;margin:4px 0 16px'>"
        f"<div style='height:100%;width:{rate*100:.1f}%;background:#4ade80'></div></div>",
        unsafe_allow_html=True)

    def bar_row(label, games, w, l, rt, sub=""):
        color = wr_color(rt)
        return (
            f"<div style='margin:6px 0'>"
            f"<div style='display:flex;justify-content:space-between;font-size:13px'>"
            f"<span><b>{label}</b> <span style='color:#7a86b0'>{sub}</span></span>"
            f"<span style='color:{color};font-weight:800'>{rt*100:.0f}% "
            f"<span style='color:#7a86b0;font-weight:400'>({w}勝{l}敗/{games}戦)</span></span></div>"
            f"<div style='height:8px;border-radius:4px;background:rgba(255,255,255,0.08);margin-top:3px'>"
            f"<div style='height:100%;width:{rt*100:.0f}%;background:{color};border-radius:4px'></div></div>"
            f"</div>")

    min_g = st.slider("分析の最小試合数(これ未満は除外)", 1, 10, 1)

    # 相手ポケモン別
    st.markdown("### 🆚 相手ポケモン別 勝率")
    st.caption("その相手が相手チームにいた試合での勝率。得意なポケモン・苦手なポケモンが分かります。")
    rows = [r for r in winrate_by_opp_pokemon(matches) if r["games"] >= min_g]
    if not rows:
        st.caption("（該当データなし）")
    else:
        good = [r for r in rows if r["rate"] >= 0.6]
        bad = [r for r in rows if r["rate"] < 0.4]
        gc, bc = st.columns(2)
        with gc:
            st.markdown("#### 💪 得意な相手 (勝率60%以上)")
            if good:
                for r in good:
                    st.markdown(bar_row(r["key"], r["games"], r["wins"], r["losses"], r["rate"]),
                                unsafe_allow_html=True)
            else:
                st.caption("（なし）")
        with bc:
            st.markdown("#### 😣 苦手な相手 (勝率40%未満)")
            if bad:
                for r in bad:
                    st.markdown(bar_row(r["key"], r["games"], r["wins"], r["losses"], r["rate"]),
                                unsafe_allow_html=True)
            else:
                st.caption("（なし）")
        with st.expander("📋 相手ポケモン別 全一覧"):
            for r in rows:
                st.markdown(bar_row(r["key"], r["games"], r["wins"], r["losses"], r["rate"]),
                            unsafe_allow_html=True)

    # 相手構築別
    st.markdown("### 🧱 相手構築(6体)別 勝率")
    st.caption("同じ6体構成と複数回戦った場合の勝率。得意・苦手な構築タイプが分かります。")
    brows = [r for r in winrate_by_build(matches) if r["games"] >= min_g]
    if not brows:
        st.caption("（該当データなし）")
    else:
        for r in brows:
            st.markdown(bar_row(r["key"], r["games"], r["wins"], r["losses"], r["rate"]),
                        unsafe_allow_html=True)

    # 相手ポケモン別 選出率
    st.markdown("### 👁 相手ポケモン別 選出率")
    st.caption("相手チームにそのポケモンがいた時、相手が実際に選出してきた割合。"
               "高いほど『相手が必ず出してくる＝警戒すべき』ポケモンです。"
               "（試合記録時に『相手の選出』を入力した試合のみ集計）")
    sel_rows = [r for r in selection_rate_opp(matches) if r["in_team"] >= min_g]
    if not sel_rows:
        st.caption("（『相手の選出』を入力した試合がまだありません）")
    else:
        for r in sel_rows:
            color = wr_color(r["rate"])
            st.markdown(
                f"<div style='margin:6px 0'>"
                f"<div style='display:flex;justify-content:space-between;font-size:13px'>"
                f"<span><b>{r['key']}</b></span>"
                f"<span style='color:{color};font-weight:800'>選出率 {r['rate']*100:.0f}% "
                f"<span style='color:#7a86b0;font-weight:400'>"
                f"({r['selected']}/{r['in_team']}回)</span></span></div>"
                f"<div style='height:8px;border-radius:4px;background:rgba(255,255,255,0.08);margin-top:3px'>"
                f"<div style='height:100%;width:{r['rate']*100:.0f}%;background:{color};border-radius:4px'>"
                f"</div></div></div>",
                unsafe_allow_html=True)

    # 自分の選出別
    st.markdown("### 🎯 自分の選出別 勝率")
    st.caption("自分が出した3体の組合せごとの勝率。勝てている選出パターンが分かります。")
    srows = [r for r in winrate_by_my_selection(matches) if r["games"] >= min_g]
    if not srows:
        st.caption("（該当データなし）")
    else:
        srows = sorted(srows, key=lambda r: (-r["rate"], -r["games"]))
        for r in srows:
            st.markdown(bar_row(r["key"], r["games"], r["wins"], r["losses"], r["rate"]),
                        unsafe_allow_html=True)

    # 試合ログ
    st.divider()
    st.markdown("### 🗒 試合ログ")
    for m in reversed(matches[-30:]):
        badge = ("<span style='color:#4ade80;font-weight:800'>WIN</span>"
                 if m["result"] == "win"
                 else "<span style='color:#f87171;font-weight:800'>LOSE</span>")
        my_s = " / ".join(m["my_selection"]) or "—"
        opp_t = " / ".join(m["opp_team"]) or "—"
        opp_s = (" / ".join(m["opp_selection"])) if m["opp_selection"] else ""
        memo = f"　📝{m['memo']}" if m["memo"] else ""
        lc1, lc2 = st.columns([10, 1])
        lc1.markdown(
            f"<div style='font-size:13px;margin:3px 0'>{badge} "
            f"<span style='color:#7a86b0'>{m['datetime']}</span><br>"
            f"<b>自分:</b> {my_s} ／ <b>相手:</b> {opp_t}"
            f"{('　<b>相手選出:</b> '+opp_s) if opp_s else ''}{memo}</div>",
            unsafe_allow_html=True)
        if lc2.button("🗑", key=f"del_match_{m['id']}"):
            data["matches"] = [x for x in data["matches"] if x["id"] != m["id"]]
            save_data(data)
            st.rerun()


if __name__ == "__main__":
    main()
