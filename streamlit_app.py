"""NSE Index Returns Dashboard — single-file build.

Everything (index map, data fetching, return maths, both pages) lives in this
one file so it can be uploaded to GitHub through the web UI without folders.

Deploy: put this file + requirements.txt in a repo, point Streamlit Community
Cloud at streamlit_app.py.

KNOWN LIMITS — read before trusting any number:
  1. Yahoo Finance throttles shared cloud IPs. Missing data renders "N/A".
  2. INDEX_MAP constituent lists below are UNVERIFIED seed data. NSE
     reconstitutes indices semi-annually plus ad-hoc on corporate actions.
     Verify against NSE's published CSVs before relying on them.
  3. Indices with index_ticker=None have no reliable Yahoo symbol and show
     N/A at index level by design. Their constituent tables still work.
  4. Stock closes are auto-adjusted (dividends/splits); NSE headline indices
     are price indices. Long-window stock vs index returns are not
     strictly like-for-like.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf
from pandas.tseries.offsets import DateOffset

st.set_page_config(
    page_title="NSE Index Returns Dashboard",
    page_icon="📈",
    layout="wide",
)

IST = ZoneInfo("Asia/Kolkata")
POSITIVE, NEGATIVE, NEUTRAL = "#0f9d58", "#d93025", "#8a8a8a"
BATCH_SIZE = 40
CACHE_TTL = 3600
HISTORY_PERIOD = "2y"

# ===========================================================================
# 1. INDEX MAP  —  edit this block to add indices or refresh constituents
# ===========================================================================
INDEX_MAP: dict[str, dict] = {
    "NIFTY 50": {
        "ticker": "^NSEI",
        "constituents": ["ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO"],
    },
    "NIFTY BANK": {
        "ticker": "^NSEBANK",
        "constituents": ["AUBANK", "AXISBANK", "BANKBARODA", "CANBK", "FEDERALBNK", "HDFCBANK", "ICICIBANK", "IDFCFIRSTB", "INDUSINDBK", "KOTAKBANK", "PNB", "SBIN"],
    },
    "NIFTY IT": {
        "ticker": "^CNXIT",
        "constituents": ["COFORGE", "HCLTECH", "INFY", "LTIM", "MPHASIS", "OFSS", "PERSISTENT", "TCS", "TECHM", "WIPRO"],
    },
    "NIFTY AUTO": {
        "ticker": "^CNXAUTO",
        "constituents": ["ASHOKLEY", "BAJAJ-AUTO", "BALKRISIND", "BHARATFORG", "BOSCHLTD", "EICHERMOT", "EXIDEIND", "HEROMOTOCO", "M&M", "MARUTI", "MOTHERSON", "MRF", "TATAMOTORS", "TIINDIA", "TVSMOTOR"],
    },
    "NIFTY FMCG": {
        "ticker": "^CNXFMCG",
        "constituents": ["BALRAMCHIN", "BRITANNIA", "COLPAL", "DABUR", "EMAMILTD", "GODREJCP", "HINDUNILVR", "ITC", "MARICO", "NESTLEIND", "PGHH", "RADICO", "TATACONSUM", "UNITDSPR", "VBL"],
    },
    "NIFTY PHARMA": {
        "ticker": "^CNXPHARMA",
        "constituents": ["ABBOTINDIA", "AJANTPHARM", "ALKEM", "AUROPHARMA", "BIOCON", "CIPLA", "DIVISLAB", "DRREDDY", "GLENMARK", "GRANULES", "IPCALAB", "JBCHEPHARM", "LAURUSLABS", "LUPIN", "MANKIND", "NATCOPHARM", "PPLPHARMA", "SUNPHARMA", "TORNTPHARM", "ZYDUSLIFE"],
    },
    "NIFTY METAL": {
        "ticker": "^CNXMETAL",
        "constituents": ["ADANIENT", "APLAPOLLO", "HINDALCO", "HINDCOPPER", "HINDZINC", "JINDALSTEL", "JSL", "JSWSTEEL", "LLOYDSME", "NATIONALUM", "NMDC", "SAIL", "TATASTEEL", "VEDL", "WELCORP"],
    },
    "NIFTY ENERGY": {
        "ticker": "^CNXENERGY",
        "constituents": ["ADANIGREEN", "BPCL", "COALINDIA", "GAIL", "IOC", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "TATAPOWER"],
    },
    "NIFTY FIN SERVICE": {
        "ticker": None,
        "constituents": ["AXISBANK", "BAJAJFINSV", "BAJFINANCE", "CHOLAFIN", "HDFCAMC", "HDFCBANK", "HDFCLIFE", "ICICIBANK", "ICICIGI", "ICICIPRULI", "JIOFIN", "KOTAKBANK", "LICHSGFIN", "MUTHOOTFIN", "PFC", "RECLTD", "SBICARD", "SBILIFE", "SBIN", "SHRIRAMFIN"],
    },
    "NIFTY REALTY": {
        "ticker": "^CNXREALTY",
        "constituents": ["ANANTRAJ", "BRIGADE", "DLF", "GODREJPROP", "LODHA", "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE", "RAYMOND", "SOBHA"],
    },
    "NIFTY PSU BANK": {
        "ticker": "^CNXPSUBANK",
        "constituents": ["BANKBARODA", "BANKINDIA", "CANBK", "CENTRALBK", "INDIANB", "IOB", "MAHABANK", "PNB", "PSB", "SBIN", "UCOBANK", "UNIONBANK"],
    },
    "NIFTY MEDIA": {
        "ticker": "^CNXMEDIA",
        "constituents": ["DISHTV", "HATHWAY", "NAZARA", "NETWORK18", "PVRINOX", "SAREGAMA", "SUNTV", "TIPSMUSIC", "TV18BRDCST", "ZEEL"],
    },
    "NIFTY NEXT 50": {"ticker": "^NSMIDCP", "constituents": []},
    "NIFTY 100": {"ticker": "^CNX100", "constituents": []},
    "NIFTY 500": {"ticker": "^CRSLDX", "constituents": []},
    "NIFTY MIDCAP 100": {"ticker": None, "constituents": []},
    "NIFTY SMALLCAP 100": {"ticker": None, "constituents": []},
}

CONSTITUENTS_VERIFIED = False  # set True after you check the lists against NSE

# ===========================================================================
# 2. RETURN PERIODS
# ===========================================================================
# 1D/3D use trading-day offsets: a calendar 1-day return is 0% Monday-to-Monday
# and null over a holiday. 1W and longer use calendar offsets resolved to the
# last close on or before the target date.
PERIODS: dict[str, dict] = {
    "1D": {"kind": "trading", "n": 1},
    "3D": {"kind": "trading", "n": 3},
    "1W": {"kind": "calendar", "offset": DateOffset(days=7)},
    "2W": {"kind": "calendar", "offset": DateOffset(days=14)},
    "1M": {"kind": "calendar", "offset": DateOffset(months=1)},
    "2M": {"kind": "calendar", "offset": DateOffset(months=2)},
    "3M": {"kind": "calendar", "offset": DateOffset(months=3)},
    "6M": {"kind": "calendar", "offset": DateOffset(months=6)},
    "1Y": {"kind": "calendar", "offset": DateOffset(years=1)},
}
PERIOD_LABELS = list(PERIODS)

PERIOD_HELP = {
    "1D": "Previous trading day close",
    "3D": "3 trading days ago",
    "1W": "7 calendar days ago (last close on/before)",
    "2W": "14 calendar days ago",
    "1M": "1 calendar month ago",
    "2M": "2 calendar months ago",
    "3M": "3 calendar months ago",
    "6M": "6 calendar months ago",
    "1Y": "1 calendar year ago",
}


def to_yahoo(symbol: str) -> str:
    symbol = symbol.strip().upper()
    return symbol if symbol.startswith("^") or symbol.endswith(".NS") else f"{symbol}.NS"


def _as_of(series: pd.Series, target: pd.Timestamp) -> float | None:
    window = series.loc[:target]
    return None if window.empty else float(window.iloc[-1])


def compute_returns(series: pd.Series | None) -> dict[str, float | None]:
    empty = {label: None for label in PERIOD_LABELS}
    if series is None or len(series) == 0:
        return empty
    series = pd.Series(series).dropna().sort_index()
    series = series[series > 0]
    if len(series) < 2:
        return empty

    last = float(series.iloc[-1])
    last_date = series.index[-1]
    out: dict[str, float | None] = {}
    for label, spec in PERIODS.items():
        if spec["kind"] == "trading":
            n = spec["n"]
            base = float(series.iloc[-1 - n]) if len(series) > n else None
        else:
            target = last_date - spec["offset"]
            # Require genuine coverage: without this a 6-month-old listing
            # would report a fake 1Y return off its first available close.
            base = _as_of(series, target) if series.index[0] <= target else None
        out[label] = None if not base else (last - base) / base * 100.0
    return out


def returns_frame(label_to_series: dict, name_column: str = "Name") -> pd.DataFrame:
    rows = []
    for name, series in label_to_series.items():
        row = {name_column: name}
        row.update(compute_returns(series))
        rows.append(row)
    return pd.DataFrame(rows, columns=[name_column, *PERIOD_LABELS])


def last_price_date(label_to_series: dict) -> pd.Timestamp | None:
    dates = [
        s.dropna().index[-1]
        for s in label_to_series.values()
        if s is not None and len(s.dropna()) > 0
    ]
    return max(dates) if dates else None


# ===========================================================================
# 3. DATA FETCH
# ===========================================================================
def _extract_close(raw: pd.DataFrame, tickers: list[str]) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    if raw is None or raw.empty:
        return out
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        for ticker in tickers:
            try:
                series = raw["Close"][ticker] if "Close" in level0 else raw[ticker]["Close"]
            except (KeyError, IndexError):
                continue
            series = series.dropna()
            if not series.empty:
                out[ticker] = series
    elif "Close" in raw.columns and len(tickers) == 1:
        series = raw["Close"].dropna()
        if not series.empty:
            out[tickers[0]] = series
    return out


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_close_prices(tickers: tuple[str, ...]) -> dict[str, pd.Series]:
    """Batched daily closes. A failed ticker is omitted, not raised — one bad
    symbol must not blank the other 49."""
    tickers = tuple(dict.fromkeys(t for t in tickers if t))
    result: dict[str, pd.Series] = {}
    for start in range(0, len(tickers), BATCH_SIZE):
        batch = list(tickers[start : start + BATCH_SIZE])
        try:
            raw = yf.download(
                batch,
                period=HISTORY_PERIOD,
                interval="1d",
                auto_adjust=True,
                actions=False,
                progress=False,
                threads=True,
                group_by="column",
            )
        except Exception:
            continue
        result.update(_extract_close(raw, batch))
    return result


# ===========================================================================
# 4. DISPLAY
# ===========================================================================
def _colour(value) -> str:
    if pd.isna(value):
        return f"color: {NEUTRAL}"
    if value > 0:
        return f"color: {POSITIVE}; font-weight: 600"
    if value < 0:
        return f"color: {NEGATIVE}; font-weight: 600"
    return f"color: {NEUTRAL}"


def style_returns(df: pd.DataFrame):
    cols = [c for c in PERIOD_LABELS if c in df.columns]
    return df.style.map(_colour, subset=cols).format(
        {c: "{:+.2f}%" for c in cols}, na_rep="N/A"
    )


def coverage_note(df: pd.DataFrame) -> str | None:
    cols = [c for c in PERIOD_LABELS if c in df.columns]
    if not cols or df.empty:
        return None
    missing = int(df[cols].isna().all(axis=1).sum())
    return None if missing == 0 else f"{missing} of {len(df)} rows returned no price data."


def column_config(name_label: str) -> dict:
    config = {"Name": st.column_config.TextColumn(name_label, width="medium")}
    for label in PERIOD_LABELS:
        config[label] = st.column_config.TextColumn(label, help=PERIOD_HELP[label])
    return config


def timestamp_caption(series_map: dict) -> None:
    as_of = last_price_date(series_map)
    stamp = datetime.now(IST).strftime("%d %b %Y, %H:%M IST")
    st.caption(
        f"Last updated: {stamp}  ·  Latest close in data: "
        f"{as_of.strftime('%d %b %Y') if as_of is not None else 'unavailable'}  ·  "
        f"Cache TTL 60 min  ·  Source: Yahoo Finance via yfinance"
    )


# ===========================================================================
# 5. PAGES  (routed through st.session_state — no pages/ folder needed)
# ===========================================================================
def home_page() -> None:
    header, refresh = st.columns([5, 1])
    with header:
        st.title("📈 NSE Index Returns Dashboard")
    with refresh:
        st.write("")
        if st.button("🔄 Refresh Data", use_container_width=True):
            fetch_close_prices.clear()
            st.rerun()

    tickers = tuple(v["ticker"] for v in INDEX_MAP.values() if v["ticker"])
    with st.spinner("Fetching index prices…"):
        prices = fetch_close_prices(tickers)

    series = {
        name: prices.get(cfg["ticker"]) if cfg["ticker"] else None
        for name, cfg in INDEX_MAP.items()
    }
    df = returns_frame(series)

    query = st.text_input("Search index", placeholder="e.g. BANK, PHARMA, MIDCAP").strip()
    view = df[df["Name"].str.contains(query, case=False, na=False)] if query else df
    view = view.reset_index(drop=True)

    st.caption("Click a row to open the index detail page. Click a column header to sort.")

    selection = st.dataframe(
        style_returns(view),
        use_container_width=True,
        hide_index=True,
        height=min(640, 40 + 36 * max(len(view), 1)),
        column_config=column_config("Index"),
        on_select="rerun",
        selection_mode="single-row",
        key="index_table",
    )

    rows = selection.get("selection", {}).get("rows", []) if selection else []
    if rows:
        st.session_state["selected_index"] = view.iloc[rows[0]]["Name"]
        st.session_state["view"] = "detail"
        st.rerun()

    timestamp_caption(series)

    note = coverage_note(df)
    if note:
        st.warning(
            f"{note} Indices with ticker=None have no reliable Yahoo symbol and always "
            "show N/A at index level — their constituent tables still work."
        )
    if not CONSTITUENTS_VERIFIED:
        st.info(
            "Constituent lists in INDEX_MAP are unverified seed data. Check them "
            "against NSE's published index CSVs, then set CONSTITUENTS_VERIFIED = True."
        )


def detail_page() -> None:
    if st.button("⬅ Back to all indices"):
        st.session_state["view"] = "home"
        st.rerun()

    name = st.session_state.get("selected_index")
    if name not in INDEX_MAP:
        name = st.selectbox("Pick an index", list(INDEX_MAP))
        st.session_state["selected_index"] = name

    cfg = INDEX_MAP[name]
    constituents = cfg["constituents"]
    stock_tickers = tuple(to_yahoo(s) for s in constituents)
    all_tickers = tuple(t for t in (cfg["ticker"], *stock_tickers) if t)

    with st.spinner(f"Fetching {len(all_tickers)} tickers…"):
        prices = fetch_close_prices(all_tickers)

    index_series = prices.get(cfg["ticker"]) if cfg["ticker"] else None
    index_returns = compute_returns(index_series)

    st.subheader(name)
    cols = st.columns(len(PERIOD_LABELS))
    for col, label in zip(cols, PERIOD_LABELS):
        value = index_returns.get(label)
        text = "N/A" if value is None else f"{value:+.2f}%"
        colour = NEUTRAL if value is None else (POSITIVE if value > 0 else NEGATIVE if value < 0 else NEUTRAL)
        col.markdown(
            f"<div style='text-align:center'>"
            f"<div style='font-size:0.75rem;color:{NEUTRAL}'>{label}</div>"
            f"<div style='font-size:1.15rem;font-weight:700;color:{colour}'>{text}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    if cfg["ticker"] is None:
        st.caption("No Yahoo symbol mapped for this index — set 'ticker' in INDEX_MAP.")

    st.divider()

    if not constituents:
        st.info(f"No constituents stored for {name}. Add them to INDEX_MAP.")
        return

    stock_series = {sym: prices.get(to_yahoo(sym)) for sym in constituents}
    df = returns_frame(stock_series, name_column="Name")

    st.markdown(f"**Constituents — {len(constituents)} stocks**")
    query = st.text_input("Search stock", placeholder="e.g. HDFC, TATA").strip()
    view = df[df["Name"].str.contains(query, case=False, na=False)] if query else df
    view = view.reset_index(drop=True)

    st.dataframe(
        style_returns(view),
        use_container_width=True,
        hide_index=True,
        height=min(700, 40 + 36 * max(len(view), 1)),
        column_config=column_config("Symbol"),
    )

    st.download_button(
        "⬇ Export to CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"{name.replace(' ', '_').lower()}_returns.csv",
        mime="text/csv",
    )

    timestamp_caption({**stock_series, "_index": index_series})

    note = coverage_note(df)
    if note:
        st.warning(
            f"{note} Usual causes: symbol renamed after a corporate action, recent "
            "listing with under 1 year of history, or Yahoo rate-limiting."
        )


def main() -> None:
    if st.session_state.get("view") == "detail":
        detail_page()
    else:
        home_page()


if __name__ == "__main__":
    main()
