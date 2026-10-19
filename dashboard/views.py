import json
import os
import plotly.graph_objects as go
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder
from django.shortcuts import render
from django.http import JsonResponse

from .data_loader import (
    load_data, get_countries, get_regions, get_years,
    get_annual_data, get_monthly_data, get_top_warmers,
    get_choropleth_data, get_regional_comparison,
    get_yearly_heatmap_data, get_correlation_data,
    get_boxplot_data, get_dataset_page, get_trend_stats
)

PALETTE = {'cold':'#4fc3f7','hot':'#ef5350','accent':'#f0a500','muted':'#6e7681'}

DEFAULT_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family='Open Sans, sans-serif', color='#c9d1d9', size=11),
    margin=dict(l=50, r=20, t=40, b=40),
    legend=dict(bgcolor='rgba(0,0,0,0)', bordercolor='#30363d', borderwidth=1),
    xaxis=dict(gridcolor='#21262d', zerolinecolor='#30363d'),
    yaxis=dict(gridcolor='#21262d', zerolinecolor='#30363d'),
)

def _rate_limit_response(request, exception):
    """Return clean JSON 429 when rate limit is hit."""
    return JsonResponse({
        'error': 'Too many requests. Please slow down and try again shortly.',
        'retry_after': 60,
    }, status=429)


def _json(fig):
    return json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))

def _layout(**extra):
    l = dict(**DEFAULT_LAYOUT)
    l.update(extra)
    return l

# ── PAGES ──

def landing(request):
    return render(request, 'dashboard/landing.html', {})

def index(request):
    countries = get_countries(include_territories=False)
    all_areas = get_countries(include_territories=True)
    regions   = get_regions()
    years     = get_years()
    return render(request, 'dashboard/index.html', {
        'countries':    countries,
        'all_areas':    all_areas,
        'regions':      regions,
        'years':        years,
        'year_min':     min(years),
        'year_max':     max(years),
        'default_area': 'Philippines',
    })

def dataset_page(request):
    return render(request, 'dashboard/dataset.html', {})

# ── API ──

def handle_429(request, exception):
    """Global 429 handler — returns JSON for API calls, plain text for pages."""
    if request.path.startswith('/api/'):
        return JsonResponse({
            'error': 'Rate limit exceeded. Please wait before making more requests.',
            'retry_after': 60,
        }, status=429)
    from django.http import HttpResponse
    return HttpResponse(
        'Too many requests. Please wait a moment and try again.',
        status=429, content_type='text/plain'
    )


@ratelimit(key='ip', rate='60/m', block=True)
def api_timeseries(request):
    area   = request.GET.get('area', 'Philippines')
    smooth = request.GET.get('smooth', 'false') == 'true'
    data   = get_annual_data(area).sort_values('Year')
    if data.empty:
        return JsonResponse({'error': 'No data for {}'.format(area)}, status=404)

    y = data['TempChange']
    fig = go.Figure()
    fig.add_hline(y=0, line_dash='dot', line_color='#30363d', line_width=1)
    fig.add_trace(go.Bar(
        x=data['Year'], y=y,
        marker_color=[PALETTE['hot'] if v >= 0 else PALETTE['cold'] for v in y],
        name='Annual anomaly',
        hovertemplate='<b>%{x}</b><br>%{y:.2f}°C<extra></extra>',
    ))
    if smooth and len(data) > 5:
        import numpy as np
        z = np.polyfit(data['Year'].astype(int), y, 1)
        p = np.poly1d(z)
        fig.add_trace(go.Scatter(
            x=data['Year'], y=p(data['Year'].astype(int)),
            mode='lines', line=dict(color=PALETTE['accent'], width=2, dash='dash'),
            name='Trend ({:+.4f}°C/yr)'.format(z[0]),
        ))
    fig.update_layout(**_layout(
        title=dict(text='Temperature Anomaly — {}'.format(area), font=dict(size=13)),
        yaxis_title='°C vs 1951–1980 baseline',
        hovermode='x unified', height=320,
    ))
    return JsonResponse({'chart': _json(fig)})


@ratelimit(key='ip', rate='60/m', block=True)
def api_monthly_heatmap(request):
    area = request.GET.get('area', 'Philippines')
    data = get_monthly_data(area)
    if data.empty:
        return JsonResponse({'error': 'No data for {}'.format(area)}, status=404)

    MONTH_ORDER = ['January','February','March','April','May','June',
                   'July','August','September','October','November','December']
    pivot = data.pivot_table(index='Months', columns='Year', values='TempChange', aggfunc='mean')
    pivot = pivot.reindex(MONTH_ORDER)
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.astype(int).tolist(),
        y=[m[:3] for m in pivot.index.tolist()],
        colorscale=[[0,'#4fc3f7'],[0.5,'#1a1a2e'],[1,'#ef5350']],
        zmid=0,
        colorbar=dict(title='°C', tickfont=dict(color='#c9d1d9', size=9)),
        hovertemplate='<b>%{y} %{x}</b><br>%{z:.2f}°C<extra></extra>',
    ))
    fig.update_layout(**_layout(
        title=dict(text='Monthly Anomaly Heatmap — {}'.format(area), font=dict(size=13)),
        height=300, yaxis=dict(gridcolor='#21262d', autorange='reversed'),
    ))
    return JsonResponse({'chart': _json(fig)})


@ratelimit(key='ip', rate='60/m', block=True)
def api_heatmap_yearly(request):
    area = request.GET.get('area', 'Philippines')
    data = get_yearly_heatmap_data(area)
    if data.empty:
        return JsonResponse({'error': 'No data for {}'.format(area)}, status=404)

    MONTH_ORDER = ['January','February','March','April','May','June',
                   'July','August','September','October','November','December']
    pivot = data.pivot_table(index='Months', columns='Decade', values='TempChange', aggfunc='mean')
    pivot = pivot.reindex(MONTH_ORDER)
    decade_order = sorted(pivot.columns.tolist())
    pivot = pivot[decade_order]

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=[m[:3] for m in pivot.index.tolist()],
        colorscale=[[0,'#4fc3f7'],[0.5,'#1a1a2e'],[1,'#ef5350']],
        zmid=0,
        text=[['{:.2f}'.format(v) if v == v else '' for v in row] for row in pivot.values],
        texttemplate='%{text}', textfont=dict(size=9),
        colorbar=dict(title='°C', tickfont=dict(color='#c9d1d9', size=9)),
        hovertemplate='<b>%{y} %{x}</b><br>%{z:.2f}°C avg<extra></extra>',
    ))
    fig.update_layout(**_layout(
        title=dict(text='Decadal Monthly Average — {}'.format(area), font=dict(size=13)),
        height=340, yaxis=dict(gridcolor='#21262d', autorange='reversed'),
    ))
    return JsonResponse({'chart': _json(fig)})


@ratelimit(key='ip', rate='20/m', block=True)
def api_choropleth(request):
    year             = int(request.GET.get('year', 2019))
    incl_territories = request.GET.get('territories', 'false') == 'true'
    data = get_choropleth_data(year, include_territories=incl_territories)
    if data.empty:
        return JsonResponse({'error': 'No data'}, status=404)

    fig = go.Figure(go.Choropleth(
        locations=data['Area'], locationmode='country names',
        z=data['TempChange'],
        colorscale=[[0,'#4fc3f7'],[0.45,'#161b22'],[0.55,'#161b22'],[1,'#ef5350']],
        zmid=0, zmin=-3, zmax=3,
        colorbar=dict(title='°C', tickfont=dict(color='#c9d1d9', size=9)),
        hovertemplate='<b>%{location}</b><br>%{z:.2f}°C<extra></extra>',
        marker_line_color='#30363d', marker_line_width=0.4,
    ))
    fig.update_layout(**_layout(
        title=dict(text='Global Temperature Anomaly — {}'.format(year), font=dict(size=13)),
        geo=dict(
            showframe=False, showcoastlines=True, coastlinecolor='#30363d',
            bgcolor='rgba(0,0,0,0)', showland=True, landcolor='#161b22',
            showocean=True, oceancolor='#0d1117', projection_type='natural earth',
        ),
        height=380,
    ))
    return JsonResponse({'chart': _json(fig)})


@ratelimit(key='ip', rate='60/m', block=True)
def api_top_warmers(request):
    n                = int(request.GET.get('n', 10))
    incl_territories = request.GET.get('territories', 'false') == 'true'
    data = get_top_warmers(n, include_territories=incl_territories)

    labels = [row['Area'] + (' *' if row['is_territory'] else '') for _, row in data.iterrows()]
    fig = go.Figure(go.Bar(
        x=data['delta'].round(2), y=labels, orientation='h',
        marker=dict(color=data['delta'], colorscale=[[0,'#f0a500'],[1,'#ef5350']]),
        hovertemplate='<b>%{y}</b><br>+%{x:.2f}°C warming<extra></extra>',
    ))
    note = '  * territory / dependency' if incl_territories else ''
    fig.update_layout(**_layout(
        title=dict(text='Top {} Most Warmed — 1961–70 vs 2010–19{}'.format(n, note), font=dict(size=12)),
        xaxis_title='°C warming', height=max(320, n * 24),
        margin=dict(l=160, r=20, t=40, b=40),
        yaxis=dict(gridcolor='#21262d', autorange='reversed'),
    ))
    return JsonResponse({'chart': _json(fig)})


@ratelimit(key='ip', rate='60/m', block=True)
def api_regional_comparison(request):
    selected = request.GET.getlist('regions') or ['Africa','Asia','Europe','Americas','Oceania']
    data = get_regional_comparison(selected)
    if data.empty:
        return JsonResponse({'error': 'No data'}, status=404)

    colors = px.colors.qualitative.Set2
    fig = go.Figure()
    for i, region in enumerate(selected):
        rdata = data[data['Area'] == region].sort_values('Year')
        fig.add_trace(go.Scatter(
            x=rdata['Year'], y=rdata['TempChange'],
            mode='lines', name=region,
            line=dict(color=colors[i % len(colors)], width=2),
            hovertemplate='<b>{}</b><br>%{{x}}: %{{y:.2f}}°C<extra></extra>'.format(region),
        ))
    fig.add_hline(y=0, line_dash='dot', line_color='#30363d', line_width=1)
    fig.update_layout(**_layout(
        title=dict(text='Regional Temperature Anomaly Comparison', font=dict(size=13)),
        yaxis_title='°C vs baseline', hovermode='x unified', height=340,
    ))
    return JsonResponse({'chart': _json(fig)})


@ratelimit(key='ip', rate='60/m', block=True)
def api_correlation(request):
    corr_data = get_correlation_data()
    corr = corr_data.corr().round(3)
    labels = corr.columns.tolist()
    z = corr.values.tolist()

    fig = go.Figure(go.Heatmap(
        z=z, x=labels, y=labels,
        colorscale=[[0,'#4fc3f7'],[0.5,'#161b22'],[1,'#ef5350']],
        zmin=-1, zmax=1, zmid=0,
        text=[['{:.2f}'.format(v) for v in row] for row in z],
        texttemplate='%{text}', textfont=dict(size=11, color='#e6edf3'),
        colorbar=dict(title='r', tickfont=dict(color='#c9d1d9', size=9)),
        hovertemplate='%{y} vs %{x}<br>r = %{z:.3f}<extra></extra>',
    ))
    fig.update_layout(**_layout(
        title=dict(text='Regional Correlation Matrix (Annual Anomaly)', font=dict(size=13)),
        height=320, margin=dict(l=80, r=20, t=40, b=80),
        xaxis=dict(gridcolor='#21262d', tickangle=-30),
    ))

    table = [{'region': r, **{c: corr.loc[r, c] for c in labels}} for r in labels]
    return JsonResponse({'chart': _json(fig), 'table': table, 'labels': labels})


@ratelimit(key='ip', rate='60/m', block=True)
def api_boxplot(request):
    area = request.GET.get('area', 'Philippines')
    data = get_boxplot_data(area)
    if data.empty:
        return JsonResponse({'error': 'No data for {}'.format(area)}, status=404)

    decade_order = sorted(data['Decade'].unique())
    colors = ['#4fc3f7','#5fb8e8','#7aadce','#d4895a','#e8683a','#ef5350']
    fig = go.Figure()
    for i, dec in enumerate(decade_order):
        vals = data[data['Decade'] == dec]['TempChange'].tolist()
        fig.add_trace(go.Box(
            y=vals, name=dec,
            marker_color=colors[i % len(colors)],
            line_color=colors[i % len(colors)],
            boxmean=True,
            hovertemplate='<b>{}</b><br>%{{y:.2f}}°C<extra></extra>'.format(dec),
        ))
    fig.add_hline(y=0, line_dash='dot', line_color='#30363d', line_width=1)
    fig.update_layout(**_layout(
        title=dict(text='Annual Anomaly Distribution by Decade — {}'.format(area), font=dict(size=13)),
        yaxis_title='°C vs 1951–1980 baseline', showlegend=False, height=320,
    ))
    return JsonResponse({'chart': _json(fig)})


@ratelimit(key='ip', rate='60/m', block=True)
def api_dataset(request):
    result = get_dataset_page(
        page=int(request.GET.get('page', 1)),
        per_page=int(request.GET.get('per_page', 50)),
        area=request.GET.get('area', ''),
        month=request.GET.get('month', ''),
        element=request.GET.get('element', ''),
        search=request.GET.get('search', ''),
    )
    return JsonResponse(result)


# ── AI EXPLAIN ──
CHART_PROMPTS = {
    'timeseries': (
        "You are a climate scientist explaining a data visualization to a Master's IT student. "
        "The chart is an Annual Temperature Anomaly Time Series for {area}, showing yearly temperature "
        "deviations (°C) from the 1951-1980 baseline from 1961 to 2019. Red bars = warmer, blue = cooler. {smooth_note} "
        "Trend data: warming rate {rate_per_year}C/year, early average (1961-70) {early_avg}C, "
        "recent average (2010-19) {recent_avg}C, last recorded (2019) {last_value}C, "
        "projected 2024: {proj_2024}C, projected 2029: {proj_2029}C. "
        "Paragraph 1 (3 sentences): explain what this chart shows and what the warming pattern means for {area} specifically. "
        "Paragraph 2 (2-3 sentences): based on the linear trend, describe what temperatures are projected to look like "
        "by 2024 and 2029 for {area}, and what real-world impacts this level of warming could bring to this country."
    ),
    'choropleth': (
        "You are a climate scientist explaining a data visualization to a Master's IT student. "
        "The chart is a global choropleth map showing temperature anomalies (°C vs 1951-1980 baseline) "
        "for the year {year}. Red = warmer, blue = cooler. Scope: {scope}. "
        "Paragraph 1 (3 sentences): explain what this map reveals about global warming patterns in {year} "
        "and which regions stand out. "
        "Paragraph 2 (2 sentences): based on the warming trajectory observed up to {year}, project which "
        "regions are most at risk by 2029 and what the global map might look like if current trends continue."
    ),
    'top_warmers': (
        "You are a climate scientist explaining a data visualization to a Master's IT student. "
        "The chart ranks the top {n} most warmed {scope} comparing 1960s vs 2010s anomaly. "
        "Ranked list: {countries}. "
        "Paragraph 1 (3 sentences): explain specifically why these countries top the list, referencing "
        "actual country names and their geographic or climate characteristics. Do not invent countries not in the list. "
        "Paragraph 2 (2 sentences): project how these top-ranked countries are likely to continue warming "
        "through 2029 if current trends persist, and what that means for their populations."
    ),
    'heatmap_monthly': (
        "You are a climate scientist explaining a data visualization to a Master's IT student. "
        "The chart is a Monthly Anomaly Heatmap for {area}, showing temperature deviation (°C) "
        "for each month across each year from 1961 to 2019. "
        "Trend data: warming rate {rate_per_year}C/year, projected 2029: {proj_2029}C. "
        "Paragraph 1 (3 sentences): explain which months show the strongest warming signal and what seasonal "
        "patterns reveal about climate change in {area}. "
        "Paragraph 2 (2 sentences): project how seasonal warming patterns in {area} might intensify by 2029 "
        "and what months are most at risk of extreme heat anomalies."
    ),
    'heatmap_yearly': (
        "You are a climate scientist explaining a data visualization to a Master's IT student. "
        "The chart is a Decadal Monthly Heatmap for {area}, showing average anomaly per month per decade. "
        "Trend data: warming rate {rate_per_year}C/year, projected 2029: {proj_2029}C. "
        "Paragraph 1 (3 sentences): explain the decade-by-decade progression visible in the chart and "
        "which months show the clearest acceleration for {area}. "
        "Paragraph 2 (2 sentences): extrapolate what the 2020s decade cell might look like by 2029 "
        "based on the current trajectory, and what that implies for {area}."
    ),
    'heatmap_corr': (
        "You are a climate scientist explaining a data visualization to a Master's IT student. "
        "The chart is a Correlation Heatmap showing Pearson r values between annual temperature "
        "anomaly time series of 5 regions: Africa, Asia, Europe, Americas, Oceania. "
        "Paragraph 1 (3 sentences): explain what the correlation values mean, which pair is most "
        "correlated and which is least, and why Europe tends to be more independent. "
        "Paragraph 2 (2 sentences): explain what high inter-regional correlation implies about "
        "future warming — if one region accelerates toward 2029, what does that mean for the others."
    ),
    'regional': (
        "You are a climate scientist explaining a data visualization to a Master's IT student. "
        "The chart shows annual temperature anomaly trend lines for: {regions}, from 1961 to 2019. "
        "Paragraph 1 (3 sentences): explain the divergence or convergence of these lines, "
        "which region is warming fastest, and what the acceleration since the 1980s signals. "
        "Paragraph 2 (2 sentences): based on current trajectories, project where each region's "
        "anomaly line is likely to be by 2029, and which region faces the steepest warming ahead."
    ),
    'boxplot': (
        "You are a climate scientist explaining a data visualization to a Master's IT student. "
        "The chart shows distribution of annual anomalies by decade for {area}. "
        "Trend data: warming rate {rate_per_year}C/year, recent avg (2010-19) {recent_avg}C, "
        "projected 2024: {proj_2024}C, projected 2029: {proj_2029}C. "
        "Paragraph 1 (3 sentences): explain what the upward shift in median and boxes means decade "
        "by decade, and what the 2010s box position tells us about how far {area} has already warmed. "
        "Paragraph 2 (2 sentences): describe what the hypothetical 2020s box might look like by 2029 "
        "based on the projected {proj_2029}C anomaly, and what that level of warming means for {area}."
    ),
}

@ratelimit(key='ip', rate='10/m', block=True)
def api_explain(request):
    from django.http import StreamingHttpResponse
    chart   = request.GET.get('chart', '')
    area    = request.GET.get('area', 'Philippines')
    year    = request.GET.get('year', '2019')
    n       = request.GET.get('n', '10')
    scope   = request.GET.get('scope', 'sovereign countries')
    smooth  = request.GET.get('smooth', 'false')
    regions = request.GET.get('regions', 'Africa, Asia, Europe, Americas, Oceania')

    # For top_warmers: fetch actual ranked list
    countries_list = ''
    if chart == 'top_warmers':
        incl_terr = scope != 'sovereign countries'
        top_data = get_top_warmers(int(n), include_territories=incl_terr)
        countries_list = ', '.join([
            '{} (+{:.2f}C)'.format(row['Area'], row['delta'])
            for _, row in top_data.iterrows()
        ])

    # Fetch trend stats for area-based charts (provides real numbers for prediction)
    trend = get_trend_stats(area)
    if trend is None:
        trend = {
            'rate_per_year': 0.0, 'early_avg': 0.0, 'recent_avg': 0.0,
            'last_value': 0.0, 'proj_2024': 0.0, 'proj_2029': 0.0,
            'total_delta': 0.0,
        }

    # For top_warmers / choropleth / regional / corr — use global avg trend
    if chart in ('top_warmers', 'choropleth', 'heatmap_corr', 'regional'):
        # Use Asia as global proxy if area not relevant
        global_trend = get_trend_stats('Asia') or trend
        trend = global_trend

    template = CHART_PROMPTS.get(chart, '')
    if not template:
        return JsonResponse({'error': 'Unknown chart type'}, status=400)

    smooth_note = 'A trend line is overlaid showing the linear rate of change.' if smooth == 'true' else ''
    prompt = template.format(
        area=area, year=year, n=n, scope=scope,
        smooth_note=smooth_note, regions=regions,
        countries=countries_list,
        rate_per_year='{:+.4f}'.format(trend['rate_per_year']),
        early_avg='{:+.3f}'.format(trend['early_avg']),
        recent_avg='{:+.3f}'.format(trend['recent_avg']),
        last_value='{:+.3f}'.format(trend['last_value']),
        proj_2024='{:+.3f}'.format(trend['proj_2024']),
        proj_2029='{:+.3f}'.format(trend['proj_2029']),
        total_delta='{:+.3f}'.format(trend['total_delta']),
    )

    api_key = os.environ.get('GROQ_API_KEY', '')
    if not api_key or api_key.startswith('placeholder'):
        return JsonResponse({'text': (
            "To enable AI-powered chart explanations, add your free Groq API key to the .env file.\n\n"
            "1. Sign up at console.groq.com (free, no credit card)\n"
            "2. Create an API key\n"
            "3. Open .env in the project root\n"
            "4. Replace 'placeholder_replace_with_real_key' with your key\n"
            "5. Restart the Django server"
        ), 'placeholder': True})

    def stream_groq():
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            stream = client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                messages=[
                    {'role': 'system', 'content': 'You are a helpful climate data analyst. Be concise, specific, and educational.'},
                    {'role': 'user',   'content': prompt},
                ],
                max_tokens=300, stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:
            yield '\n\n[Error contacting Groq API: {}]'.format(str(e))

    resp = StreamingHttpResponse(stream_groq(), content_type='text/plain; charset=utf-8')
    resp['X-Accel-Buffering'] = 'no'
    resp['Cache-Control'] = 'no-cache'
    return resp