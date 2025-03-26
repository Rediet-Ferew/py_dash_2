import dash
from dash import dcc, html, dash_table
import plotly.express as px
import pandas as pd
import io
import base64
from dash.dependencies import Input, Output, State
import time

# Initialize Dash app
app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "CSV Data Visualization"
server = app.server

data = None  # Global variable to store processed data

def monthly_breakdown(file_path):
    # Load data
    df = pd.read_csv(file_path)

    # Ensure date is in datetime format
    df['job_date'] = pd.to_datetime(df['job_date'], format='%Y-%m-%d', errors='coerce')

    # Add month column for aggregation
    df['month'] = df['job_date'].dt.to_period('M')

    # Find first visit date for each customer
    first_visits = df.groupby('phone')['job_date'].min().reset_index()
    first_visits.columns = ['phone', 'first_visit_date']

    # Merge first visit date back to main dataframe
    df = pd.merge(df, first_visits, on='phone')

    # Create period for first visit month
    df['first_visit_month'] = df['first_visit_date'].dt.to_period('M')

    # Monthly breakdown of new vs returning
    monthly_results = []

    for month in sorted(df['month'].unique()):
        # Filter data for current month
        month_data = df[df['month'] == month]

        # Count unique customers for the month
        total_customers = month_data['phone'].nunique()

        # Count new customers (first visit in this month)
        new_customers = month_data[month_data['month'] == month_data['first_visit_month']]['phone'].nunique()

        # Count returning customers
        returning_customers = total_customers - new_customers

        # Calculate percentages
        new_percentage = round((new_customers / total_customers * 100), 2) if total_customers > 0 else 0
        returning_percentage = round((returning_customers / total_customers * 100), 2) if total_customers > 0 else 0

        # Total revenue for the month
        month_revenue = month_data['price'].sum()

        # Revenue from new vs returning
        new_revenue = month_data[month_data['month'] == month_data['first_visit_month']]['price'].sum()
        returning_revenue = month_revenue - new_revenue

        monthly_results.append({
            'month': month,
            'total_customers': total_customers,
            'new_customers': new_customers,
            'returning_customers': returning_customers,
            'new_percentage': new_percentage,
            'returning_percentage': returning_percentage,
            'total_revenue': month_revenue,
            'new_customer_revenue': new_revenue,
            'returning_customer_revenue': returning_revenue
        })

    # Convert results to DataFrame
    monthly_df = pd.DataFrame(monthly_results)

# Convert 'month' column to string
    monthly_df['month'] = monthly_df['month'].astype(str)

    # Calculate LTV
    total_revenue = df['price'].sum()
    unique_customers = df['phone'].nunique()
    basic_ltv = total_revenue / unique_customers

    avg_purchase_value = total_revenue / len(df)
    avg_purchase_frequency = len(df) / unique_customers

    # Customer lifespan calculation (simplified)
    df_sorted = df.sort_values(['phone', 'job_date'])

    # Calculate days between visits for each customer
    df_sorted['next_visit'] = df_sorted.groupby('phone')['job_date'].shift(-1)
    df_sorted['days_between_visits'] = (df_sorted['next_visit'] - df_sorted['job_date']).dt.days

    # Compute average days between visits
    avg_days_between_visits = df_sorted['days_between_visits'].mean()
    churn_threshold = 180
    avg_customer_lifespan = churn_threshold / avg_days_between_visits

    # Calculate LTV
    ltv = avg_purchase_value * avg_purchase_frequency * avg_customer_lifespan

    return {
        'monthly_breakdown': monthly_df,
        'Basic LTV': basic_ltv,
        'Advanced LTV': ltv,
        'Average Purchase Value': avg_purchase_value,
        'Average Purchase Frequency': avg_purchase_frequency,
        'Average Customer LifeSpan(Months)': avg_customer_lifespan
    }

def generate_visuals(df):
    return html.Div([
        html.H2("📊 Data Table"),
        dash_table.DataTable(
            columns=[{"name": col, "id": col} for col in df.columns],
            data=df.round(2).to_dict('records'),
            style_table={'overflowX': 'auto'}
        ),
        html.H2("📈 Monthly Trends"),
        dcc.Graph(figure=px.line(df, x='month', y=['new_customers', 'returning_customers'], markers=True)),
        dcc.Graph(figure=px.bar(df, x='month', y=['total_revenue', 'new_customer_revenue', 'returning_customer_revenue'], barmode='group')),
    ])

def generate_ltv_metrics(processed_data):
    return html.Div([
        html.H2("📊 LTV Metrics"),
        html.P(f"Basic LTV: ${processed_data['Basic LTV']:.2f}"),
        html.P(f"Advanced LTV: ${processed_data['Advanced LTV']:.2f}"),
        html.P(f"Average Purchase Value: ${processed_data['Average Purchase Value']:.2f}"),
        html.P(f"Average Purchase Frequency: {processed_data['Average Purchase Frequency']:.2f}"),
        html.P(f"Average Customer Lifespan (Months): {processed_data['Average Customer LifeSpan(Months)']:.2f}"),
    ])

# Layout
app.layout = html.Div([
    html.H1("📂 Upload CSV & Visualize"),
    dcc.Upload(
        id='upload-data',
        children=html.Button("📤 Upload CSV"),
        multiple=False,
        style={"marginBottom": "20px"}
    ),
    html.Div(id='loading-message', style={'color': 'blue', 'marginTop': '10px'}),
    dcc.Tabs([
        dcc.Tab(label='Data Visualization', children=[
            html.Div(id='visualization-content')
        ]),
        dcc.Tab(label='LTV Metrics', children=[
            html.Div(id='ltv-metrics-content')
        ]),
    ]),
])

@app.callback(
    [Output('visualization-content', 'children'),
     Output('ltv-metrics-content', 'children'),
     Output('loading-message', 'children')],
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    prevent_initial_call=True
)
def update_output(contents, filename):
    global data
    if contents is None:
        return dash.no_update, dash.no_update, "⚠️ No file uploaded!"

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    # Pass the decoded content as a StringIO object to pd.read_csv
    processed_data = monthly_breakdown(io.StringIO(decoded.decode('utf-8')))  # Use StringIO for CSV

    time.sleep(2)
    data = processed_data  # Store processed data globally
    
    # Generate visuals
    visuals = generate_visuals(processed_data['monthly_breakdown'])
    
    # LTV Metrics
    ltv_metrics = generate_ltv_metrics(processed_data)
    
    return visuals, ltv_metrics, "✅ File uploaded & processed!"

if __name__ == '__main__':
    app.run(debug=True)
