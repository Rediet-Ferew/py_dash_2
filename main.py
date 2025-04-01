import dash
from dash import dcc, html, dash_table
import plotly.express as px
import pandas as pd
import io
import base64
import json
import os
from dash.dependencies import Input, Output, State

# Initialize Dash app
app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "CSV Data Visualization"
server = app.server

# Define file path for storing processed data
PROCESSED_DATA_FILE = 'output_data.json'

# Store uploaded data persistently
app.layout = html.Div([
    dcc.Store(id='stored-data', storage_type='local'),  # Stores the cleaned DataFrame
    dcc.Location(id='url', refresh=False),

    html.H1("📂 Upload CSV & Visualize"),
    dcc.Upload(
        id='upload-data',
        children=html.Button("📤 Upload CSV"),
        multiple=True,
        style={"marginBottom": "20px"}
    ),
    html.Div(id='loading-message', style={'color': 'blue', 'marginTop': '10px'}),

    # Navigation buttons
    html.Div([
        dcc.Link('📊 Monthly Breakdown', href='/'),
        " | ",
        dcc.Link('📈 LTV Calculations', href='/ltv')
    ], style={'marginBottom': '20px'}),

    html.Div(id='page-content')  # Main content placeholder
])

# Function to clean and merge CSV data
def clean_and_merge_data(contents_list):
    dfs = []
    for content in contents_list:
        content_type, content_string = content.split(',')
        decoded = base64.b64decode(content_string)
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), index_col=False)
        dfs.append(df)

    merged_df = pd.concat(dfs, ignore_index=True)
    df_needed = merged_df[['PHONE NO', 'DRIVER PRICE', 'JOB DATE']]
    df_needed.columns = ['phone', 'price', 'job_date']
    df_cleaned = df_needed[df_needed["phone"].notna() & (df_needed["phone"] != "")]

    df_cleaned.loc[:, "job_date"] = pd.to_datetime(df_cleaned["job_date"], format="%d/%m/%y %H:%M:%S", errors='coerce', dayfirst=True).dt.date

    return df_cleaned

# Function to compute monthly breakdown & LTV
def monthly_breakdown(df):
    df['job_date'] = pd.to_datetime(df['job_date'], errors='coerce')
    df['month'] = df['job_date'].dt.to_period('M')

    first_visits = df.groupby('phone')['job_date'].min().reset_index()
    first_visits.columns = ['phone', 'first_visit_date']
    df = pd.merge(df, first_visits, on='phone')
    df['first_visit_month'] = df['first_visit_date'].dt.to_period('M')

    monthly_results = []
    for month in sorted(df['month'].unique()):
        month_data = df[df['month'] == month]
        total_customers = month_data['phone'].nunique()
        new_customers = month_data[month_data['month'] == month_data['first_visit_month']]['phone'].nunique()
        returning_customers = total_customers - new_customers

        new_percentage = round((new_customers / total_customers * 100), 2) if total_customers > 0 else 0
        returning_percentage = round((returning_customers / total_customers * 100), 2) if total_customers > 0 else 0

        month_revenue = month_data['price'].sum()
        new_revenue = month_data[month_data['month'] == month_data['first_visit_month']]['price'].sum()
        returning_revenue = month_revenue - new_revenue

        monthly_results.append({
            'month': str(month),
            'total_customers': total_customers,
            'new_customers': new_customers,
            'returning_customers': returning_customers,
            'new_percentage': new_percentage,
            'returning_percentage': returning_percentage,
            'total_revenue': month_revenue,
            'new_customer_revenue': new_revenue,
            'returning_customer_revenue': returning_revenue
        })

    monthly_df = pd.DataFrame(monthly_results)

    # Convert DataFrame to JSON serializable format
    monthly_dict = monthly_df.to_dict('records')

    # LTV Calculations
    total_revenue = df['price'].sum()
    unique_customers = df['phone'].nunique()
    basic_ltv = total_revenue / unique_customers if unique_customers > 0 else 0

    avg_purchase_value = total_revenue / len(df) if len(df) > 0 else 0
    avg_purchase_frequency = len(df) / unique_customers if unique_customers > 0 else 0

    df_sorted = df.sort_values(['phone', 'job_date'])
    df_sorted['next_visit'] = df_sorted.groupby('phone')['job_date'].shift(-1)
    df_sorted['days_between_visits'] = (df_sorted['next_visit'] - df_sorted['job_date']).dt.days

    avg_days_between_visits = df_sorted['days_between_visits'].mean() if not df_sorted['days_between_visits'].isna().all() else 1
    churn_threshold = 180
    avg_customer_lifespan = churn_threshold / avg_days_between_visits if avg_days_between_visits > 0 else 0

    advanced_ltv = avg_purchase_value * avg_purchase_frequency * avg_customer_lifespan

    return {
        'monthly_breakdown': monthly_dict,  # Convert DataFrame to JSON serializable format
        'Basic LTV': basic_ltv,
        'Advanced LTV': advanced_ltv,
        'Average Purchase Value': avg_purchase_value,
        'Average Purchase Frequency': avg_purchase_frequency,
        'Average Customer LifeSpan (Months)': avg_customer_lifespan
    }

# Callback to process uploaded data and store it persistently
@app.callback(
    [Output('stored-data', 'data'), Output('loading-message', 'children')],
    Input('upload-data', 'contents'),
    prevent_initial_call=True
)
def update_data(contents_list):
    if not contents_list:
        return dash.no_update, "⚠️ No file uploaded!"
    
    df_cleaned = clean_and_merge_data(contents_list)
    processed_data = monthly_breakdown(df_cleaned)

    # Load existing data if available
    existing_data = load_processed_data()
    if existing_data:
        existing_monthly_breakdown = existing_data.get('monthly_breakdown', [])
        processed_data['monthly_breakdown'] = existing_monthly_breakdown + processed_data['monthly_breakdown']  # Append new breakdown

    # Save the processed data to file
    with open(PROCESSED_DATA_FILE, 'w') as f:
        json.dump(processed_data, f)

    return processed_data, "✅ Files uploaded & processed!"

# Function to read the processed data from file
def load_processed_data():
    if os.path.exists(PROCESSED_DATA_FILE):
        with open(PROCESSED_DATA_FILE, 'r') as f:
            return json.load(f)
    return None

def generate_visuals(df):
    return html.Div([
        html.H2("\ud83d\udcca Data Table"),
        dash_table.DataTable(
            columns=[{"name": col, "id": col} for col in df.columns],
            data=df.round(2).to_dict('records'),
            style_table={'overflowX': 'auto'}
        ),
        html.H2("\ud83d\udcc8 Monthly Trends"),
        dcc.Graph(figure=px.line(df, x='month', y=['new_customers', 'returning_customers'], markers=True)),
        dcc.Graph(figure=px.bar(df, x='month', y=['total_revenue', 'new_customer_revenue', 'returning_customer_revenue'], barmode='group')),
    ])

# Callback to update the page content
@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname'), Input('stored-data', 'data')]
)
def display_page(pathname, stored_data):
    if not stored_data:
        stored_data = load_processed_data()
        if not stored_data:
            return "\ud83d\udce4 Upload a file to begin."
    
    if pathname == '/ltv':
        return html.Div([  # LTV page
            html.H2("\ud83d\udcc8 LTV Calculations", style={"textAlign": "center", "marginBottom": "30px"}),
            html.Div([
                html.Div([
                    html.Div([
                        html.H3(f"${stored_data['Basic LTV']:.2f}", style={"fontSize": "36px", "fontWeight": "bold"}),
                        html.P("Basic LTV", style={"color": "#999", "fontSize": "18px"}),
                    ], className="card card-basic"),
                ], className="card-container"),
                
                html.Div([
                    html.Div([
                        html.H3(f"${stored_data['Advanced LTV']:.2f}", style={"fontSize": "36px", "fontWeight": "bold"}),
                        html.P("Advanced LTV", style={"color": "#999", "fontSize": "18px"}),
                    ], className="card card-advanced"),
                ], className="card-container"),
                
                html.Div([
                    html.Div([
                        html.H3(f"${stored_data['Average Purchase Value']:.2f}", style={"fontSize": "36px", "fontWeight": "bold"}),
                        html.P("Average Purchase Value", style={"color": "#999", "fontSize": "18px"}),
                    ], className="card card-purchase-value"),
                ], className="card-container"),

                html.Div([
                    html.Div([
                        html.H3(f"{stored_data['Average Purchase Frequency']:.2f}", style={"fontSize": "36px", "fontWeight": "bold"}),
                        html.P("Average Purchase Frequency", style={"color": "#999", "fontSize": "18px"}),
                    ], className="card card-frequency"),
                ], className="card-container"),

                html.Div([
                    html.Div([
                        html.H3(f"{stored_data['Average Customer LifeSpan (Months)']:.2f}", style={"fontSize": "36px", "fontWeight": "bold"}),
                        html.P("Average Customer LifeSpan (Months)", style={"color": "#999", "fontSize": "18px"}),
                    ], className="card card-lifespan"),
                ], className="card-container"),
            ], style={"display": "flex", "flexWrap": "wrap", "gap": "20px", "justifyContent": "center"})
        ])
    
    monthly_df = pd.DataFrame(stored_data['monthly_breakdown'])
    return generate_visuals(monthly_df)

if __name__ == '__main__':
    app.run(debug=True)
