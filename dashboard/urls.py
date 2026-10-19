from django.urls import path
from . import views

urlpatterns = [
    path('',                         views.landing,                 name='landing'),
    path('dashboard/',               views.index,                   name='index'),
    path('dataset/',                 views.dataset_page,            name='dataset'),
    path('api/timeseries/',          views.api_timeseries),
    path('api/monthly-heatmap/',     views.api_monthly_heatmap),
    path('api/heatmap-yearly/',      views.api_heatmap_yearly),
    path('api/choropleth/',          views.api_choropleth),
    path('api/top-warmers/',         views.api_top_warmers),
    path('api/regional-comparison/', views.api_regional_comparison),
    path('api/correlation/',         views.api_correlation),
    path('api/boxplot/',             views.api_boxplot),
    path('api/explain/',             views.api_explain),
    path('api/dataset/',             views.api_dataset),
]
