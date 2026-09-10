from scripts.update import main as refresh_market_data
from pathlib import Path
import json, html, subprocess, sys
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import requests
from io import BytesIO
ROOT = Path(__file__).parent
OUT = ROOT / 'data' / 'snapshots'

WORKBOOK_URL = "https://albionfinancial.sharepoint.com/:x:/g/IQAKJ_K4HfyQT7KiKzFz85SXAaUdKpYhcfSyfgP7xl7Kel4?e=bb46E8&download=1"

@st.cache_data(ttl=300)
def load_workbook():
    r = requests.get(WORKBOOK_URL)
    r.raise_for_status()

    return {
        "editorial": pd.read_excel(
            BytesIO(r.content),
            sheet_name="Editorial",
            engine="openpyxl"
        ),
        "economic": pd.read_excel(
            BytesIO(r.content),
            sheet_name="Economic Indicators",
            engine="openpyxl"
        ),
        "money_market": pd.read_excel(
            BytesIO(r.content),
            sheet_name="Money Market Fund Yields",
            engine="openpyxl"
        ),
        "mappings": pd.read_excel(
            BytesIO(r.content),
            sheet_name="Source Mappings",
            engine="openpyxl"
        )
    }


st.set_page_config(page_title='Jason Ware Daily',page_icon='📈',layout='wide');st.markdown('<style>'+Path('assets/style.css').read_text()+'</style>',unsafe_allow_html=True)
def read_json(p,d):
    try:return json.loads(p.read_text(encoding='utf-8'))
    except:return d
def stamp(v):return 'Not available' if not v else pd.to_datetime(v,utc=True).tz_convert('America/Los_Angeles').strftime('%b %d, %Y | %I:%M %p PT')
def cell_color(v):return '' if pd.isna(v) else 'color:#2E7D32;font-weight:600' if v>0 else 'color:#C62828;font-weight:600' if v<0 else 'color:#667782'
RET=['Today','WTD','MTD','QTD','YTD','3Y Cum.','5Y Cum.','10Y Cum.']
def perf(rows,fixed=False):
    d=pd.DataFrame(rows);first='Yield' if fixed else 'Close';cols=['Description',first,*RET];d=d.reindex(columns=cols);sty=d.style.format({first:'{:.2%}' if fixed else '{:,.2f}',**{c:'{:+.2%}' for c in RET}},na_rep='N/A')
    for c in RET:sty=sty.map(cell_color,subset=[c])
    return sty
def sector_chart(rows,key,title):
    d = pd.DataFrame(rows).set_index('Description')[key].dropna().sort_values()
    values = d * 100
    lo = float(values.min())
    hi = float(values.max())
    span = max(hi - lo, 1.0)
    left_pad = max(span * 0.25, 2.0) if lo < 0 else max(span * 0.03, 0.30)
    right_pad = max(span * 0.06, 0.55)
    fig = go.Figure(
        go.Bar(
            x=values,
            y=d.index,
            orientation='h',
            marker_color=[
                '#2D6A9F' if n == 'S&P 500'
                else '#2E7D32' if v >= 0
                else '#C62828'
                for n, v in d.items()
            ],
            text=[f'{v:+.1%}' for v in d],
            textposition='outside',
            cliponaxis=False,
            constraintext='none'
        )
    )
    fig.update_layout(
        title=title,
        height=475,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=180, r=85, t=55, b=40),
        xaxis=dict(
            range=[min(0, lo) - left_pad, max(0, hi) + right_pad],
            ticksuffix='%',
            zeroline=True,
            zerolinecolor='#D0D7DE'
        ),
        yaxis=dict(automargin=True),
        uniformtext_minsize=10,
        uniformtext_mode='show'
    )
    return fig

refresh_market_data()
s = read_json(OUT/'current.json', {})

wb = load_workbook()

editorial = wb["editorial"]

e = {
    "quote": editorial.loc[
        editorial["Field"]=="Quote",
        "Value"
    ].iloc[0],

    "attribution": editorial.loc[
        editorial["Field"]=="Attribution",
        "Value"
    ].iloc[0],

    "commentary": editorial.loc[
        editorial["Field"]=="Commentary",
        "Value"
    ].iloc[0]
};

left,right=st.columns([4,1])
with left:st.caption('Daily Market Recap')
with right:st.markdown(f'<div class=meta><b>Updated:</b> {html.escape(stamp(s.get("generated_at")))}</div>',unsafe_allow_html=True)
st.markdown('<div class=q>&ldquo;'+html.escape(e.get('quote',''))+'&rdquo;<small>'+html.escape(e.get('attribution',''))+'</small></div>',unsafe_allow_html=True);
st.subheader('Jason Ware Daily');st.markdown('<div class=c>'+html.escape(e.get('commentary','')).replace('\n','<br>')+'</div>',unsafe_allow_html=True)
if not s:st.warning('No snapshot yet. Use Editor & Settings to refresh.');st.stop()
st.divider()
st.subheader('Risk-On / Risk-Off Dashboard');cols=st.columns([1.1,1.15,1.1,1.05,1.35,0.95])
for col,z in zip(cols,s.get('risk',[])):
    with col:
        if z['Yield']:
            display_value = f"{z['Current']:.2f}%"
        elif z['Asset'] in ['U.S. Dollar Index', 'VIX']:
            display_value = f"{z['Current']:,.2f}"
        else:
            display_value = f"{z['Current']:,.0f}"
        st.metric(z['Asset'],display_value,f"{z['Change']:+.2f} pts" if z['Yield'] else f"{z['Change']:+.2%}")
st.divider();st.subheader('Major Equity Indices');st.dataframe(perf(s.get('equities',[])),use_container_width=True,hide_index=True)
st.divider();st.subheader('Sector Performance');a,b=st.columns(2)
with a:st.plotly_chart(sector_chart(s.get('sectors',[]),'Today','Sector Performance Today'),use_container_width=True)
with b:st.plotly_chart(sector_chart(s.get('sectors',[]),'YTD','Sector Performance YTD'),use_container_width=True)
st.divider();st.subheader('Fixed Income Benchmarks');st.dataframe(perf(s.get('fixed_income',[]),True),use_container_width=True,hide_index=True)
st.divider();st.subheader('Treasury Yield Curve');curve=s.get('curve',{})
if curve:
    maturities=list(curve);fig=go.Figure()
    for key,name,line_color,dash in [('Current','Current','#4DA3FF','solid'),('1 Month Prior','1 Month Prior','#8CB8E8','dash'),('1 Year Prior','1 Year Prior','#777777','dot')]:fig.add_trace(go.Scatter(x=maturities,y=[curve[x][key] for x in maturities],mode='lines+markers',name=name,line=dict(color=line_color,width=3,dash=dash)))
    vals=[curve[x][k] for x in maturities for k in ['Current','1 Month Prior','1 Year Prior'] if curve[x].get(k) is not None];fig.update_layout(height=480,plot_bgcolor='rgba(0,0,0,0)',paper_bgcolor='rgba(0,0,0,0)',yaxis_title='Yield (%)',yaxis_range=[0,max(6,max(vals)*1.15)],legend=dict(orientation='h',y=1.12));st.plotly_chart(fig,use_container_width=True)
    t=pd.DataFrame([{'Maturity':x,'Current':curve[x]['Current'],'1 Month Prior':curve[x]['1 Month Prior'],'1 Year Prior':curve[x]['1 Year Prior']} for x in maturities]);st.dataframe(t.style.format({'Current':'{:.2f}%','1 Month Prior':'{:.2f}%','1 Year Prior':'{:.2f}%'}),use_container_width=True,hide_index=True)
else:st.info('Treasury yield data is unavailable.')
for title,key in [('Commodities','commodities'),('Global Markets & Currency Trends','global_markets')]:st.divider();st.subheader(title);st.dataframe(perf(s.get(key,[])),use_container_width=True,hide_index=True)

st.divider()
st.subheader('Economic Indicators')
economic = wb["economic"]
st.dataframe(
    economic,
    use_container_width=True,
    hide_index=True)
money_market = wb["money_market"]

st.divider()
st.subheader('Money Market Fund Yields')

st.dataframe(
    money_market,
    use_container_width=True,
    hide_index=True
)
st.divider()

if st.button("🔄 Refresh Commentary and Manual Entries"):
    st.cache_data.clear()
    st.rerun()

if st.button("📈 Refresh Market Data"):
    refresh_market_data()

    s = read_json(OUT/'current.json', {})

    st.cache_data.clear()

    st.success(
        f"Market data refreshed. Snapshot: {s.get('snapshot_id')}"
    )

    st.rerun()
