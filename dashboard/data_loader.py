import pandas as pd
import numpy as np
from pathlib import Path
from functools import lru_cache

DATA_PATH = Path(__file__).parent / 'data_transformed.csv'

MONTH_ORDER = [
    'January','February','March','April','May','June',
    'July','August','September','October','November','December'
]

SEASON_MAP = {
    'Dec\x96Jan\x96Feb': 'DJF (Winter)',
    'Mar\x96Apr\x96May': 'MAM (Spring)',
    'Jun\x96Jul\x96Aug': 'JJA (Summer)',
    'Sep\x96Oct\x96Nov': 'SON (Autumn)',
}

# Non-sovereign territories (FAO area codes)
TERRITORY_CODES = {
    5,22,25,36,42,43,47,64,65,70,82,85,87,96,
    127,128,135,139,142,153,160,161,164,172,187,
    190,214,218,224,239,240,242,243,244,258,259,
    260,270,271,299
}

# FAO name → Plotly/ISO name fixes for choropleth
COUNTRY_NAME_MAP = {
    'United States of America': 'United States',
    'United Kingdom of Great Britain and Northern Ireland': 'United Kingdom',
    'Bolivia (Plurinational State of)': 'Bolivia',
    'Venezuela (Bolivarian Republic of)': 'Venezuela',
    'Iran (Islamic Republic of)': 'Iran',
    "Korea, Democratic People's Republic of": 'North Korea',
    'Korea, Republic of': 'South Korea',
    'China, mainland': 'China',
    'China, Taiwan Province of': 'Taiwan',
    'Congo': 'Republic of the Congo',
    'Democratic Republic of the Congo': 'Democratic Republic of Congo',
    "Côte d'Ivoire": 'Ivory Coast',
    'Czechia': 'Czech Republic',
    'North Macedonia': 'Macedonia',
    'Eswatini': 'Swaziland',
    'Viet Nam': 'Vietnam',
    'Syrian Arab Republic': 'Syria',
    "Lao People's Democratic Republic": 'Laos',
    'Tanzania, United Republic of': 'Tanzania',
    'Moldova, Republic of': 'Moldova',
    'Russian Federation': 'Russia',
    'Türkiye': 'Turkey',
    'Cabo Verde': 'Cape Verde',
    'Timor-Leste': 'East Timor',
    'Brunei Darussalam': 'Brunei',
    'Micronesia (Federated States of)': 'Micronesia',
    'Sudan (former)': 'Sudan',
}

@lru_cache(maxsize=1)
def load_data():
    df = pd.read_csv(DATA_PATH, encoding='utf-8')
    # Fix seasonal labels
    df['Months'] = df['Months'].replace(SEASON_MAP)
    # Tag territories
    df['is_territory'] = df['Area Code'].isin(TERRITORY_CODES)
    # Ensure Year is int and Value is float
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce').astype('Int64')
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
    return df

def get_tc(include_territories=False, months_filter=None, areas=None):
    """Get Temperature change rows with optional filters."""
    df = load_data()
    mask = df['Element'] == 'Temperature change'
    if not include_territories:
        pass  # applied separately per function
    if months_filter:
        if isinstance(months_filter, str):
            mask &= df['Months'] == months_filter
        else:
            mask &= df['Months'].isin(months_filter)
    if areas:
        mask &= df['Area'].isin(areas)
    return df[mask].copy()

def get_countries(include_territories=False):
    df = load_data()
    mask = (df['Area Code'] <= 5000) & (df['Element'] == 'Temperature change')
    if not include_territories:
        mask &= ~df['is_territory']
    return sorted(df[mask]['Area'].unique().tolist())

def get_regions():
    df = load_data()
    mask = (df['Area Code'] > 5000) & (df['Element'] == 'Temperature change')
    return sorted(df[mask]['Area'].unique().tolist())

def get_years():
    df = load_data()
    return sorted(df['Year'].dropna().unique().astype(int).tolist())

def get_annual_data(area=None):
    """Annual (Meteorological year) anomaly per area."""
    tc = get_tc(months_filter='Meteorological year')
    if area:
        tc = tc[tc['Area'] == area]
    return tc[['Area', 'Area Code', 'is_territory', 'Year', 'Value']].dropna(subset=['Value']).rename(columns={'Value': 'TempChange'})

def get_monthly_data(area):
    """Monthly anomaly for a specific area."""
    tc = get_tc(months_filter=MONTH_ORDER, areas=[area])
    return tc[['Area', 'Months', 'Year', 'Value']].dropna(subset=['Value']).rename(columns={'Value': 'TempChange'})

def get_top_warmers(n=20, include_territories=False, period_start=2010, period_end=2019):
    df = load_data()
    mask = (
        (df['Element'] == 'Temperature change') &
        (df['Months'] == 'Meteorological year') &
        (df['Area Code'] <= 5000)
    )
    if not include_territories:
        mask &= ~df['is_territory']
    annual = df[mask][['Area', 'is_territory', 'Year', 'Value']].copy()

    early = annual[annual['Year'].between(1961, 1970)].groupby(['Area','is_territory'])['Value'].mean().rename('early_avg')
    late  = annual[annual['Year'].between(period_start, period_end)].groupby(['Area','is_territory'])['Value'].mean().rename('late_avg')

    result = pd.concat([early, late], axis=1).dropna()
    result['delta']      = result['late_avg'] - result['early_avg']
    result['recent_avg'] = result['late_avg']
    result = result.reset_index()
    return result.sort_values('delta', ascending=False).head(n)

def get_choropleth_data(year, include_territories=False):
    df = load_data()
    mask = (
        (df['Element'] == 'Temperature change') &
        (df['Months'] == 'Meteorological year') &
        (df['Area Code'] <= 5000) &
        (df['Year'] == year)
    )
    if not include_territories:
        mask &= ~df['is_territory']
    result = df[mask][['Area', 'Value']].dropna().copy()
    result['Area'] = result['Area'].replace(COUNTRY_NAME_MAP)
    return result.rename(columns={'Value': 'TempChange'})

def get_regional_comparison(regions_list):
    df = load_data()
    mask = (
        (df['Element'] == 'Temperature change') &
        (df['Months'] == 'Meteorological year') &
        (df['Area'].isin(regions_list))
    )
    return df[mask][['Area', 'Year', 'Value']].dropna(subset=['Value']).rename(columns={'Value': 'TempChange'})

def get_yearly_heatmap_data(area):
    """Month × decade average for a specific area."""
    tc = get_tc(months_filter=MONTH_ORDER, areas=[area])
    tc = tc.dropna(subset=['Value']).copy()
    tc['Decade'] = (tc['Year'] // 10 * 10).astype(str) + 's'
    return tc[['Months', 'Decade', 'Value']].rename(columns={'Value': 'TempChange'})

def get_correlation_data():
    """Annual anomaly per region for correlation matrix."""
    regions = ['Africa', 'Asia', 'Europe', 'Americas', 'Oceania']
    df = load_data()
    mask = (
        (df['Element'] == 'Temperature change') &
        (df['Months'] == 'Meteorological year') &
        (df['Area'].isin(regions))
    )
    pivot = df[mask].pivot_table(index='Year', columns='Area', values='Value', aggfunc='mean')
    return pivot.dropna()

def get_boxplot_data(area):
    """Annual anomaly grouped by decade for box plot."""
    annual = get_annual_data(area)
    annual = annual.dropna(subset=['TempChange']).copy()
    annual['Decade'] = (annual['Year'] // 10 * 10).astype(str) + 's'
    return annual[['Decade', 'TempChange']]

def get_dataset_page(page=1, per_page=50, area='', month='', element='', search=''):
    """Paginated dataset for viewer — long format, all years."""
    df = load_data()
    filtered = df.copy()
    if area:
        filtered = filtered[filtered['Area'] == area]
    if month:
        filtered = filtered[filtered['Months'] == month]
    if element:
        filtered = filtered[filtered['Element'] == element]
    if search:
        filtered = filtered[filtered['Area'].str.contains(search, case=False, na=False)]

    total = len(filtered)
    start = (page - 1) * per_page
    display_cols = ['Area Code', 'Area', 'Months', 'Element', 'Unit', 'Year', 'Value']
    page_df = filtered[display_cols].iloc[start:start+per_page].copy()
    page_df['Value'] = page_df['Value'].round(3)
    page_df = page_df.fillna('—')

    return {
        'total':    total,
        'page':     page,
        'per_page': per_page,
        'pages':    max(1, (total + per_page - 1) // per_page),
        'columns':  display_cols,
        'rows':     page_df.values.tolist(),
        'areas':    sorted(df['Area'].unique().tolist()),
        'months':   sorted(df['Months'].unique().tolist()),
        'elements': sorted(df['Element'].unique().tolist()),
    }

def warm_cache():
    print("Pre-loading climate data into cache...")
    load_data()
    get_annual_data()
    get_top_warmers(30, include_territories=False)
    get_top_warmers(30, include_territories=True)
    get_correlation_data()
    print("Cache ready.")

def get_trend_stats(area):
    """Calculate linear warming trend and project to 2024 and 2029."""
    import numpy as np
    df = load_data()
    tc = df[
        (df['Element'] == 'Temperature change') &
        (df['Months'] == 'Meteorological year') &
        (df['Area'] == area)
    ].dropna(subset=['Value']).sort_values('Year')

    if len(tc) < 10:
        return None

    years = tc['Year'].astype(int).values
    vals  = tc['Value'].astype(float).values

    z = np.polyfit(years, vals, 1)
    p = np.poly1d(z)

    return {
        'area':          area,
        'rate_per_year': round(float(z[0]), 4),
        'last_year':     int(years[-1]),
        'last_value':    round(float(vals[-1]), 3),
        'early_avg':     round(float(vals[:10].mean()), 3),   # 1961-70
        'recent_avg':    round(float(vals[-10:].mean()), 3),  # 2010-19
        'proj_2024':     round(float(p(2024)), 3),
        'proj_2029':     round(float(p(2029)), 3),
        'total_delta':   round(float(vals[-10:].mean() - vals[:10].mean()), 3),
    }