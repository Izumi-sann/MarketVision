from __future__ import annotations

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import pandas as pd
import plotly.express as px
import streamlit as st

from InstaIntegration import (
    PostRecord,
    fetch_official_insights,
    fetch_public_profile_posts,
    summarize_posts,
)
import db


st.set_page_config(
    page_title="MarketVision Instagram Dashboard",
    page_icon="📈",
    layout="wide",
)

# Ensure database exists
DB_PATH = db.init_db()


def _rows_to_posts(rows: list[dict]) -> list[PostRecord]:
    posts: list[PostRecord] = []
    for row in rows:
        posted_at_raw = row.get("posted_at")
        posted_at = datetime.fromisoformat(posted_at_raw) if posted_at_raw else datetime.utcnow()
        posts.append(
            PostRecord(
                username=row.get("account") or row.get("username") or "",
                shortcode=row.get("shortcode") or "",
                post_url=row.get("post_url") or "",
                post_type=row.get("post_type") or "photo",
                posted_at=posted_at,
                likes=int(row.get("likes") or 0),
                comments=int(row.get("comments") or 0),
                views=(int(row["views"]) if row.get("views") is not None else None),
                caption=row.get("caption"),
            )
        )
    return posts

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg, #08111f 0%, #0d1729 45%, #101b31 100%);
        color: #eef2ff;
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .hero {
        padding: 1.4rem 1.6rem;
        border-radius: 22px;
        background: linear-gradient(135deg, rgba(80, 113, 255, 0.26), rgba(18, 26, 46, 0.92));
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 18px 60px rgba(0,0,0,0.25);
        margin-bottom: 1.25rem;
    }
    .small-label {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: rgba(238, 242, 255, 0.72);
        margin-bottom: 0.25rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="small-label">MarketVision</div>
        <h1 style="margin: 0; color: #ffffff;">Instagram Competitive Dashboard</h1>
        <p style="margin: 0.4rem 0 0 0; color: rgba(238, 242, 255, 0.84); max-width: 900px;">
            Analizza gli ultimi post pubblici di un profilo, il tipo di contenuto, engagement e frequenza di pubblicazione.
            Per gli account proprietari puoi anche leggere gli insights ufficiali via Meta Graph API.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Configurazione")
    usernames_input = st.text_area(
        "Profili Instagram da analizzare",
        value="nike\nadidas",
        height=120,
        help="Inserisci uno username per riga oppure separato da virgole.",
    )
    max_posts = st.slider("Post recenti per profilo", 3, 30, 12)
    load_button = st.button("Carica dati", width='stretch')

profile_names = [name.strip().lstrip("@") for part in usernames_input.splitlines() for name in part.split(",") if name.strip()]

if load_button and profile_names:
    st.session_state["profiles"] = profile_names
    st.session_state["max_posts"] = max_posts

profiles = st.session_state.get("profiles", profile_names)
max_posts = st.session_state.get("max_posts", max_posts)

if not profiles:
    st.info("Inserisci almeno uno username per iniziare.")
    st.stop()

all_tables: list[pd.DataFrame] = []

for profile in profiles:
    with st.container(border=True):
        st.subheader(f"@{profile}")
        try:
            posts = fetch_public_profile_posts(profile, max_posts=max_posts)
        except Exception as exc:
            cached_rows = db.fetch_snapshots(profile, db_path=DB_PATH)
            if not cached_rows:
                st.error(f"Impossibile caricare @{profile}: {exc}")
                continue

            posts = _rows_to_posts(cached_rows)
            st.warning(f"Caricamento live non disponibile per @{profile}: {exc}. Uso l'ultimo snapshot locale.")

        summary = summarize_posts(posts)
        table = pd.DataFrame([item.to_dict() for item in posts])
        table["posted_at"] = pd.to_datetime(table["posted_at"])
        table["account"] = profile
        all_tables.append(table)

        try:
            db.save_posts_snapshot(profile, posts, db_path=DB_PATH)
        except Exception:
            # non-blocking: if DB write fails, continue showing UI
            st.warning("Attenzione: impossibile salvare lo snapshot nel DB locale.")

        top_cols = st.columns(4)
        top_cols[0].metric("Post caricati", summary["count"])
        top_cols[1].metric("Frequenza media", f"{summary['avg_days_between_posts']} giorni" if summary["avg_days_between_posts"] is not None else "N/D")
        top_cols[2].metric("Like medi", summary["avg_likes"])
        top_cols[3].metric("Commenti medi", summary["avg_comments"])

        chart_cols = st.columns([1, 1])
        with chart_cols[0]:
            type_df = pd.DataFrame(
                [{"tipo": key, "conteggio": value} for key, value in summary["type_counts"].items()]
            )
            if not type_df.empty:
                fig = px.bar(
                    type_df,
                    x="tipo",
                    y="conteggio",
                    color="tipo",
                    title="Distribuzione tipi post",
                )
                fig.update_layout(height=330, margin=dict(l=10, r=10, t=50, b=10), showlegend=False)
                st.plotly_chart(fig, width='stretch')
            else:
                st.caption("Nessun dato sui tipi post disponibile.")

        with chart_cols[1]:
            engagement_df = table.sort_values("posted_at")[["posted_at", "likes", "comments"]]
            melted = engagement_df.melt(id_vars="posted_at", var_name="metrica", value_name="valore")
            fig = px.line(
                melted,
                x="posted_at",
                y="valore",
                color="metrica",
                markers=True,
                title="Like e commenti sugli ultimi post",
            )
            fig.update_layout(height=330, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, width='stretch')

        st.markdown("#### Ultimi post")
        display_table = table[["posted_at", "post_type", "likes", "comments", "views", "post_url"]].copy()
        display_table = display_table.rename(
            columns={
                "posted_at": "data",
                "post_type": "tipo",
                "likes": "like",
                "comments": "commenti",
                "views": "views",
                "post_url": "link",
            }
        )
        st.dataframe(display_table, width='stretch', hide_index=True)

        if summary["avg_views"] is not None:
            st.metric("Views medie sui post video", summary["avg_views"])
        if summary.get("views_coverage_pct") is not None:
            st.metric(
                "Copertura views video",
                f"{summary['views_coverage_pct']}%",
                help="Quota di post video per cui Instagram espone un conteggio views leggibile.",
            )

if all_tables:
    combined = pd.concat(all_tables, ignore_index=True)
    combined["posted_at"] = pd.to_datetime(combined["posted_at"])

    # Feature engineering for cross-format comparison.
    combined["post_kind"] = combined["post_type"].replace({
        "carousel": "foto",
        "photo": "foto",
        "video": "video",
        "reel": "video",
    })

    def _zscore(series: pd.Series) -> pd.Series:
        series = pd.to_numeric(series, errors="coerce")
        std = series.std(ddof=0)
        if pd.isna(std) or std == 0:
            return pd.Series([0.0] * len(series), index=series.index)
        return (series - series.mean()) / std

    combined["z_likes"] = _zscore(combined["likes"])
    combined["z_comments"] = _zscore(combined["comments"])
    combined["z_views"] = pd.NA
    video_mask = combined["views"].notna() & (combined["views"] > 0)
    if video_mask.any():
        combined.loc[video_mask, "z_views"] = _zscore(combined.loc[video_mask, "views"])

    # Common score for photo/video comparison: only metrics shared by both formats.
    combined["common_appreciation_score"] = (combined["z_likes"] + combined["z_comments"]) / 2
    # Video-specific reach signal, kept separate from the cross-format score.
    combined["video_reach_score"] = combined["z_views"]
    combined["engagement_score"] = (combined["z_likes"] + combined["z_comments"]) / 2
    combined["comment_to_like_ratio"] = combined["comments"] / combined["likes"].replace(0, pd.NA)

    st.markdown("### Confronto tra profili")
    summary_rows = []
    for account, group in combined.groupby("account"):
        ordered_group = group.sort_values("posted_at")
        deltas = ordered_group["posted_at"].diff().dt.total_seconds().dropna() / 86400
        summary_rows.append(
            {
                "account": account,
                "post": len(group),
                "like_medi": round(group["likes"].mean(), 2),
                "commenti_medi": round(group["comments"].mean(), 2),
                "frequenza_media_giorni": round(deltas.mean(), 2) if not deltas.empty else None,
            }
        )

    comparison_df = pd.DataFrame(summary_rows).sort_values("like_medi", ascending=False)
    st.dataframe(comparison_df, width='stretch', hide_index=True)

    if not comparison_df.empty:
        fig = px.bar(
            comparison_df,
            x="account",
            y="like_medi",
            title="Confronto like medi per account",
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width='stretch')

    st.markdown("### Foto vs Video: indice normalizzato")
    kind_summary = (
        combined.groupby("post_kind", dropna=False)
        .agg(
            post_count=("post_kind", "size"),
            score_media=("common_appreciation_score", "mean"),
            score_mediana=("common_appreciation_score", "median"),
            z_like_media=("z_likes", "mean"),
            z_commenti_media=("z_comments", "mean"),
            z_views_media=("video_reach_score", "mean"),
            like_medi=("likes", "mean"),
            commenti_medi=("comments", "mean"),
            views_medi=("views", "mean"),
        )
        .reset_index()
        .sort_values("post_kind")
    )

    kind_col1, kind_col2 = st.columns([1.1, 0.9])
    with kind_col1:
        st.dataframe(kind_summary, width='stretch', hide_index=True)
    with kind_col2:
        fig = px.bar(
            kind_summary,
            x="post_kind",
            y="score_media",
            color="post_kind",
            title="Indice normalizzato medio per tipo post",
            text_auto=True,
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10), showlegend=False)
        st.plotly_chart(fig, width='stretch')

    st.markdown("#### Distribuzione punteggi normalizzati")
    dist_fig = px.violin(
        combined,
        x="post_kind",
        y="common_appreciation_score",
        box=True,
        points="all",
        color="post_kind",
        title="Foto vs video: distribuzione dell'indice comune normalizzato",
    )
    dist_fig.update_layout(height=420, margin=dict(l=10, r=10, t=50, b=10), showlegend=False)
    st.plotly_chart(dist_fig, width='stretch')

    st.markdown("#### Andamento nel tempo dell'indice comune")
    timeline_frames = []
    for kind, group in combined.sort_values("posted_at").groupby("post_kind", dropna=False):
        group = group.copy()
        group["score_roll"] = group["common_appreciation_score"].rolling(window=min(5, len(group)), min_periods=1).mean()
        timeline_frames.append(group)
    timeline_df = pd.concat(timeline_frames, ignore_index=True) if timeline_frames else combined.copy()
    line_fig = px.line(
        timeline_df,
        x="posted_at",
        y="score_roll",
        color="post_kind",
        markers=True,
        title="Trend dell'indice normalizzato nel tempo",
    )
    line_fig.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(line_fig, width='stretch')

    st.markdown("#### Top post per indice comune normalizzato")
    top_posts = combined.sort_values("common_appreciation_score", ascending=False)[
        ["account", "post_kind", "posted_at", "likes", "comments", "views", "common_appreciation_score", "video_reach_score", "post_url"]
    ].head(10)
    top_posts = top_posts.rename(
        columns={
            "post_kind": "tipo",
            "posted_at": "data",
            "likes": "like",
            "comments": "commenti",
            "views": "views",
            "common_appreciation_score": "indice_comune",
            "video_reach_score": "reach_video",
            "post_url": "link",
        }
    )
    st.dataframe(top_posts, width='stretch', hide_index=True)

    st.caption(
        "L'indice comune usa solo like e commenti, quindi foto e video sono confrontabili. Le views restano separate come segnale di reach solo per i video."
    )

st.markdown("---")
st.markdown("### Insights account proprietario")
st.caption(
    "Per gli account gestiti da voi puoi usare IG_USER_ID e ACCESS_TOKEN per recuperare gli insights ufficiali."
)

insight_cols = st.columns([1, 1, 1])
with insight_cols[0]:
    ig_user_id = st.text_input("IG_USER_ID", value=os.getenv("IG_USER_ID", ""))
with insight_cols[1]:
    access_token = st.text_input("ACCESS_TOKEN", value=os.getenv("ACCESS_TOKEN", ""), type="password")
with insight_cols[2]:
    fetch_insights_button = st.button("Leggi insights", width='stretch')

if fetch_insights_button:
    try:
        insights = fetch_official_insights(ig_user_id, access_token)
        insight_rows = []
        for item in insights:
            values = item.get("values", [])
            insight_rows.append(
                {
                    "metrica": item.get("name"),
                    "valore": values[0].get("value") if values else None,
                }
            )
        st.dataframe(pd.DataFrame(insight_rows), width='stretch', hide_index=True)
    except Exception as exc:
        st.error(f"Errore nel recupero degli insights: {exc}")


st.markdown("---")
st.markdown("### Cronologia snapshot salvati")
accounts_in_db = db.list_accounts(DB_PATH)
if not accounts_in_db:
    st.info("Nessuno snapshot ancora salvato nel DB locale. Carica prima qualche profilo.")
else:
    hist_col1, hist_col2 = st.columns([2, 1])
    with hist_col1:
        selected_account = st.selectbox("Seleziona account", options=accounts_in_db)
    with hist_col2:
        load_history = st.button("Carica cronologia", width='stretch')

    if load_history:
        try:
            rows = db.fetch_snapshots(selected_account, db_path=DB_PATH)
            import pandas as pd

            df = pd.DataFrame(rows)
            if df.empty:
                st.warning("Nessun record trovato per questo account.")
            else:
                df["posted_at"] = pd.to_datetime(df["posted_at"]) 
                df["snapshot_at"] = pd.to_datetime(df["snapshot_at"]) 
                # show most recent snapshot per post
                st.markdown(f"#### Snapshot records per @{selected_account} (ultimi {len(df)} righe)")
                st.dataframe(df[["snapshot_at", "posted_at", "post_type", "likes", "comments", "views", "post_url"]], width='stretch')

                # show posts captured over time (count per snapshot)
                counts = df.groupby("snapshot_at").size().reset_index(name="posts_count")
                fig = px.line(counts, x="snapshot_at", y="posts_count", markers=True, title="Numero post catturati per snapshot nel tempo")
                st.plotly_chart(fig, width='stretch')
        except Exception as exc:
            st.error(f"Errore nel caricamento della cronologia: {exc}")